"""CLI wrapper for the schema drift checker.

Usage:
    python scripts/check_schema_drift.py [--db-url URL] [--json]

Exit codes:
    0 — no drift (ORM matches DB)
    1 — drift found (divergences reported)
    2 — error (couldn't connect to DB, couldn't import models, etc.)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `app.*` importable when run as a script from backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check ORM/DB schema drift")
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLAlchemy DB URL. Defaults to ICODER_DB_URL env var or sqlite:///data/icoder.db",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable text",
    )
    args = parser.parse_args()

    import os
    db_url = args.db_url or os.environ.get("ICODER_DB_URL") or "sqlite:///data/icoder.db"

    try:
        from app.services.schema_drift_service import check_drift
        report = check_drift(db_url)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.total == 0 else 1

    # Human-readable
    if report.total == 0:
        print(f"OK — 0 divergences across {report.tables_checked} tables / {report.columns_checked} columns")
        return 0

    print(f"DRIFT — {report.total} divergences across {report.tables_checked} tables:")
    by_type = report.by_type
    for t, n in sorted(by_type.items()):
        print(f"  {t}: {n}")
    print()
    for d in report.divergences:
        print(f"  [{d.type}] {d.table}.{d.column}")
        if d.orm_value is not None:
            print(f"    ORM: {d.orm_value}")
        if d.db_value is not None:
            print(f"    DB:  {d.db_value}")
        if d.detail:
            print(f"    {d.detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
