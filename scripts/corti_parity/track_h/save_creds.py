"""Save Corti credentials from argv to .corti_creds.json.

Usage: python save_creds.py <supabase_jwt> <corti_jwt>
"""
import json, sys
from pathlib import Path

if len(sys.argv) != 3:
    print("Usage: save_creds.py <supabase_jwt> <corti_jwt>", file=sys.stderr)
    sys.exit(2)
Path("scripts/corti_parity/track_h/.corti_creds.json").write_text(
    json.dumps({"supabase_jwt": sys.argv[1], "corti_jwt": sys.argv[2]}, indent=2),
    encoding="utf-8",
)
print("OK: wrote scripts/corti_parity/track_h/.corti_creds.json")
