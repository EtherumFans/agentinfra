"""Phase A1A Gate 3.2 — Tenant Read Policy + Quarantine tests.

Charter §8 B coverage:
  - normal tenant read of UNKNOWN     → 404
  - normal tenant read of AMBIGUOUS   → 404
  - normal tenant read of QUARANTINED → 404
  - normal tenant read of MODERN_SYSTEM → 404
  - normal tenant read of NULL classification → 404
  - list / aggregate / usage exclude all four invisibility classes
  - Security Admin role check + audit emit
"""
from __future__ import annotations

from typing import Optional

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, MetaData, String, Table, select

from app.middleware.tenancy_guard import (
    CLASS_LEGACY_AMBIGUOUS,
    CLASS_LEGACY_INFERRED,
    CLASS_LEGACY_VERIFIED,
    CLASS_MODERN_SYSTEM,
)
from app.services.tenant_read_policy import (
    SECURITY_ADMIN_ROLES,
    TENANT_INVISIBLE_CLASSIFICATIONS,
    TENANT_VISIBLE_CLASSIFICATIONS,
    apply_tenant_visibility_filter,
    assert_security_admin_access,
    enforce_tenant_visible_or_404,
    is_tenant_visible,
)


# ── §1 Visibility predicate ─────────────────────────────────────────────


@pytest.mark.parametrize("cls", sorted(TENANT_VISIBLE_CLASSIFICATIONS))
def test_visible_classifications_pass(cls: str):
    assert is_tenant_visible(cls) is True


@pytest.mark.parametrize("cls", sorted(TENANT_INVISIBLE_CLASSIFICATIONS))
def test_invisible_classifications_fail(cls: str):
    assert is_tenant_visible(cls) is False


def test_null_classification_is_invisible():
    """Charter §3.2 §2: NULL classification must NOT be treated as visible."""
    assert is_tenant_visible(None) is False


def test_unknown_string_is_invisible():
    """Defensive: a typo / future classification that isn't in the
    allowlist is invisible (fail-closed)."""
    assert is_tenant_visible("LEGACY_TENANT_KNOWN") is False  # removed by Gate 3.1
    assert is_tenant_visible("Bogus") is False
    assert is_tenant_visible("") is False


# ── §2 Point-read guard: exact 404 without leak ─────────────────────────


@pytest.mark.parametrize("cls", sorted(TENANT_INVISIBLE_CLASSIFICATIONS))
def test_enforce_guard_404_on_invisible(cls: str):
    with pytest.raises(HTTPException) as exc:
        enforce_tenant_visible_or_404(classification=cls, run_id="run-X")
    assert exc.value.status_code == 404
    # Message must NOT leak the run_id or classification.
    detail = exc.value.detail
    assert "run-X" not in str(detail)
    assert cls not in str(detail)


@pytest.mark.parametrize("cls", sorted(TENANT_VISIBLE_CLASSIFICATIONS))
def test_enforce_guard_passes_visible(cls: str):
    # No exception raised.
    enforce_tenant_visible_or_404(classification=cls)


def test_enforce_guard_404_on_null():
    with pytest.raises(HTTPException) as exc:
        enforce_tenant_visible_or_404(classification=None)
    assert exc.value.status_code == 404


# ── §3 List / aggregate filter ─────────────────────────────────────────


def _build_test_table() -> Table:
    md = MetaData()
    return Table(
        "test_rows",
        md,
        Column("id", String(64), primary_key=True),
        Column("tenancy_classification", String(32), nullable=True),
    )


def test_apply_filter_excludes_invisible():
    tbl = _build_test_table()
    stmt = select(tbl.c.id)
    filtered = apply_tenant_visibility_filter(
        stmt, tbl.c.tenancy_classification, also_exclude_null=True,
    )
    # Compile to SQL string and verify the WHERE clause contains every
    # visible classification and excludes NULL.
    sql = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    for cls in TENANT_VISIBLE_CLASSIFICATIONS:
        assert cls in sql
    assert "IS NOT NULL" in sql


def test_apply_filter_optional_null_inclusion():
    """``also_exclude_null=False`` lets callers opt out (rare — only
    when the table genuinely has no classification column and we
    don't want to filter)."""
    tbl = _build_test_table()
    stmt = select(tbl.c.id)
    filtered = apply_tenant_visibility_filter(
        stmt, tbl.c.tenancy_classification, also_exclude_null=False,
    )
    sql = str(filtered.compile(compile_kwargs={"literal_binds": True}))
    assert "IS NOT NULL" not in sql


# ── §4 Security Admin role check ────────────────────────────────────────


class _StubUser:
    def __init__(self, *, user_id: str = "u-admin", role: Optional[str] = None):
        self.id = user_id
        self.role = role


class _StubRole:
    def __init__(self, value: str):
        self.value = value


@pytest.mark.asyncio
async def test_security_admin_allows_platform_security_admin(monkeypatch):
    """User with role ``platform_security_admin`` passes the gate."""
    user = _StubUser(role=_StubRole("platform_security_admin"))

    # Avoid importing system_audit (Gate 3.6 not yet wired) by stubbing
    # the import inside assert_security_admin_access. The function
    # already falls back to logger.warning if system_audit isn't
    # importable, so we just need to ensure no exception is raised.
    await assert_security_admin_access(
        user, db=None,
        action="read_quarantined",
        resource_type="run_history",
        resource_id="run-Q",
        reason="forensic investigation",
    )


@pytest.mark.asyncio
async def test_security_admin_denies_normal_user():
    """User with role ``member`` (a normal tenant user) is denied."""
    user = _StubUser(role=_StubRole("member"))
    with pytest.raises(HTTPException) as exc:
        await assert_security_admin_access(
            user, db=None,
            action="read_quarantined",
            resource_type="run_history",
            resource_id="run-Q",
        )
    assert exc.value.status_code == 403
    assert "Security Admin" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_security_admin_denies_null_role():
    """User with no role at all is denied."""
    user = _StubUser(role=None)
    with pytest.raises(HTTPException) as exc:
        await assert_security_admin_access(
            user, db=None, action="x", resource_type="y",
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_security_admin_denies_org_admin():
    """``admin`` role (tenant-level) must NOT pass — only platform-
    level security roles pass. This is the charter §3.2 "Security
    Admin 路径需要专用权限" requirement: a hospital admin cannot
    reach into another tenant's quarantined data."""
    user = _StubUser(role=_StubRole("admin"))
    with pytest.raises(HTTPException) as exc:
        await assert_security_admin_access(
            user, db=None, action="x", resource_type="y",
        )
    assert exc.value.status_code == 403


def test_security_admin_roles_allowlist_is_restrictive():
    """Only platform-level security roles are in the allowlist."""
    assert "admin" not in SECURITY_ADMIN_ROLES
    assert "member" not in SECURITY_ADMIN_ROLES
    assert "security_admin" in SECURITY_ADMIN_ROLES
    assert "platform_security_admin" in SECURITY_ADMIN_ROLES
