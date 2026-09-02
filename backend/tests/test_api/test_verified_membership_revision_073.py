from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "073_verified_membership_bootstrap.py"


def _module():
    spec = importlib.util.spec_from_file_location("membership_migration_073", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_073_is_linear_and_minimum_disclosure() -> None:
    module = _module()
    source = MIGRATION.read_text(encoding="utf-8")
    assert module.revision == "073"
    assert module.down_revision == "072"
    assert "RETURNS boolean" in source
    assert "LANGUAGE plpgsql VOLATILE" in source
    assert "SECURITY DEFINER" in source
    assert "SET search_path = pg_catalog, public" in source
    assert "JOIN public.organizations" in source
    assert "o.is_active IS TRUE" in source
    assert "previous_tenant" in source
    assert "coalesce(previous_tenant, '')" in source
    assert "icoder_oauth_credential_is_active" in source
    assert "t.expires_at > clock_timestamp()" in source
    assert "t.is_revoked IS FALSE" in source
    assert "RETURNS text" not in source
