"""Regression coverage for PostgreSQL-compatible ORM server defaults."""

import re

from sqlalchemy import Boolean, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause

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
            expression = column.server_default.arg
            rendered = str(
                expression.compile(dialect=dialect)
                if hasattr(expression, "compile")
                else expression
            ).strip().lower()
            if rendered in {"0", "1"}:
                invalid.append(f"{table.name}.{column.name}=DEFAULT {rendered}")

    assert checked > 0, "model registry exposed no Boolean server defaults"
    assert invalid == [], (
        "PostgreSQL Boolean columns must use false()/true(), not numeric defaults: "
        + ", ".join(invalid)
    )


def test_string_server_defaults_are_not_bare_sql_identifiers() -> None:
    """A bare ``text('ok')`` default is a column reference in PostgreSQL."""

    invalid: list[str] = []
    checked = 0

    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if not isinstance(column.type, String) or column.server_default is None:
                continue
            checked += 1
            expression = column.server_default.arg
            if isinstance(expression, TextClause) and re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", expression.text.strip()
            ):
                invalid.append(
                    f"{table.name}.{column.name}=DEFAULT {expression.text.strip()}"
                )

    assert checked > 0, "model registry exposed no String server defaults"
    assert invalid == [], (
        "PostgreSQL string defaults must be quoted literals, not bare SQL identifiers: "
        + ", ".join(invalid)
    )
