"""Declare top-level JSON field types for Hub-visible Agent Pack outputs.

The command derives an initial declaration only from contract-complete,
checked-in example outputs.  It fails on absent, null, unsupported, or
conflicting example types.  Dry-run is the default; ``--write`` updates the
Pack and refreshes its canonical integrity digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENTS_DIR = REPO_ROOT / "backend" / "official_agents"
INTEGRITY_EXCLUDED_FIELDS = {
    "integrity",
    "downloads",
    "published_at",
    "loaded_at",
    "_pack_mtime_iso",
}


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite number is not valid JSON contract data")
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    raise ValueError(f"unsupported example value type: {type(value).__name__}")


def _canonical_pack_sha256(pack: dict[str, Any]) -> str:
    clean = {
        key: value
        for key, value in pack.items()
        if key not in INTEGRITY_EXCLUDED_FIELDS
    }
    payload = json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _derive_field_types(pack: dict[str, Any]) -> dict[str, str]:
    contract = pack.get("output_contract") or {}
    required = contract.get("required_fields") or []
    optional = contract.get("optional_fields") or []
    examples = [
        example
        for example in (pack.get("example_outputs") or [])
        if isinstance(example, dict)
        and all(field in example for field in required)
    ]
    if not required or not examples:
        raise ValueError("requires fields and a contract-complete example_output")

    declarations: dict[str, str] = {}
    for field in required + optional:
        observed = {
            _json_type(example[field]) for example in examples if field in example
        }
        if not observed:
            raise ValueError(f"field {field!r} has no checked-in example value")
        if observed == {"integer", "number"}:
            observed = {"number"}
        if len(observed) != 1:
            raise ValueError(
                f"field {field!r} has conflicting example types {sorted(observed)}"
            )
        declarations[field] = observed.pop()
    return declarations


def sync_field_types(agents_dir: Path, *, write: bool) -> dict[str, Any]:
    visible = 0
    changed: list[str] = []
    for pack_path in sorted(agents_dir.glob("*/agent_pack.json")):
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        visible += 1
        agent_id = str(pack.get("agent_ref") or "").rsplit("/", 1)[-1].split("@", 1)[0]
        declared = _derive_field_types(pack)
        contract = pack.get("output_contract")
        if not isinstance(contract, dict):
            raise ValueError(f"{agent_id}: output_contract must be an object")
        types_changed = contract.get("field_types") != declared
        contract["field_types"] = declared
        expected_sha = _canonical_pack_sha256(pack)
        integrity_changed = bool(
            isinstance(pack.get("integrity"), dict)
            and pack["integrity"].get("sha256") != expected_sha
        )
        if not types_changed and not integrity_changed:
            continue
        changed.append(agent_id)
        if write:
            if isinstance(pack.get("integrity"), dict):
                pack["integrity"]["sha256"] = expected_sha
            pack_path.write_text(
                json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return {"visible_agents": visible, "changed_agents": changed, "write": write}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(json.dumps(
        sync_field_types(args.agents_dir.resolve(), write=args.write),
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
