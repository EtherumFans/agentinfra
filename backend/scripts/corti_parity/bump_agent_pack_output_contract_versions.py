"""Version Hub-visible output contracts after an intentional schema change.

The immutable registry keeps earlier versions append-only.  This command only
increments the final ``/vN`` segment on current visible Packs and refreshes
references owned by that same Pack.  Dry-run is the default.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENTS_DIR = REPO_ROOT / "backend" / "official_agents"
INTEGRITY_EXCLUDED_FIELDS = {
    "integrity", "downloads", "published_at", "loaded_at", "_pack_mtime_iso",
}
VERSION_RE = re.compile(r"^(?P<prefix>.+)/v(?P<version>[1-9][0-9]*)$")


def _canonical_pack_sha256(pack: dict[str, Any]) -> str:
    clean = {key: value for key, value in pack.items() if key not in INTEGRITY_EXCLUDED_FIELDS}
    payload = json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _replace_owned_reference(value: Any, old: str, new: str) -> Any:
    if isinstance(value, str):
        return value.replace(old, new)
    if isinstance(value, list):
        return [_replace_owned_reference(item, old, new) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_owned_reference(item, old, new)
            for key, item in value.items()
        }
    return value


def bump_versions(
    agents_dir: Path,
    *,
    write: bool,
    selected_agents: set[str] | None = None,
) -> dict[str, Any]:
    changes: list[dict[str, str]] = []
    for pack_path in sorted(agents_dir.glob("*/agent_pack.json")):
        if selected_agents and pack_path.parent.name not in selected_agents:
            continue
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        contract = pack.get("output_contract") or {}
        old = contract.get("schema_ref")
        match = VERSION_RE.fullmatch(str(old or ""))
        if match is None:
            raise ValueError(f"{pack_path.parent.name}: invalid versioned schema_ref {old!r}")
        new = f"{match.group('prefix')}/v{int(match.group('version')) + 1}"
        pack = _replace_owned_reference(pack, old, new)
        if isinstance(pack.get("integrity"), dict):
            pack["integrity"]["sha256"] = _canonical_pack_sha256(pack)
        changes.append({"agent": pack_path.parent.name, "old": old, "new": new})
        if write:
            pack_path.write_text(
                json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return {"visible_agents": len(changes), "changes": changes, "write": write}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--agent", action="append", dest="agents")
    args = parser.parse_args()
    print(json.dumps(
        bump_versions(
            args.agents_dir.resolve(),
            write=args.write,
            selected_agents=set(args.agents or []),
        ),
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
