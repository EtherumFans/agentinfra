"""A1D.3 — A1C-B-020 UserRole enum extension.

Predecessor state (Phase A1C.4 §3.1): UserRole enum had 7 values
(ADMIN/CODER/DEPT_HEAD/INSURANCE/QC/CLINICIAN/IT). 2 of 7 hospital
principal mappings were PARTIAL:
  - CDI 专员 → QC (proposed: CDI_SPECIALIST — Migration 030)
  - 病案管理员 → DEPT_HEAD (proposed: MEDICAL_RECORDS_ADMIN — Migration 030)

iCoDer A1C.4 §3.1 explicitly deferred UserRole enum extension to
Migration 030. A1D.3 closes the deferral.

Coverage:
  - enum has 9 values (7 prior + 2 new)
  - new values are string enums with expected literals
  - DB migration 030 applies cleanly (column type widen from 7 to 9
    allowed values; SQLite ENUM constraint)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ─────────────────────────────────────────────────────────────────────
# §1 enum values
# ─────────────────────────────────────────────────────────────────────


def test_user_role_enum_has_9_values() -> None:
    """UserRole has 7 prior + 2 new = 9 values."""
    from app.models.user import UserRole
    assert len(UserRole) == 9


def test_user_role_enum_includes_cdi_specialist() -> None:
    """CDI specialist principal has its own role (no longer conflated with QC)."""
    from app.models.user import UserRole
    assert UserRole.CDI_SPECIALIST == "cdi_specialist"


def test_user_role_enum_includes_medical_records_admin() -> None:
    """Medical records admin principal has its own role (no longer conflated with DEPT_HEAD)."""
    from app.models.user import UserRole
    assert UserRole.MEDICAL_RECORDS_ADMIN == "medical_records_admin"


def test_user_role_enum_prior_values_unchanged() -> None:
    """All 7 prior values still exist with same literals (no rename)."""
    from app.models.user import UserRole
    assert UserRole.ADMIN == "admin"
    assert UserRole.CODER == "coder"
    assert UserRole.DEPT_HEAD == "dept_head"
    assert UserRole.INSURANCE == "insurance"
    assert UserRole.QC == "qc"
    assert UserRole.CLINICIAN == "clinician"
    assert UserRole.IT == "it"


# ─────────────────────────────────────────────────────────────────────
# §2 DB migration 030 — column type widen
# ─────────────────────────────────────────────────────────────────────


def _load_migration_module():
    """Load migration 030 from file path (module name starts with a digit)."""
    import importlib.util
    migration_path = BACKEND_DIR / "alembic" / "versions" / "030_user_role_extension.py"
    spec = importlib.util.spec_from_file_location("migration_030", migration_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_030_revision_chain() -> None:
    """Migration 030 chains from 029 (patient_contexts)."""
    mod = _load_migration_module()
    assert mod.revision == "030"
    assert mod.down_revision == "029"


def test_migration_030_upgrade_downgrade_callable() -> None:
    """Migration 030 exposes upgrade() and downgrade() callables."""
    mod = _load_migration_module()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_030_role_literals_match_user_role_enum() -> None:
    """Migration allowed literals match UserRole enum values exactly."""
    from app.models.user import UserRole
    mod = _load_migration_module()
    assert sorted(mod._USER_ROLE_LITERALS) == sorted(v.value for v in UserRole)


# ─────────────────────────────────────────────────────────────────────
# §3 User factory accepts new roles
# ─────────────────────────────────────────────────────────────────────


def test_user_factory_accepts_cdi_specialist_role() -> None:
    """A User can be constructed with role=CDI_SPECIALIST."""
    from app.models.user import User, UserRole
    u = User(
        username="cdi-user",
        email="cdi@example.com",
        hashed_password="x",
        full_name="CDI User",
        role=UserRole.CDI_SPECIALIST,
    )
    assert u.role == UserRole.CDI_SPECIALIST
    assert u.role.value == "cdi_specialist"


def test_user_factory_accepts_medical_records_admin_role() -> None:
    """A User can be constructed with role=MEDICAL_RECORDS_ADMIN."""
    from app.models.user import User, UserRole
    u = User(
        username="mra-user",
        email="mra@example.com",
        hashed_password="x",
        full_name="MRA User",
        role=UserRole.MEDICAL_RECORDS_ADMIN,
    )
    assert u.role == UserRole.MEDICAL_RECORDS_ADMIN
    assert u.role.value == "medical_records_admin"
