from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.corti_parity.sync_agent_pack_field_types import sync_field_types


def _write_pack(root: Path, *, examples: list[dict]) -> Path:
    path = root / "sample" / "agent_pack.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "agent_ref": "icoder/sample@1.0.0",
        "manifest": {"hidden_from_hub": False},
        "output_contract": {
            "schema_ref": "icoder/Sample/v1",
            "required_fields": ["summary", "issues", "score", "review"],
        },
        "example_outputs": examples,
        "integrity": {"sha256": "0" * 64},
    }), encoding="utf-8")
    return path


def test_sync_declares_types_refreshes_integrity_and_is_idempotent(tmp_path: Path) -> None:
    path = _write_pack(tmp_path, examples=[{
        "summary": "review",
        "issues": [],
        "score": 0.5,
        "review": True,
    }])

    dry = sync_field_types(tmp_path, write=False)
    assert dry["changed_agents"] == ["sample"]
    written = sync_field_types(tmp_path, write=True)
    assert written["changed_agents"] == ["sample"]

    pack = json.loads(path.read_text(encoding="utf-8"))
    assert pack["output_contract"]["field_types"] == {
        "summary": "string",
        "issues": "array",
        "score": "number",
        "review": "boolean",
    }
    assert pack["integrity"]["sha256"] != "0" * 64
    assert sync_field_types(tmp_path, write=False)["changed_agents"] == []


def test_sync_rejects_conflicting_example_types(tmp_path: Path) -> None:
    _write_pack(tmp_path, examples=[
        {"summary": "review", "issues": [], "score": 1, "review": True},
        {"summary": [], "issues": [], "score": 0.5, "review": True},
    ])

    with pytest.raises(ValueError, match="conflicting example types"):
        sync_field_types(tmp_path, write=False)


def test_sync_rejects_non_finite_json_number(tmp_path: Path) -> None:
    _write_pack(tmp_path, examples=[{
        "summary": "review",
        "issues": [],
        "score": float("nan"),
        "review": True,
    }])

    with pytest.raises(ValueError, match="non-finite number"):
        sync_field_types(tmp_path, write=False)
