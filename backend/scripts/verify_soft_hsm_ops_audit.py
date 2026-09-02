"""Verify the independent software-HSM operations audit chain."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.soft_hsm_ops_audit import (  # noqa: E402
    audit_config_from_environment,
    audit_minimum_sequence_from_environment,
    audit_verification_keys_from_environment,
    verify_audit_file,
    zeroize,
)
from app.services.soft_hsm_audit_archive import archive_from_environment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--minimum-sequence", type=int,
        default=None,
    )
    parser.add_argument("--verify-archive", action="store_true")
    args = parser.parse_args()
    minimum_sequence = (
        args.minimum_sequence if args.minimum_sequence is not None
        else audit_minimum_sequence_from_environment()
    )
    if minimum_sequence < 0:
        raise RuntimeError("minimum audit sequence must not be negative")
    path, audit_key, signing_key_id = audit_config_from_environment()
    verification_keys = audit_verification_keys_from_environment()
    try:
        report = verify_audit_file(
            path, audit_key=audit_key, signing_key_id=signing_key_id,
            minimum_sequence=minimum_sequence, verification_keys=verification_keys,
        )
        if args.verify_archive:
            report["archive"] = archive_from_environment().verify(
                verification_keys=verification_keys, minimum_sequence=minimum_sequence,
            )
    finally:
        zeroize(audit_key)
        for key in verification_keys.values():
            zeroize(key)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
