"""Verify S3 Object Lock, writer identity and cross-region replication controls."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.soft_hsm_audit_archive import (  # noqa: E402
    S3ObjectLockAuditArchive,
    archive_from_environment,
)


def main() -> int:
    import boto3

    archive = archive_from_environment()
    if not isinstance(archive, S3ObjectLockAuditArchive):
        raise RuntimeError("S3 Object Lock archive adapter is required")
    region = os.environ.get("ICODER_SOFT_HSM_AUDIT_S3_REGION", "").strip()
    report = archive.verify_control_plane(
        sts_client=boto3.client("sts", region_name=region),
        expected_caller_arn=os.environ.get(
            "ICODER_SOFT_HSM_AUDIT_S3_EXPECTED_WRITER_ARN", ""
        ).strip(),
        replica_bucket_arn=os.environ.get(
            "ICODER_SOFT_HSM_AUDIT_S3_REPLICA_BUCKET_ARN", ""
        ).strip(),
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
