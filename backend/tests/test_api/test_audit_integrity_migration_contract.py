import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "070_audit_integrity_archive.py"


def test_revision_070_is_linear_after_wave5() -> None:
    spec = importlib.util.spec_from_file_location("audit_migration_070", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "070"
    assert module.down_revision == "069"


def test_archive_contract_is_append_only_and_tenant_scoped() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    required = (
        "audit_integrity_archive",
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "icoder.current_organization_id",
        "trg_audit_archive_immutable",
        "BEFORE UPDATE OR DELETE",
        "icoder_append_audit_archive",
        "pg_advisory_xact_lock",
        "uq_audit_archive_stream_sequence",
        "audit archive source does not exist or tenant mismatches",
    )
    for marker in required:
        assert marker in source


def test_archive_survives_hot_audit_retention() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    create_section = source.split("if op.get_bind().dialect.name", 1)[0]
    assert "ForeignKeyConstraint([\"audit_log_id\"]" not in create_section

