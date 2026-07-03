"""Export FastAPI OpenAPI schema to docs/openapi/openapi.json.

The committed schema is the source of truth for the frontend API contract test
(frontend/src/services/__tests__/apiContract.test.ts), which asserts every
hardcoded path in frontend/src/services/*.ts exists in the OpenAPI schema.

Usage:
    python scripts/export_openapi.py
    python scripts/export_openapi.py --check  # exit 1 if committed schema is stale
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `app.*` importable when run as a script from backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

# Output path — committed to repo, used by frontend contract test
_OUTPUT_PATH = _BACKEND_DIR.parent / "docs" / "openapi" / "openapi.json"


def export_schema() -> dict:
    """Import the FastAPI app and dump its OpenAPI schema."""
    from app.main import app
    schema = app.openapi()
    return schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI schema")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if committed schema is stale (for CI use)",
    )
    parser.add_argument(
        "--output",
        default=str(_OUTPUT_PATH),
        help=f"Output path (default: {_OUTPUT_PATH})",
    )
    args = parser.parse_args()

    schema = export_schema()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    new_text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not output_path.exists():
            print(f"FAIL: {output_path} does not exist. Run without --check first.")
            return 1
        existing = output_path.read_text(encoding="utf-8")
        if existing != new_text:
            print(f"FAIL: {output_path} is stale. Re-run without --check to update.")
            return 1
        print(f"OK: {output_path} is up to date")
        return 0

    output_path.write_text(new_text, encoding="utf-8")
    print(f"Wrote {len(new_text)} bytes to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
