"""Reconcile immutable HSM audit records and emit monitoring-ready JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.soft_hsm_audit_archive import archive_from_environment  # noqa: E402
from app.services.soft_hsm_audit_reconcile import reconcile_audit_archive  # noqa: E402
from app.services.soft_hsm_ops_audit import (  # noqa: E402
    audit_config_from_environment,
    audit_minimum_sequence_from_environment,
    audit_verification_keys_from_environment,
    zeroize,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-pending-seconds", type=int, default=900)
    args = parser.parse_args()
    path, audit_key, signing_key_id = audit_config_from_environment()
    verification_keys = audit_verification_keys_from_environment()
    try:
        report = reconcile_audit_archive(
            path, audit_key=audit_key, signing_key_id=signing_key_id,
            verification_keys=verification_keys, archive=archive_from_environment(),
            minimum_sequence=audit_minimum_sequence_from_environment(),
            max_pending_seconds=args.max_pending_seconds,
        )
    finally:
        zeroize(audit_key)
        for key in verification_keys.values():
            zeroize(key)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
