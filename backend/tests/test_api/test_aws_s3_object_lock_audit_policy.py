from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT.parent / "deploy" / "security" / "aws-s3-object-lock-audit-writer-policy.template.json"


def test_audit_writer_policy_is_prefix_scoped_and_cannot_delete_or_bypass() -> None:
    document = json.loads(POLICY.read_text(encoding="utf-8"))
    statements = {item["Sid"]: item for item in document["Statement"]}
    writer = statements["CreateComplianceLockedAuditObjects"]
    assert writer["Condition"]["StringEquals"]["s3:x-amz-object-lock-mode"] == "COMPLIANCE"
    assert writer["Condition"]["StringEquals"]["s3:x-amz-server-side-encryption"] == "aws:kms"
    assert "s3:PutObject" in writer["Action"]
    deny = statements["NeverDeleteOrBypassAuditRetention"]
    assert deny["Effect"] == "Deny"
    assert {
        "s3:BypassGovernanceRetention", "s3:DeleteObject", "s3:DeleteObjectVersion",
        "s3:PutBucketPolicy", "s3:PutBucketObjectLockConfiguration",
    }.issubset(set(deny["Action"]))
    assert "s3:PutObjectLegalHold" not in POLICY.read_text(encoding="utf-8")
