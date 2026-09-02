"""Immutable archive contract and filesystem WORM simulator for HSM audit records.

The filesystem implementation is intentionally a CI/development simulator.  It
enforces create-only objects, retention, legal hold and signed chain-head
checkpoints through this API, but a privileged host administrator can still
alter the directory.  Production adapters must map the same contract to a
provider's compliance-mode object lock and independent credentials.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from app.services.soft_hsm_ops_audit import GENESIS_HASH, parse_and_verify


ARCHIVE_SCHEMA = "icoder.software-hsm-audit-archive/v1"
CHECKPOINT_SCHEMA = "icoder.software-hsm-audit-checkpoint/v1"
EXPORT_SCHEMA = "icoder.software-hsm-audit-export/v1"
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_ACCOUNT = re.compile(r"^[0-9]{12}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _sign(value: dict[str, Any], key: bytes | bytearray) -> str:
    digest = hmac.new(bytes(key), _canonical(value), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _safe_root(root: Path) -> Path:
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise RuntimeError("audit archive root must be an existing absolute directory")
    return root


def _record_envelope(
    record: dict[str, Any], *, checkpoint_key: bytes,
    policy: "ArchivePolicy", archived_at: datetime | None = None,
) -> dict[str, Any]:
    sequence = record.get("sequence")
    chain_hash = record.get("chain_hash")
    if (
        not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1
        or not isinstance(chain_hash, str) or re.fullmatch(r"[0-9a-f]{64}", chain_hash) is None
    ):
        raise RuntimeError("audit archive record metadata is invalid")
    timestamp = archived_at or datetime.fromisoformat(record["recorded_at"])
    envelope = {
        "schema": ARCHIVE_SCHEMA, "sequence": sequence, "chain_hash": chain_hash,
        "archived_at": timestamp.isoformat(),
        "retention_until": (timestamp + timedelta(days=policy.retention_days)).isoformat(),
        "legal_hold": policy.legal_hold, "record": record,
    }
    envelope["archive_signature"] = _sign(envelope, checkpoint_key)
    return envelope


def _checkpoint(
    *, sequence: int, chain_hash: str, checkpoint_key: bytes,
    checkpoint_key_id: str, recorded_at: datetime | None = None,
) -> dict[str, Any]:
    unsigned = {
        "schema": CHECKPOINT_SCHEMA, "sequence": sequence, "chain_hash": chain_hash,
        "recorded_at": (recorded_at or datetime.now(UTC)).isoformat(),
        "signing_key_id": checkpoint_key_id,
    }
    return {**unsigned, "signature": _sign(unsigned, checkpoint_key)}


def _verify_envelope(envelope: Any, checkpoint_key: bytes) -> dict[str, Any]:
    if not isinstance(envelope, dict) or envelope.get("schema") != ARCHIVE_SCHEMA:
        raise RuntimeError("audit archive object integrity failed")
    unsigned = {key: value for key, value in envelope.items() if key != "archive_signature"}
    if not hmac.compare_digest(
        envelope.get("archive_signature", ""), _sign(unsigned, checkpoint_key)
    ):
        raise RuntimeError("audit archive object signature verification failed")
    return envelope


def _write_once(path: Path, document: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink() or not path.parent.is_dir():
        raise RuntimeError("audit archive object path is unsafe")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o400)
    except FileExistsError:
        if path.read_bytes() == document:
            return
        raise RuntimeError("immutable audit archive object overwrite rejected") from None
    try:
        os.write(descriptor, document)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(path, 0o400)


@dataclass(frozen=True)
class ArchivePolicy:
    retention_days: int
    legal_hold: bool = False

    def __post_init__(self) -> None:
        if self.retention_days < 1 or self.retention_days > 36500:
            raise RuntimeError("audit archive retention must be between 1 and 36500 days")


class AuditArchive(Protocol):
    """Provider-neutral contract implemented by compliance-mode WORM adapters."""

    def replicate_records(self, records: list[dict[str, Any]]) -> dict[str, Any]: ...

    def verify(
        self, *, verification_keys: dict[str, bytes | bytearray], minimum_sequence: int = 0,
    ) -> dict[str, Any]: ...

    def export_evidence(self) -> bytes: ...

    def uses_checkpoint_key(self, candidate: bytes | bytearray) -> bool: ...


class LocalWormAuditArchive:
    """Create-only local adapter used to exercise the production archive contract."""

    def __init__(
        self, root: Path, *, checkpoint_key: bytes | bytearray,
        checkpoint_key_id: str, policy: ArchivePolicy,
    ) -> None:
        self.root = _safe_root(root)
        if len(checkpoint_key) < 32 or _KEY_ID.fullmatch(checkpoint_key_id) is None:
            raise RuntimeError("audit archive checkpoint signer is invalid")
        self._checkpoint_key = bytes(checkpoint_key)
        self.checkpoint_key_id = checkpoint_key_id
        self.policy = policy

    def uses_checkpoint_key(self, candidate: bytes | bytearray) -> bool:
        return hmac.compare_digest(self._checkpoint_key, bytes(candidate))

    def _object_path(self, sequence: int, chain_hash: str) -> Path:
        return self.root / "objects" / f"{sequence:020d}-{chain_hash}.json"

    def archive_record(self, record: dict[str, Any]) -> dict[str, Any]:
        envelope = _record_envelope(
            record, checkpoint_key=self._checkpoint_key, policy=self.policy,
        )
        sequence = envelope["sequence"]
        chain_hash = envelope["chain_hash"]
        path = self._object_path(sequence, chain_hash)
        if path.exists():
            existing = json.loads(path.read_bytes())
            if existing.get("record") == record:
                return existing
            raise RuntimeError("immutable audit archive object overwrite rejected")
        _write_once(path, _canonical(envelope) + b"\n")
        return envelope

    def write_checkpoint(
        self, *, sequence: int, chain_hash: str, recorded_at: datetime | None = None,
    ) -> dict[str, Any]:
        path = self.root / "checkpoints" / f"{sequence:020d}-{chain_hash}.json"
        if path.exists():
            existing = json.loads(path.read_bytes())
            unsigned = {key: value for key, value in existing.items() if key != "signature"}
            if (
                existing.get("sequence") == sequence
                and existing.get("chain_hash") == chain_hash
                and hmac.compare_digest(existing.get("signature", ""), _sign(unsigned, self._checkpoint_key))
            ):
                return existing
            raise RuntimeError("immutable audit archive checkpoint overwrite rejected")
        signed = _checkpoint(
            sequence=sequence, chain_hash=chain_hash,
            checkpoint_key=self._checkpoint_key, checkpoint_key_id=self.checkpoint_key_id,
            recorded_at=recorded_at,
        )
        _write_once(path, _canonical(signed) + b"\n")
        return signed

    def replicate_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        previous = GENESIS_HASH
        for expected, record in enumerate(records, start=1):
            if record.get("sequence") != expected or record.get("previous_hash") != previous:
                raise RuntimeError("audit archive replication order is invalid")
            self.archive_record(record)
            previous = record["chain_hash"]
        checkpoint = self.write_checkpoint(
            sequence=len(records), chain_hash=previous,
            recorded_at=(datetime.fromisoformat(records[-1]["recorded_at"]) if records else None),
        )
        return {"records": len(records), "head_hash": previous, "checkpoint": checkpoint}

    def _load_objects(self) -> list[dict[str, Any]]:
        object_root = self.root / "objects"
        if not object_root.exists():
            return []
        if object_root.is_symlink() or not object_root.is_dir():
            raise RuntimeError("audit archive object root is unsafe")
        envelopes = []
        for path in sorted(object_root.glob("*.json")):
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("audit archive contains an unsafe object")
            try:
                envelope = json.loads(path.read_bytes())
            except Exception as exc:
                raise RuntimeError("audit archive object is invalid") from exc
            if (
                not isinstance(envelope, dict) or envelope.get("schema") != ARCHIVE_SCHEMA
                or envelope.get("sequence") != envelope.get("record", {}).get("sequence")
                or envelope.get("chain_hash") != envelope.get("record", {}).get("chain_hash")
                or path != self._object_path(envelope["sequence"], envelope["chain_hash"])
            ):
                raise RuntimeError("audit archive object integrity failed")
            _verify_envelope(envelope, self._checkpoint_key)
            envelopes.append(envelope)
        return envelopes

    def verify(
        self, *, verification_keys: dict[str, bytes | bytearray], minimum_sequence: int = 0,
    ) -> dict[str, Any]:
        envelopes = self._load_objects()
        document = b"".join(_canonical(item["record"]) + b"\n" for item in envelopes)
        fallback_id, fallback_key = next(iter(verification_keys.items()))
        records = parse_and_verify(
            document, audit_key=fallback_key, signing_key_id=fallback_id,
            verification_keys=verification_keys, minimum_sequence=minimum_sequence,
        )
        checkpoint_root = self.root / "checkpoints"
        checkpoints = sorted(checkpoint_root.glob("*.json")) if checkpoint_root.exists() else []
        if not checkpoints:
            raise RuntimeError("independent audit archive checkpoint is missing")
        checkpoint = json.loads(checkpoints[-1].read_bytes())
        unsigned = {key: value for key, value in checkpoint.items() if key != "signature"}
        if (
            checkpoint.get("schema") != CHECKPOINT_SCHEMA
            or checkpoint.get("signing_key_id") != self.checkpoint_key_id
            or not hmac.compare_digest(checkpoint.get("signature", ""), _sign(unsigned, self._checkpoint_key))
            or checkpoint.get("sequence") != len(records)
            or checkpoint.get("chain_hash") != (records[-1]["chain_hash"] if records else GENESIS_HASH)
        ):
            raise RuntimeError("independent audit archive checkpoint verification failed")
        return {
            "schema": ARCHIVE_SCHEMA, "status": "passed", "records": len(records),
            "head_hash": checkpoint["chain_hash"], "checkpoint_key_id": self.checkpoint_key_id,
            "signing_key_ids": sorted({record["signing_key_id"] for record in records}),
        }

    def export_evidence(self) -> bytes:
        envelopes = self._load_objects()
        evidence = {
            "schema": EXPORT_SCHEMA,
            "exported_at": datetime.now(UTC).isoformat(),
            "records": [item["record"] for item in envelopes],
        }
        return _canonical(evidence) + b"\n"

    def delete_object(self, *, sequence: int, chain_hash: str, now: datetime | None = None) -> None:
        """Administrative simulator API; production deletion belongs to the WORM provider."""
        path = self._object_path(sequence, chain_hash)
        envelope = json.loads(path.read_bytes())
        unsigned = {key: value for key, value in envelope.items() if key != "archive_signature"}
        if not hmac.compare_digest(
            envelope.get("archive_signature", ""), _sign(unsigned, self._checkpoint_key)
        ):
            raise RuntimeError("audit archive object signature verification failed")
        current = now or datetime.now(UTC)
        if envelope["legal_hold"]:
            raise RuntimeError("audit archive legal hold prevents deletion")
        if current < datetime.fromisoformat(envelope["retention_until"]):
            raise RuntimeError("audit archive retention prevents deletion")
        os.chmod(path, 0o600)
        path.unlink()


class S3ObjectLockAuditArchive:
    """AWS S3 Object Lock adapter using COMPLIANCE retention and SSE-KMS.

    The injected client keeps provider behavior testable without credentials.
    The deployment identity must not have delete, retention-bypass, bucket-policy
    or legal-hold removal permissions.
    """

    def __init__(
        self, client: Any, *, bucket: str, prefix: str, expected_bucket_owner: str,
        kms_key_id: str, checkpoint_key: bytes | bytearray,
        checkpoint_key_id: str, policy: ArchivePolicy,
    ) -> None:
        if _BUCKET.fullmatch(bucket) is None or _ACCOUNT.fullmatch(expected_bucket_owner) is None:
            raise RuntimeError("S3 audit archive bucket identity is invalid")
        normalized_prefix = prefix.strip("/")
        if not normalized_prefix or ".." in normalized_prefix.split("/"):
            raise RuntimeError("S3 audit archive prefix is invalid")
        if (
            re.match(r"^arn:aws(?:-[a-z]+)?:kms:[a-z0-9-]+:[0-9]{12}:key/", kms_key_id)
            is None
            or len(kms_key_id) > 2048
        ):
            raise RuntimeError("S3 audit archive KMS key id is invalid")
        if len(checkpoint_key) < 32 or _KEY_ID.fullmatch(checkpoint_key_id) is None:
            raise RuntimeError("audit archive checkpoint signer is invalid")
        self.client = client
        self.bucket = bucket
        self.prefix = normalized_prefix
        self.expected_bucket_owner = expected_bucket_owner
        self.kms_key_id = kms_key_id
        self._checkpoint_key = bytes(checkpoint_key)
        self.checkpoint_key_id = checkpoint_key_id
        self.policy = policy

    def uses_checkpoint_key(self, candidate: bytes | bytearray) -> bool:
        return hmac.compare_digest(self._checkpoint_key, bytes(candidate))

    def _key(self, category: str, name: str) -> str:
        return f"{self.prefix}/{category}/{name}.json"

    @staticmethod
    def _error_code(exc: Exception) -> str:
        response = getattr(exc, "response", {})
        return str(response.get("Error", {}).get("Code", ""))

    def _get_bytes(self, key: str) -> tuple[bytes, dict[str, Any]]:
        response = self.client.get_object(
            Bucket=self.bucket, Key=key, ExpectedBucketOwner=self.expected_bucket_owner,
        )
        body = response["Body"].read()
        return body, response

    def _verify_remote_protection(
        self, key: str, response: dict[str, Any], *, retention_until: datetime,
        legal_hold: bool,
    ) -> None:
        version_id = response.get("VersionId")
        if not isinstance(version_id, str) or not version_id:
            raise RuntimeError("S3 Object Lock object has no version id")
        head = self.client.head_object(
            Bucket=self.bucket, Key=key, VersionId=version_id,
            ExpectedBucketOwner=self.expected_bucket_owner,
        )
        actual_retention = head.get("ObjectLockRetainUntilDate")
        if (
            head.get("ObjectLockMode") != "COMPLIANCE"
            or not isinstance(actual_retention, datetime) or actual_retention < retention_until
            or head.get("ServerSideEncryption") != "aws:kms"
            or head.get("SSEKMSKeyId") != self.kms_key_id
            or (legal_hold and head.get("ObjectLockLegalHoldStatus") != "ON")
        ):
            raise RuntimeError("S3 Object Lock or SSE-KMS verification failed")

    def _put_once(self, key: str, document: bytes, *, retention_until: datetime) -> str:
        checksum = base64.b64encode(hashlib.sha256(document).digest()).decode("ascii")
        request = {
            "Bucket": self.bucket, "Key": key, "Body": document,
            "ContentType": "application/json", "ChecksumSHA256": checksum,
            "IfNoneMatch": "*", "ObjectLockMode": "COMPLIANCE",
            "ObjectLockRetainUntilDate": retention_until,
            "ServerSideEncryption": "aws:kms", "SSEKMSKeyId": self.kms_key_id,
            "BucketKeyEnabled": True, "ExpectedBucketOwner": self.expected_bucket_owner,
        }
        if self.policy.legal_hold:
            request["ObjectLockLegalHoldStatus"] = "ON"
        try:
            response = self.client.put_object(**request)
        except Exception as exc:
            if self._error_code(exc) not in {"PreconditionFailed", "412"}:
                raise RuntimeError("S3 immutable audit archive write failed") from exc
            existing, response = self._get_bytes(key)
            if existing != document:
                raise RuntimeError("S3 immutable audit archive collision detected") from exc
        version_id = response.get("VersionId")
        if not isinstance(version_id, str) or not version_id:
            raise RuntimeError("S3 Object Lock write did not return a version id")
        self._verify_remote_protection(
            key, {"VersionId": version_id}, retention_until=retention_until,
            legal_hold=self.policy.legal_hold,
        )
        return version_id

    def archive_record(self, record: dict[str, Any]) -> dict[str, Any]:
        envelope = _record_envelope(
            record, checkpoint_key=self._checkpoint_key, policy=self.policy,
        )
        document = _canonical(envelope) + b"\n"
        key = self._key(
            "objects", f'{envelope["sequence"]:020d}-{envelope["chain_hash"]}',
        )
        version_id = self._put_once(
            key, document, retention_until=datetime.fromisoformat(envelope["retention_until"]),
        )
        return {**envelope, "archive_version_id": version_id}

    def write_checkpoint(
        self, *, sequence: int, chain_hash: str, recorded_at: datetime | None = None,
    ) -> dict[str, Any]:
        checkpoint = _checkpoint(
            sequence=sequence, chain_hash=chain_hash, checkpoint_key=self._checkpoint_key,
            checkpoint_key_id=self.checkpoint_key_id, recorded_at=recorded_at,
        )
        document = _canonical(checkpoint) + b"\n"
        self._put_once(
            self._key("checkpoints", f"{sequence:020d}-{chain_hash}"), document,
            retention_until=(
                datetime.fromisoformat(checkpoint["recorded_at"])
                + timedelta(days=self.policy.retention_days)
            ),
        )
        return checkpoint

    def replicate_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        previous = GENESIS_HASH
        for expected, record in enumerate(records, start=1):
            if record.get("sequence") != expected or record.get("previous_hash") != previous:
                raise RuntimeError("audit archive replication order is invalid")
            self.archive_record(record)
            previous = record["chain_hash"]
        checkpoint = self.write_checkpoint(
            sequence=len(records), chain_hash=previous,
            recorded_at=(datetime.fromisoformat(records[-1]["recorded_at"]) if records else None),
        )
        return {"records": len(records), "head_hash": previous, "checkpoint": checkpoint}

    def _list_keys(self, category: str) -> list[str]:
        prefix = f"{self.prefix}/{category}/"
        keys: list[str] = []
        token: str | None = None
        while True:
            request: dict[str, Any] = {
                "Bucket": self.bucket, "Prefix": prefix,
                "ExpectedBucketOwner": self.expected_bucket_owner,
            }
            if token:
                request["ContinuationToken"] = token
            response = self.client.list_objects_v2(**request)
            keys.extend(item["Key"] for item in response.get("Contents", []))
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
            if not token:
                raise RuntimeError("S3 audit archive listing continuation is invalid")
        return sorted(keys)

    def _load_objects(self) -> list[dict[str, Any]]:
        envelopes = []
        for key in self._list_keys("objects"):
            document, response = self._get_bytes(key)
            try:
                envelope = _verify_envelope(json.loads(document), self._checkpoint_key)
            except Exception as exc:
                raise RuntimeError("S3 audit archive object verification failed") from exc
            expected_key = self._key(
                "objects", f'{envelope["sequence"]:020d}-{envelope["chain_hash"]}',
            )
            if key != expected_key:
                raise RuntimeError("S3 audit archive object key mismatch")
            self._verify_remote_protection(
                key, response,
                retention_until=datetime.fromisoformat(envelope["retention_until"]),
                legal_hold=bool(envelope["legal_hold"]),
            )
            envelopes.append(envelope)
        return envelopes

    def verify(
        self, *, verification_keys: dict[str, bytes | bytearray], minimum_sequence: int = 0,
    ) -> dict[str, Any]:
        envelopes = self._load_objects()
        document = b"".join(_canonical(item["record"]) + b"\n" for item in envelopes)
        fallback_id, fallback_key = next(iter(verification_keys.items()))
        records = parse_and_verify(
            document, audit_key=fallback_key, signing_key_id=fallback_id,
            verification_keys=verification_keys, minimum_sequence=minimum_sequence,
        )
        checkpoint_keys = self._list_keys("checkpoints")
        if not checkpoint_keys:
            raise RuntimeError("S3 audit archive checkpoint is missing")
        checkpoint_document, checkpoint_response = self._get_bytes(checkpoint_keys[-1])
        checkpoint = json.loads(checkpoint_document)
        unsigned = {key: value for key, value in checkpoint.items() if key != "signature"}
        if (
            checkpoint.get("signing_key_id") != self.checkpoint_key_id
            or not hmac.compare_digest(checkpoint.get("signature", ""), _sign(unsigned, self._checkpoint_key))
            or checkpoint.get("sequence") != len(records)
            or checkpoint.get("chain_hash") != (records[-1]["chain_hash"] if records else GENESIS_HASH)
        ):
            raise RuntimeError("S3 audit archive checkpoint verification failed")
        self._verify_remote_protection(
            checkpoint_keys[-1], checkpoint_response,
            retention_until=(
                datetime.fromisoformat(checkpoint["recorded_at"])
                + timedelta(days=self.policy.retention_days)
            ),
            legal_hold=self.policy.legal_hold,
        )
        return {
            "schema": ARCHIVE_SCHEMA, "status": "passed", "provider": "aws_s3_object_lock",
            "records": len(records), "head_hash": checkpoint["chain_hash"],
            "checkpoint_key_id": self.checkpoint_key_id,
            "signing_key_ids": sorted({record["signing_key_id"] for record in records}),
        }

    def export_evidence(self) -> bytes:
        return _canonical({
            "schema": EXPORT_SCHEMA, "exported_at": datetime.now(UTC).isoformat(),
            "records": [item["record"] for item in self._load_objects()],
        }) + b"\n"


def archive_from_environment() -> AuditArchive:
    adapter = os.environ.get("ICODER_SOFT_HSM_AUDIT_ARCHIVE_ADAPTER", "").strip()
    if adapter not in {"local_worm_simulator", "aws_s3_object_lock"}:
        raise RuntimeError("a supported immutable software HSM audit archive is required")
    if (
        adapter == "local_worm_simulator"
        and
        os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().lower() == "cloud"
        and os.environ.get("ICODER_ALLOW_LOCAL_WORM_SIMULATOR", "false").strip().lower()
        not in {"1", "true", "yes", "on"}
    ):
        raise RuntimeError("local WORM simulator is forbidden in cloud mode")
    raw_key = os.environ.get("ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY", "").strip()
    key_id = os.environ.get("ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY_ID", "").strip()
    try:
        key = base64.urlsafe_b64decode(raw_key + "=" * (-len(raw_key) % 4))
        retention_days = int(os.environ.get("ICODER_SOFT_HSM_AUDIT_RETENTION_DAYS", "2555"))
    except Exception as exc:
        raise RuntimeError("software HSM audit archive configuration is invalid") from exc
    legal_hold = os.environ.get("ICODER_SOFT_HSM_AUDIT_LEGAL_HOLD", "false").lower() == "true"
    policy = ArchivePolicy(retention_days=retention_days, legal_hold=legal_hold)
    if adapter == "local_worm_simulator":
        root_value = os.environ.get("ICODER_SOFT_HSM_AUDIT_ARCHIVE_ROOT", "").strip()
        return LocalWormAuditArchive(
            Path(root_value), checkpoint_key=key, checkpoint_key_id=key_id, policy=policy,
        )
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for the S3 Object Lock audit archive") from exc
    region = os.environ.get("ICODER_SOFT_HSM_AUDIT_S3_REGION", "").strip()
    if not region:
        raise RuntimeError("S3 audit archive region is required")
    client = boto3.client("s3", region_name=region)
    return S3ObjectLockAuditArchive(
        client,
        bucket=os.environ.get("ICODER_SOFT_HSM_AUDIT_S3_BUCKET", "").strip(),
        prefix=os.environ.get("ICODER_SOFT_HSM_AUDIT_S3_PREFIX", "").strip(),
        expected_bucket_owner=os.environ.get(
            "ICODER_SOFT_HSM_AUDIT_S3_EXPECTED_OWNER", ""
        ).strip(),
        kms_key_id=os.environ.get("ICODER_SOFT_HSM_AUDIT_S3_KMS_KEY_ID", "").strip(),
        checkpoint_key=key, checkpoint_key_id=key_id, policy=policy,
    )


__all__ = [
    "ARCHIVE_SCHEMA", "CHECKPOINT_SCHEMA", "EXPORT_SCHEMA", "ArchivePolicy", "AuditArchive",
    "LocalWormAuditArchive", "S3ObjectLockAuditArchive", "archive_from_environment",
]
