from __future__ import annotations

from dataclasses import MISSING

import pytest

from scripts.provision_postgresql_roles import RoleSpec, normalize_postgresql_url


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("postgresql+asyncpg://admin:secret@db:5432/icoder", "postgresql://admin:secret@db:5432/icoder"),
        ("postgresql+psycopg://admin@db/icoder", "postgresql://admin@db/icoder"),
        ("postgres://admin@db/icoder", "postgres://admin@db/icoder"),
    ),
)
def test_normalize_postgresql_url_accepts_supported_driver_forms(source: str, expected: str) -> None:
    assert normalize_postgresql_url(source) == expected


def test_normalize_postgresql_url_rejects_non_postgresql() -> None:
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        normalize_postgresql_url("sqlite:///data.db")


def test_role_spec_requires_separate_runtime_identity() -> None:
    with pytest.raises(ValueError, match="must be distinct"):
        RoleSpec(migration_role="shared", app_role="shared", schema="public").validate()


def test_role_spec_does_not_supply_product_role_name_defaults() -> None:
    fields = RoleSpec.__dataclass_fields__
    assert fields["migration_role"].default is MISSING
    assert fields["app_role"].default is MISSING
