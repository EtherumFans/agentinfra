"""Schema drift checker — compares ORM model declarations to the live DB schema.

Surfaces the class of bugs that cycle 24's alembic audit missed:
- ORM declares a column that no migration added (column missing in DB)
- DB has a column that ORM doesn't declare (column missing in ORM)
- nullable mismatch (ORM says NOT NULL, DB says nullable, or vice versa)
- server_default mismatch (DB has DEFAULT, ORM doesn't, or values differ)
- type mismatch (String length, Integer vs Boolean, etc.)

The check is read-only — it inspects the DB via sqlalchemy.inspect(engine)
and the ORM via sqlalchemy.inspect(Model).mapped_collection.

Usage (programmatic):
    from app.services.schema_drift_service import check_drift
    report = check_drift("sqlite:///data/icoder.db")
    if report.divergences:
        for d in report.divergences:
            print(d)
        sys.exit(1)

Usage (CLI):
    python scripts/check_schema_drift.py --db-url sqlite:///data/icoder.db
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, inspect


@dataclass
class Divergence:
    table: str
    column: str
    type: str  # "missing_in_db" | "missing_in_orm" | "nullable_mismatch" | "server_default_mismatch" | "type_mismatch"
    orm_value: Any = None
    db_value: Any = None
    detail: str = ""


@dataclass
class DriftReport:
    divergences: list[Divergence] = field(default_factory=list)
    tables_checked: int = 0
    columns_checked: int = 0

    @property
    def total(self) -> int:
        return len(self.divergences)

    @property
    def by_type(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.divergences:
            out[d.type] = out.get(d.type, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {
            "divergences": [
                {
                    "table": d.table,
                    "column": d.column,
                    "type": d.type,
                    "orm_value": str(d.orm_value),
                    "db_value": str(d.db_value),
                    "detail": d.detail,
                }
                for d in self.divergences
            ],
            "summary": {
                "total": self.total,
                "by_type": self.by_type,
                "tables_checked": self.tables_checked,
                "columns_checked": self.columns_checked,
            },
        }


def _normalize_server_default(value: Any) -> str | None:
    """Normalize a server_default value to a comparable canonical string.

    SQLAlchemy represents server_default differently depending on whether
    it came from an ORM declaration (sa.text("0") or "0" string or func.now())
    or from the DB introspection (a SQL expression string like "0" or
    "CURRENT_TIMESTAMP"). Normalize both to a stripped, lowercased string
    with surrounding quotes/parens removed.

    Semantic-equivalent defaults are unified:
      now() / CURRENT_TIMESTAMP / current_timestamp → "current_timestamp"
      0 / '0' / "0" → "0"
      '' / "" → ""
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    # Strip surrounding quotes
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1]
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    # Strip surrounding parens (SQLite wraps defaults in parens sometimes)
    while s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    # Unify timestamp defaults
    if s in ("now()", "current_timestamp", "current_date", "current_time"):
        return "current_timestamp" if "timestamp" in s or s == "now()" else s
    # Unify boolean/text defaults that are numeric strings
    if s in ("0", "1"):
        return s
    return s


def _normalize_type(col_type: Any) -> str:
    """Normalize a SQLAlchemy column type to a comparable string.

    e.g. VARCHAR(20) → "varchar(20)", INTEGER → "integer", BOOLEAN → "boolean".
    """
    s = str(col_type).lower()
    # Collapse "varchar(20)" variants
    s = re.sub(r"varchar\((\d+)\)", r"varchar(\1)", s)
    return s


def check_drift(db_url: str, orm_models: list[type] | None = None) -> DriftReport:
    """Compare ORM declarations to the live DB schema.

    Args:
        db_url: SQLAlchemy DB URL (e.g. "sqlite:///data/icoder.db")
        orm_models: List of ORM model classes to check. If None, imports
                    all models from app.models.* (relies on Base.metadata).

    Returns:
        DriftReport with any divergences found.
    """
    # Import Base + all models so metadata is populated
    from app.database import Base
    if orm_models is None:
        # Force-load all model modules so Base.metadata.tables is populated
        import app.models  # noqa: F401 — side effect: registers all models
        orm_models = list(Base.metadata.tables.keys())

    engine = create_engine(db_url)
    db_inspector = inspect(engine)
    db_tables = set(db_inspector.get_table_names())

    report = DriftReport()

    # Iterate over ORM-declared tables
    for table_name, table_obj in Base.metadata.tables.items():
        report.tables_checked += 1
        orm_columns = table_obj.columns

        if table_name not in db_tables:
            for col in orm_columns:
                report.divergences.append(Divergence(
                    table=table_name,
                    column=col.name,
                    type="missing_in_db",
                    orm_value=str(col.type),
                    db_value=None,
                    detail=f"Table '{table_name}' not in DB but declared in ORM",
                ))
            continue

        db_columns = {c["name"]: c for c in db_inspector.get_columns(table_name)}

        # Check each ORM-declared column exists in DB with matching attributes
        for col in orm_columns:
            report.columns_checked += 1
            if col.name not in db_columns:
                report.divergences.append(Divergence(
                    table=table_name,
                    column=col.name,
                    type="missing_in_db",
                    orm_value=str(col.type),
                    db_value=None,
                ))
                continue

            db_col = db_columns[col.name]

            # nullable mismatch
            orm_nullable = bool(col.nullable)
            db_nullable = bool(db_col.get("nullable", True))
            if orm_nullable != db_nullable:
                report.divergences.append(Divergence(
                    table=table_name,
                    column=col.name,
                    type="nullable_mismatch",
                    orm_value=f"nullable={orm_nullable}",
                    db_value=f"nullable={db_nullable}",
                ))

            # server_default mismatch
            orm_default = _normalize_server_default(col.server_default.arg if col.server_default else None)
            db_default = _normalize_server_default(db_col.get("default"))
            if orm_default != db_default:
                # Special-case: ORM may omit server_default when DB has one
                # (this is the drift we want to surface)
                report.divergences.append(Divergence(
                    table=table_name,
                    column=col.name,
                    type="server_default_mismatch",
                    orm_value=orm_default,
                    db_value=db_default,
                ))

            # type mismatch (lenient — only flag gross mismatches)
            orm_type = _normalize_type(col.type)
            db_type = _normalize_type(db_col["type"])
            if orm_type != db_type:
                report.divergences.append(Divergence(
                    table=table_name,
                    column=col.name,
                    type="type_mismatch",
                    orm_value=orm_type,
                    db_value=db_type,
                ))

        # Check for DB columns that ORM doesn't declare
        orm_col_names = {c.name for c in orm_columns}
        for db_col_name in db_columns:
            if db_col_name not in orm_col_names:
                report.divergences.append(Divergence(
                    table=table_name,
                    column=db_col_name,
                    type="missing_in_orm",
                    orm_value=None,
                    db_value=str(db_columns[db_col_name]["type"]),
                ))

    engine.dispose()
    return report


__all__ = ["check_drift", "DriftReport", "Divergence"]
