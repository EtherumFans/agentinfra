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
        sequence = record.get("sequence")
        chain_hash = record.get("chain_hash")
        if (
            not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1
            or not isinstance(chain_hash, str) or re.fullmatch(r"[0-9a-f]{64}", chain_hash) is None
        ):
            raise RuntimeError("audit archive record metadata is invalid")
        path = self._object_path(sequence, chain_hash)
        if path.exists():
            existing = json.loads(path.read_bytes())
            if existing.get("record") == record:
                return existing
            raise RuntimeError("immutable audit archive object overwrite rejected")
        archived_at = datetime.now(UTC)
        envelope = {
            "schema": ARCHIVE_SCHEMA,
            "sequence": sequence,
            "chain_hash": chain_hash,
            "archived_at": archived_at.isoformat(),
            "retention_until": (archived_at + timedelta(days=self.policy.retention_days)).isoformat(),
            "legal_hold": self.policy.legal_hold,
            "record": record,
        }
        envelope["archive_signature"] = _sign(envelope, self._checkpoint_key)
        _write_once(path, _canonical(envelope) + b"\n")
        return envelope

    def write_checkpoint(self, *, sequence: int, chain_hash: str) -> dict[str, Any]:
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
        checkpoint = {
            "schema": CHECKPOINT_SCHEMA,
            "sequence": sequence,
            "chain_hash": chain_hash,
            "recorded_at": datetime.now(UTC).isoformat(),
            "signing_key_id": self.checkpoint_key_id,
        }
        signed = {**checkpoint, "signature": _sign(checkpoint, self._checkpoint_key)}
        _write_once(path, _canonical(signed) + b"\n")
        return signed

    def replicate_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        previous = GENESIS_HASH
        for expected, record in enumerate(records, start=1):
            if record.get("sequence") != expected or record.get("previous_hash") != previous:
                raise RuntimeError("audit archive replication order is invalid")
            self.archive_record(record)
            previous = record["chain_hash"]
        checkpoint = self.write_checkpoint(sequence=len(records), chain_hash=previous)
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
            unsigned = {key: value for key, value in envelope.items() if key != "archive_signature"}
            if not hmac.compare_digest(
                envelope.get("archive_signature", ""), _sign(unsigned, self._checkpoint_key)
            ):
                raise RuntimeError("audit archive object signature verification failed")
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


def archive_from_environment() -> LocalWormAuditArchive:
    adapter = os.environ.get("ICODER_SOFT_HSM_AUDIT_ARCHIVE_ADAPTER", "").strip()
    if adapter != "local_worm_simulator":
        raise RuntimeError("a supported immutable software HSM audit archive is required")
    if (
        os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().lower() == "cloud"
        and os.environ.get("ICODER_ALLOW_LOCAL_WORM_SIMULATOR", "false").strip().lower()
        not in {"1", "true", "yes", "on"}
    ):
        raise RuntimeError("local WORM simulator is forbidden in cloud mode")
    root_value = os.environ.get("ICODER_SOFT_HSM_AUDIT_ARCHIVE_ROOT", "").strip()
    raw_key = os.environ.get("ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY", "").strip()
    key_id = os.environ.get("ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY_ID", "").strip()
    try:
        key = base64.urlsafe_b64decode(raw_key + "=" * (-len(raw_key) % 4))
        retention_days = int(os.environ.get("ICODER_SOFT_HSM_AUDIT_RETENTION_DAYS", "2555"))
    except Exception as exc:
        raise RuntimeError("software HSM audit archive configuration is invalid") from exc
    legal_hold = os.environ.get("ICODER_SOFT_HSM_AUDIT_LEGAL_HOLD", "false").lower() == "true"
    return LocalWormAuditArchive(
        Path(root_value), checkpoint_key=key, checkpoint_key_id=key_id,
        policy=ArchivePolicy(retention_days=retention_days, legal_hold=legal_hold),
    )


__all__ = [
    "ARCHIVE_SCHEMA", "CHECKPOINT_SCHEMA", "EXPORT_SCHEMA", "ArchivePolicy", "AuditArchive",
    "LocalWormAuditArchive", "archive_from_environment",
]
