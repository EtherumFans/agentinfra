"""Enforce immutable, versioned Agent Pack public output contracts.

The registry is append-only. A new ``schema_ref`` can be registered with
``--write``; an existing reference can never be rewritten by this command.
Any contract change therefore requires a new versioned schema reference.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENTS_DIR = REPO_ROOT / "backend" / "official_agents"
DEFAULT_REGISTRY = DEFAULT_AGENTS_DIR / "output_contract_registry.json"
VERSIONED_REF = re.compile(r"^icoder/[A-Za-z][A-Za-z0-9_-]*/v[1-9][0-9]*$")


def _agent_id(pack: dict[str, Any], path: Path) -> str:
    return str(pack.get("agent_ref") or path.parent.name).rsplit("/", 1)[-1].split("@", 1)[0]


def _public_contract(pack: dict[str, Any]) -> dict[str, Any]:
    contract = pack.get("output_contract") or {}
    public = {
        "required_fields": list(contract.get("required_fields") or []),
        "optional_fields": list(contract.get("optional_fields") or []),
        "field_types": dict(contract.get("field_types") or {}),
        "field_schemas": dict(contract.get("field_schemas") or {}),
    }
    if "field_relations" in contract:
        public["field_relations"] = list(contract.get("field_relations") or [])
    if "evidence_bindings" in contract:
        public["evidence_bindings"] = list(contract.get("evidence_bindings") or [])
    if "cross_agent_relations" in contract:
        public["cross_agent_relations"] = list(
            contract.get("cross_agent_relations") or []
        )
    return public


def validate(
    agents_dir: Path,
    registry_path: Path,
    *,
    write: bool,
) -> dict[str, Any]:
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    else:
        registry = {
            "schema_version": "icoder.agent-output-contract-registry/v1",
            "contracts": {},
        }
    registered = registry.get("contracts")
    if not isinstance(registered, dict):
        raise ValueError("registry.contracts must be an object")

    current: dict[str, dict[str, Any]] = {}
    invalid_refs: list[str] = []
    duplicate_refs: list[str] = []
    for path in sorted(agents_dir.glob("*/agent_pack.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        agent_id = _agent_id(pack, path)
        ref = str((pack.get("output_contract") or {}).get("schema_ref") or "")
        if not VERSIONED_REF.fullmatch(ref):
            invalid_refs.append(f"{agent_id}:{ref}")
            continue
        if ref in current:
            duplicate_refs.append(ref)
            continue
        current[ref] = {"agent_id": agent_id, "contract": _public_contract(pack)}

    changed_refs = sorted(
        ref for ref, item in current.items()
        if ref in registered and registered[ref].get("contract") != item["contract"]
    )
    new_refs = sorted(set(current) - set(registered))
    if write and not changed_refs and not invalid_refs and not duplicate_refs:
        for ref in new_refs:
            registered[ref] = {
                **current[ref],
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }
        registry_path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    passed = not invalid_refs and not duplicate_refs and not changed_refs and (
        write or not new_refs
    )
    return {
        "passed": passed,
        "visible_contracts": len(current),
        "registered_contracts": len(registered),
        "new_refs": new_refs,
        "changed_refs": changed_refs,
        "invalid_refs": invalid_refs,
        "duplicate_refs": duplicate_refs,
        "write": write,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    report = validate(
        args.agents_dir.resolve(),
        args.registry.resolve(),
        write=args.write,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
