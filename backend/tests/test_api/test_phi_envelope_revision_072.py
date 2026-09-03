import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "072_soft_hsm_v2_envelopes.py"


def _module():
    spec = importlib.util.spec_from_file_location("phi_migration_072", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_072_is_linear_and_dual_envelope() -> None:
    module = _module()
    assert module.revision == "072"
    assert module.down_revision == "071"
    assert "gAAAAA" in module.V1_PATTERN
    assert "v2:" in module.V2_PATTERN


def test_downgrade_requires_reverse_rotation() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "refuses downgrade while HSM v2 PHI remains" in source
    assert "current_organization_id" in source
    assert "exactly 71" in source
