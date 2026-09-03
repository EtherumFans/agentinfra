from __future__ import annotations

import base64
import hashlib
import io
from datetime import UTC, datetime

import pytest

from app.services.soft_hsm_audit_archive import (
    ArchivePolicy,
    S3ObjectLockAuditArchive,
    archive_from_environment,
)
from app.services.soft_hsm_ops_audit import append_event, key_store_identifier


class _S3Error(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class _FakeS3:
    def __init__(self, *, deny_put: bool = False):
        self.objects: dict[str, dict] = {}
        self.put_requests: list[dict] = []
        self.deny_put = deny_put

    def put_object(self, **request):
        self.put_requests.append(request)
        if self.deny_put:
            raise _S3Error("AccessDenied")
        key = request["Key"]
        if key in self.objects:
            raise _S3Error("PreconditionFailed")
        body = request["Body"]
        assert request["IfNoneMatch"] == "*"
        assert request["ObjectLockMode"] == "COMPLIANCE"
        assert request["ServerSideEncryption"] == "aws:kms"
        assert request["ChecksumSHA256"] == base64.b64encode(hashlib.sha256(body).digest()).decode()
        version = f"version-{len(self.objects) + 1}"
        self.objects[key] = {"body": body, "request": request, "version": version}
        return {"VersionId": version}

    def get_object(self, **request):
        item = self.objects[request["Key"]]
        return {"Body": io.BytesIO(item["body"]), "VersionId": item["version"]}

    def head_object(self, **request):
        item = self.objects[request["Key"]]
        source = item["request"]
        assert request["VersionId"] == item["version"]
        return {
            "ObjectLockMode": source["ObjectLockMode"],
            "ObjectLockRetainUntilDate": source["ObjectLockRetainUntilDate"],
            "ObjectLockLegalHoldStatus": source["ObjectLockLegalHoldStatus"],
            "ServerSideEncryption": source["ServerSideEncryption"],
            "SSEKMSKeyId": source["SSEKMSKeyId"],
        }

    def list_objects_v2(self, **request):
        keys = sorted(key for key in self.objects if key.startswith(request["Prefix"]))
        return {"Contents": [{"Key": key} for key in keys], "IsTruncated": False}

    def head_bucket(self, **request):
        return {}

    def get_bucket_versioning(self, **request):
        return {"Status": "Enabled"}

    def get_object_lock_configuration(self, **request):
        return {"ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled",
            "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 2555}},
        }}

    def get_bucket_replication(self, **request):
        return {"ReplicationConfiguration": {"Rules": [{
            "Status": "Enabled",
            "Destination": {"Bucket": "arn:aws:s3:::icoder-audit-replica"},
        }]}}


class _FakeSts:
    def get_caller_identity(self):
        return {"Arn": "arn:aws:sts::123456789012:assumed-role/audit-writer/release"}


def _event(path, phase="started", outcome="pending") -> dict:
    return {
        "operation": "rotate", "phase": phase, "outcome": outcome,
        "key_store_id": key_store_identifier(path), "expected_generation": 1,
        "resulting_generation": 2 if phase == "completed" else None,
        "active_key_id": "kek-v2" if phase == "completed" else None,
        "key_states": (
            {"kek-v1": "decrypt-only", "kek-v2": "active"}
            if phase == "completed" else {}
        ),
        "error_type": None, "change_ticket": "SEC-7101",
        "operator_identity": "release-controller", "deployment_environment": "production",
        "release_version": "release-2026.09.02",
    }


def _archive(client):
    return S3ObjectLockAuditArchive(
        client, bucket="icoder-audit-prod", prefix="software-hsm/v1",
        expected_bucket_owner="123456789012",
        kms_key_id="arn:aws:kms:ap-east-1:123456789012:key/test",
        checkpoint_key=b"independent-checkpoint-signing-key!",
        checkpoint_key_id="checkpoint-v1",
        policy=ArchivePolicy(retention_days=2555, legal_hold=True),
    )


def test_s3_object_lock_compliance_write_verify_and_idempotency(tmp_path) -> None:
    journal = (tmp_path / "ops.jsonl").resolve()
    audit_key = b"independent-audit-signing-key-32!"
    first = append_event(journal, _event(journal), audit_key=audit_key, signing_key_id="audit-v1")
    second = append_event(
        journal, _event(journal, "completed", "success"),
        audit_key=audit_key, signing_key_id="audit-v1",
    )
    client = _FakeS3()
    archive = _archive(client)
    result = archive.replicate_records([first, second])
    assert result["records"] == 2
    assert archive.verify(verification_keys={"audit-v1": audit_key}, minimum_sequence=2) == {
        "schema": "icoder.software-hsm-audit-archive/v1", "status": "passed",
        "provider": "aws_s3_object_lock", "records": 2,
        "head_hash": second["chain_hash"], "checkpoint_key_id": "checkpoint-v1",
        "signing_key_ids": ["audit-v1"],
    }
    archive.replicate_records([first, second])
    assert len(client.objects) == 3
    assert all(
        request["ExpectedBucketOwner"] == "123456789012"
        and request["ObjectLockLegalHoldStatus"] == "ON"
        and request["ObjectLockRetainUntilDate"] > datetime.now(UTC)
        for request in client.put_requests
    )


def test_s3_permission_failure_is_fail_closed() -> None:
    archive = _archive(_FakeS3(deny_put=True))
    record = {
        "sequence": 1, "chain_hash": "a" * 64,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    with pytest.raises(RuntimeError, match="write failed"):
        archive.archive_record(record)


def test_s3_verify_rejects_retention_or_encryption_drift(tmp_path) -> None:
    journal = (tmp_path / "ops.jsonl").resolve()
    audit_key = b"independent-audit-signing-key-32!"
    record = append_event(
        journal, _event(journal), audit_key=audit_key, signing_key_id="audit-v1",
    )
    client = _FakeS3()
    archive = _archive(client)
    archive.replicate_records([record])
    object_key = next(key for key in client.objects if "/objects/" in key)
    client.objects[object_key]["request"]["ObjectLockMode"] = "GOVERNANCE"
    with pytest.raises(RuntimeError, match="Object Lock"):
        archive.verify(verification_keys={"audit-v1": audit_key}, minimum_sequence=1)


def test_s3_adapter_rejects_unpinned_owner_and_unsafe_prefix() -> None:
    kwargs = {
        "client": _FakeS3(), "bucket": "icoder-audit-prod", "prefix": "../escape",
        "expected_bucket_owner": "not-an-account", "kms_key_id": "key",
        "checkpoint_key": b"independent-checkpoint-signing-key!",
        "checkpoint_key_id": "checkpoint-v1", "policy": ArchivePolicy(retention_days=30),
    }
    with pytest.raises(RuntimeError, match="bucket identity"):
        S3ObjectLockAuditArchive(**kwargs)


def test_cloud_environment_builds_real_s3_adapter(monkeypatch) -> None:
    import boto3

    client = _FakeS3()
    monkeypatch.setattr(boto3, "client", lambda service, region_name: client)
    settings = {
        "ICODER_DEPLOYMENT_MODE": "cloud",
        "ICODER_SOFT_HSM_AUDIT_ARCHIVE_ADAPTER": "aws_s3_object_lock",
        "ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY": base64.urlsafe_b64encode(
            b"independent-checkpoint-signing-key!"
        ).decode(),
        "ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY_ID": "checkpoint-v1",
        "ICODER_SOFT_HSM_AUDIT_S3_REGION": "ap-east-1",
        "ICODER_SOFT_HSM_AUDIT_S3_BUCKET": "icoder-audit-prod",
        "ICODER_SOFT_HSM_AUDIT_S3_PREFIX": "software-hsm/v1",
        "ICODER_SOFT_HSM_AUDIT_S3_EXPECTED_OWNER": "123456789012",
        "ICODER_SOFT_HSM_AUDIT_S3_KMS_KEY_ID": (
            "arn:aws:kms:ap-east-1:123456789012:key/test"
        ),
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    archive = archive_from_environment()
    assert isinstance(archive, S3ObjectLockAuditArchive)
    assert archive.client is client


def test_s3_control_plane_requires_compliance_lock_and_replication() -> None:
    archive = _archive(_FakeS3())
    report = archive.verify_control_plane(
        sts_client=_FakeSts(),
        expected_caller_arn="arn:aws:sts::123456789012:assumed-role/audit-writer/release",
        replica_bucket_arn="arn:aws:s3:::icoder-audit-replica",
    )
    assert report["status"] == "passed"
    assert report["default_retention_days"] == 2555
    assert report["replication_rules"] == 1
