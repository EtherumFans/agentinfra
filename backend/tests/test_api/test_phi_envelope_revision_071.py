import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "071_phi_envelope_plaintext_gate.py"
BACKFILL = ROOT / "scripts" / "backfill_phi_envelopes.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("phi_migration_071", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_071_is_linear_and_covers_complete_wave5_phi_inventory() -> None:
    module = _migration_module()
    assert module.revision == "071"
    assert module.down_revision == "070"
    covered = {
        f"{table}.{column}"
        for mapping in (module.TEXT_COLUMNS, module.JSON_COLUMNS)
        for table, columns in mapping.items()
        for column in columns
    }
    assert len(covered) == 71
    assert {
        "clinical_facts.encrypted_text",
        "clinical_facts.encrypted_evidence_json",
        "guided_documents.encrypted_string_document_json",
        "guided_documents.encrypted_structured_document_json",
        "guided_documents.encrypted_labels_json",
        "guided_documents.encrypted_classic_sections_json",
        "guided_sections.encrypted_definition_json",
        "documents.content",
        "encounters.admission_reason",
        "coding_reviews.report_markdown",
        "cdi_provider_queries.query_text",
    } <= covered
    assert len({
        module._constraint_name(*item.split(".", 1)) for item in covered
    }) == len(covered)


def test_migration_is_a_keyless_fail_closed_gate() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "ICODER_PHI_ENCRYPTION_KEY" not in source
    assert "encrypt_phi" not in source
    assert "refuses plaintext PHI" in source
    assert "_validate_no_plaintext()" in source
    assert "DROP DEFAULT" in source


def test_backfill_inventory_cannot_drift_from_migration() -> None:
    migration = _migration_module()
    spec = importlib.util.spec_from_file_location("phi_backfill_071", BACKFILL)
    assert spec and spec.loader
    backfill = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = backfill
    spec.loader.exec_module(backfill)
    assert backfill.TEXT_COLUMNS == migration.TEXT_COLUMNS
    assert backfill.JSON_COLUMNS == migration.JSON_COLUMNS
