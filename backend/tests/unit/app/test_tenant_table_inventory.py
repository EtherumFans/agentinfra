"""Static integrity checks for the governed tenant-table inventory."""

from __future__ import annotations

import json
import re
from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_INVENTORY_PATH = _BACKEND_ROOT / "docs" / "security" / "tenant_table_inventory.json"
_ORM_TABLE_PATTERN = re.compile(r'__tablename__\s*=\s*["\']([^"\']+)["\']')

_EXISTING_FORCE_RLS = {
    "contexts",
    "conversation_memories",
    "memory_consents",
    "patient_contexts",
    "run_history",
    "run_trace_events",
    "transactions",
}

_BATCH_2_FIRST_WAVE = {
    "context_messages",
    "context_task_refs",
    "context_artifact_refs",
    "original_input_audit",
    "a2a_task_executions",
    "a2a_task_events",
    "a2a_task_artifacts",
    "a2a_artifact_objects",
    "a2a_artifact_download_grants",
}


def _inventory() -> dict:
    return json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))


def _orm_table_names() -> set[str]:
    names: set[str] = set()
    for path in (_BACKEND_ROOT / "app").rglob("*.py"):
        names.update(_ORM_TABLE_PATTERN.findall(path.read_text(encoding="utf-8")))
    return names


def test_inventory_is_complete_unique_and_sorted() -> None:
    inventory = _inventory()
    rows = inventory["tables"]
    names = [row["name"] for row in rows]

    assert len(names) == inventory["catalog_union_count"] == 83
    assert len(set(names)) == len(names)
    assert names == sorted(names)
    assert set(names) == _orm_table_names() | {"alembic_version"}


def test_inventory_declares_schema_drift_explicitly() -> None:
    rows = {row["name"]: row for row in _inventory()["tables"]}

    assert {name for name, row in rows.items() if row["schema_presence"] == "orm_only"} == {
        "agent_accounts"
    }
    assert {
        name for name, row in rows.items() if row["schema_presence"] == "database_only"
    } == {"alembic_version"}
    assert sum(row["schema_presence"] != "orm_only" for row in rows.values()) == 82
    assert sum(row["schema_presence"] != "database_only" for row in rows.values()) == 82


def test_inventory_summary_is_derived_from_table_rows() -> None:
    inventory = _inventory()
    database_rows = [
        row for row in inventory["tables"] if row["schema_presence"] != "orm_only"
    ]
    summary = inventory["summary"]

    assert summary["database_tables_with_organization_id"] == sum(
        row["organization_id"] in {"required", "nullable"} for row in database_rows
    )
    assert summary["organization_id_not_null"] == sum(
        row["organization_id"] == "required" for row in database_rows
    )
    assert summary["organization_id_nullable"] == sum(
        row["organization_id"] == "nullable" for row in database_rows
    )
    assert summary["force_rls_enforced"] == sum(
        row["rls"] == "force" for row in database_rows
    )
    assert summary["tenant_tables_without_organization_id"] == sum(
        row["scope"] == "tenant_indirect" for row in database_rows
    )
    assert summary["platform_or_global_tables"] == sum(
        row["scope"] in {"platform_control", "schema_metadata"}
        for row in database_rows
    )
    assert summary["orm_only_schema_drift"] == sum(
        row["schema_presence"] == "orm_only" for row in inventory["tables"]
    )


def test_inventory_release_waves_match_the_approved_scope() -> None:
    inventory = _inventory()
    rows = {row["name"]: row for row in inventory["tables"]}

    assert set(inventory["existing_force_rls_tables"]) == _EXISTING_FORCE_RLS
    assert {name for name, row in rows.items() if row["rls"] == "force"} == (
        _EXISTING_FORCE_RLS
    )
    assert set(inventory["batch_2_first_wave_tables"]) == _BATCH_2_FIRST_WAVE
    assert {name for name, row in rows.items() if row["wave"] == "batch2_wave1"} == (
        _BATCH_2_FIRST_WAVE
    )


def test_every_tenant_surface_has_resolution_sensitivity_and_migration_state() -> None:
    allowed_scopes = {
        "tenant_direct",
        "tenant_indirect",
        "tenant_legacy_nullable",
        "hybrid_catalog",
        "platform_control",
        "schema_metadata",
    }
    allowed_presence = {"database_and_orm", "database_only", "orm_only"}

    for row in _inventory()["tables"]:
        assert row["scope"] in allowed_scopes
        assert row["schema_presence"] in allowed_presence
        assert row["tenant_resolution"]
        assert row["organization_id"]
        assert row["rls"]
        assert row["sensitivity"]
        assert row["wave"]
        if row["scope"].startswith("tenant") or row["scope"] == "hybrid_catalog":
            assert row["wave"] not in {"platform_exempt", ""}
