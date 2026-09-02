"""Export minimum-necessary evidence from the immutable HSM audit archive."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.soft_hsm_audit_archive import archive_from_environment  # noqa: E402


def _write_new(path: Path, document: bytes) -> None:
    if not path.is_absolute() or not path.parent.is_dir() or path.is_symlink():
        raise RuntimeError("audit export path must be absolute with an existing parent")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, document)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    document = archive_from_environment().export_evidence()
    _write_new(args.output, document)
    print(f'{{"status":"passed","bytes":{len(document)}}}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
