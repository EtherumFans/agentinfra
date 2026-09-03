"""Regression coverage for PostgreSQL-compatible ORM Boolean defaults."""

from sqlalchemy import Boolean
from sqlalchemy.dialects import postgresql

import app.models  # noqa: F401 - register every ORM table on Base.metadata
from app.database import Base


def test_boolean_server_defaults_are_not_numeric_for_postgresql() -> None:
    """PostgreSQL rejects integer DEFAULT expressions on Boolean columns."""

    invalid: list[str] = []
    checked = 0
    dialect = postgresql.dialect()

    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if not isinstance(column.type, Boolean) or column.server_default is None:
                continue
            checked += 1
            rendered = str(column.server_default.arg.compile(dialect=dialect)).strip().lower()
            if rendered in {"0", "1"}:
                invalid.append(f"{table.name}.{column.name}=DEFAULT {rendered}")

    assert checked > 0, "model registry exposed no Boolean server defaults"
    assert invalid == [], (
        "PostgreSQL Boolean columns must use false()/true(), not numeric defaults: "
        + ", ".join(invalid)
    )
