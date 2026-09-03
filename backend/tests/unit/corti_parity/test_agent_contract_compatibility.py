from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "corti_parity" / "validate_agent_contract_compatibility.py"
SPEC = importlib.util.spec_from_file_location("agent_contract_compatibility", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _pack(ref: str, *, field_type: str = "string") -> dict:
    return {
        "agent_ref": "icoder/example@1.0.0",
        "manifest": {"hidden_from_hub": False},
        "output_contract": {
            "schema_ref": ref,
            "required_fields": ["result"],
            "optional_fields": [],
            "field_types": {"result": field_type},
            "field_schemas": {},
        },
    }


def test_registry_is_append_only_and_requires_version_bump(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    pack_dir = agents / "example"
    pack_dir.mkdir(parents=True)
    pack_path = pack_dir / "agent_pack.json"
    registry = agents / "output_contract_registry.json"
    pack_path.write_text(json.dumps(_pack("icoder/ExampleOutput/v1")), encoding="utf-8")

    initialized = MODULE.validate(agents, registry, write=True)
    assert initialized["passed"] is True
    assert initialized["new_refs"] == ["icoder/ExampleOutput/v1"]

    pack_path.write_text(
        json.dumps(_pack("icoder/ExampleOutput/v1", field_type="array")),
        encoding="utf-8",
    )
    changed = MODULE.validate(agents, registry, write=True)
    assert changed["passed"] is False
    assert changed["changed_refs"] == ["icoder/ExampleOutput/v1"]
    assert json.loads(registry.read_text(encoding="utf-8"))["contracts"][
        "icoder/ExampleOutput/v1"
    ]["contract"]["field_types"]["result"] == "string"

    pack_path.write_text(
        json.dumps(_pack("icoder/ExampleOutput/v2", field_type="array")),
        encoding="utf-8",
    )
    bumped = MODULE.validate(agents, registry, write=True)
    assert bumped["passed"] is True
    assert bumped["new_refs"] == ["icoder/ExampleOutput/v2"]


def test_unregistered_or_unversioned_contract_fails_check_mode(tmp_path: Path) -> None:
    agents = tmp_path / "agents"
    pack_dir = agents / "example"
    pack_dir.mkdir(parents=True)
    pack_path = pack_dir / "agent_pack.json"
    registry = agents / "output_contract_registry.json"
    pack_path.write_text(json.dumps(_pack("icoder/ExampleOutput/v1")), encoding="utf-8")

    unregistered = MODULE.validate(agents, registry, write=False)
    assert unregistered["passed"] is False
    assert unregistered["new_refs"] == ["icoder/ExampleOutput/v1"]

    pack_path.write_text(json.dumps(_pack("ExampleOutput")), encoding="utf-8")
    invalid = MODULE.validate(agents, registry, write=False)
    assert invalid["passed"] is False
    assert invalid["invalid_refs"] == ["example:ExampleOutput"]
