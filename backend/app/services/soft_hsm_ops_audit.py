"""Independent tamper-evident append-only audit chain for software-HSM ops.

The chain is deliberately separate from the application database so key-store
creation and disaster recovery can be audited while PostgreSQL is unavailable.
Deployments should ship the JSONL stream and its head checkpoint to immutable
object storage; local append-only semantics cannot resist a privileged host
administrator deleting the file or its tail.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import stat
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = "icoder.software-hsm-ops-audit/v1"
GENESIS_HASH = "0" * 64
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
_MAX_AUDIT_BYTES = 16 * 1024 * 1024
_RECORD_FIELDS = {
    "schema", "sequence", "event_id", "recorded_at", "event", "payload_hash",
    "previous_hash", "chain_hash", "signature", "signing_algorithm", "signing_key_id",
}
_EVENT_FIELDS = {
    "operation", "phase", "outcome", "key_store_id", "expected_generation",
    "resulting_generation", "active_key_id", "key_states", "error_type",
    "change_ticket",
}
_KEY_STATES = {"active", "decrypt-only", "retired", "revoked"}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode_key(value: str) -> bytearray:
    try:
        padding = "=" * (-len(value) % 4)
        key = bytearray(base64.b64decode(
            (value + padding).encode("ascii"), altchars=b"-_", validate=True,
        ))
    except Exception as exc:
        raise RuntimeError("software HSM operations audit key is not valid base64url") from exc
    if len(key) < 32:
        raise RuntimeError("software HSM operations audit key must contain at least 32 bytes")
    return key


def audit_config_from_environment() -> tuple[Path, bytearray, str]:
    path_value = os.environ.get("ICODER_SOFT_HSM_OPS_AUDIT_PATH", "").strip()
    raw_key = os.environ.get("ICODER_SOFT_HSM_OPS_AUDIT_KEY", "").strip()
    key_id = os.environ.get("ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID", "").strip()
    if not path_value or not Path(path_value).is_absolute():
        raise RuntimeError("absolute ICODER_SOFT_HSM_OPS_AUDIT_PATH is required")
    if not raw_key:
        raise RuntimeError("ICODER_SOFT_HSM_OPS_AUDIT_KEY is required")
    if _KEY_ID.fullmatch(key_id) is None:
        raise RuntimeError("software HSM operations audit key id is invalid")
    return Path(path_value), _decode_key(raw_key), key_id


def audit_minimum_sequence_from_environment() -> int:
    raw = os.environ.get("ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE", "").strip()
    if os.environ.get("ICODER_DEPLOYMENT_MODE", "local").strip().lower() == "cloud" and not raw:
        raise RuntimeError("ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE is required in cloud mode")
    try:
        minimum = int(raw or "0")
    except ValueError as exc:
        raise RuntimeError("software HSM operations audit minimum sequence must be an integer") from exc
    if minimum < 0:
        raise RuntimeError("software HSM operations audit minimum sequence must not be negative")
    return minimum


def key_store_identifier(path: Path) -> str:
    normalized = os.path.normcase(os.path.abspath(path))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _chain_hash(sequence: int, previous_hash: str, payload_hash: str) -> str:
    return hashlib.sha256(_canonical({
        "schema": SCHEMA,
        "sequence": sequence,
        "previous_hash": previous_hash,
        "payload_hash": payload_hash,
    })).hexdigest()


def _sign(chain_hash: str, audit_key: bytes | bytearray) -> str:
    digest = hmac.new(bytes(audit_key), chain_hash.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _validate_event(event: dict[str, Any]) -> None:
    if set(event) != _EVENT_FIELDS:
        raise ValueError("software HSM audit event structure is invalid")
    if event["operation"] not in {"create", "rotate", "set-state", "rotate-bootstrap"}:
        raise ValueError("software HSM audit operation is invalid")
    if event["phase"] not in {"started", "completed", "failed"}:
        raise ValueError("software HSM audit phase is invalid")
    if event["outcome"] not in {"pending", "success", "failure"}:
        raise ValueError("software HSM audit outcome is invalid")
    expected_outcome = {
        "started": "pending", "completed": "success", "failed": "failure",
    }[event["phase"]]
    if event["outcome"] != expected_outcome:
        raise ValueError("software HSM audit phase and outcome are inconsistent")
    if not isinstance(event["key_store_id"], str) or not re.fullmatch(
        r"[0-9a-f]{24}", event["key_store_id"]
    ):
        raise ValueError("software HSM audit key store id is invalid")
    for field in ("expected_generation", "resulting_generation"):
        value = event[field]
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            raise ValueError("software HSM audit generation is invalid")
    if event["active_key_id"] is not None and (
        not isinstance(event["active_key_id"], str)
        or _KEY_ID.fullmatch(event["active_key_id"]) is None
    ):
        raise ValueError("software HSM audit active key id is invalid")
    states = event["key_states"]
    if not isinstance(states, dict) or len(states) > 64 or any(
        not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None
        or state not in _KEY_STATES for key_id, state in states.items()
    ):
        raise ValueError("software HSM audit key states are invalid")
    for field in ("error_type", "change_ticket"):
        value = event[field]
        if value is not None and (
            not isinstance(value, str) or not value or len(value) > 128
            or any(character in value for character in "\r\n")
        ):
            raise ValueError(f"software HSM audit {field} is invalid")
    if (event["phase"] == "failed") != (event["error_type"] is not None):
        raise ValueError("software HSM audit error type is inconsistent")


def create_record(
    event: dict[str, Any], *, sequence: int, previous_hash: str,
    audit_key: bytes | bytearray, signing_key_id: str,
) -> dict[str, Any]:
    if sequence < 1 or len(previous_hash) != 64:
        raise ValueError("invalid software HSM audit chain position")
    if _KEY_ID.fullmatch(signing_key_id) is None:
        raise ValueError("invalid software HSM audit signing key id")
    if len(audit_key) < 32:
        raise ValueError("software HSM audit signing key is too short")
    _validate_event(event)
    event_id = uuid.uuid4().hex
    recorded_at = datetime.now(UTC).isoformat()
    payload_hash = hashlib.sha256(_canonical({
        "event_id": event_id, "recorded_at": recorded_at, "event": event,
    })).hexdigest()
    chain_hash = _chain_hash(sequence, previous_hash, payload_hash)
    return {
        "schema": SCHEMA,
        "sequence": sequence,
        "event_id": event_id,
        "recorded_at": recorded_at,
        "event": event,
        "payload_hash": payload_hash,
        "previous_hash": previous_hash,
        "chain_hash": chain_hash,
        "signature": _sign(chain_hash, audit_key),
        "signing_algorithm": "HMAC-SHA256",
        "signing_key_id": signing_key_id,
    }


def parse_and_verify(
    document: bytes, *, audit_key: bytes | bytearray, signing_key_id: str,
    minimum_sequence: int = 0,
) -> list[dict[str, Any]]:
    if _KEY_ID.fullmatch(signing_key_id) is None or len(audit_key) < 32:
        raise ValueError("invalid software HSM audit verifier")
    if len(document) > _MAX_AUDIT_BYTES:
        raise RuntimeError("software HSM operations audit exceeds maximum size")
    records: list[dict[str, Any]] = []
    previous_hash = GENESIS_HASH
    for expected_sequence, line in enumerate(document.splitlines(), start=1):
        if not line.strip():
            raise RuntimeError("software HSM operations audit contains an empty record")
        try:
            record = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
        except Exception as exc:
            raise RuntimeError("software HSM operations audit contains invalid JSON") from exc
        if not isinstance(record, dict) or set(record) != _RECORD_FIELDS:
            raise RuntimeError("software HSM operations audit record structure is invalid")
        event = record["event"]
        if not isinstance(event, dict) or record["schema"] != SCHEMA:
            raise RuntimeError("software HSM operations audit payload is invalid")
        try:
            recorded_at = datetime.fromisoformat(record["recorded_at"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("software HSM operations audit record metadata is invalid") from exc
        if (
            not isinstance(record["sequence"], int)
            or isinstance(record["sequence"], bool)
            or not isinstance(record["event_id"], str)
            or re.fullmatch(r"[0-9a-f]{32}", record["event_id"]) is None
            or recorded_at.tzinfo is None
            or any(
                not isinstance(record[field], str)
                or re.fullmatch(r"[0-9a-f]{64}", record[field]) is None
                for field in ("payload_hash", "previous_hash", "chain_hash")
            )
            or not isinstance(record["signature"], str)
        ):
            raise RuntimeError("software HSM operations audit record metadata is invalid")
        try:
            _validate_event(event)
        except ValueError as exc:
            raise RuntimeError("software HSM operations audit payload is invalid") from exc
        payload_hash = hashlib.sha256(_canonical({
            "event_id": record["event_id"],
            "recorded_at": record["recorded_at"],
            "event": event,
        })).hexdigest()
        chain_hash = _chain_hash(expected_sequence, previous_hash, payload_hash)
        if (
            record["sequence"] != expected_sequence
            or record["previous_hash"] != previous_hash
            or record["payload_hash"] != payload_hash
            or record["chain_hash"] != chain_hash
            or record["signing_algorithm"] != "HMAC-SHA256"
            or record["signing_key_id"] != signing_key_id
            or not hmac.compare_digest(record["signature"], _sign(chain_hash, audit_key))
        ):
            raise RuntimeError("software HSM operations audit verification failed")
        records.append(record)
        previous_hash = chain_hash
    if len(records) < minimum_sequence:
        raise RuntimeError("software HSM operations audit tail rollback detected")
    return records


def _lock_file(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        # Lock one byte. New files receive a sentinel before this helper.
        msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_EX)


def _unlock_file(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(descriptor, fcntl.LOCK_UN)


def _read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = _MAX_AUDIT_BYTES + 1
    while remaining:
        chunk = os.read(descriptor, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    document = b"".join(chunks)
    if len(document) > _MAX_AUDIT_BYTES:
        raise RuntimeError("software HSM operations audit exceeds maximum size")
    return document


def _validate_file_stat(file_stat: os.stat_result) -> None:
    if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > _MAX_AUDIT_BYTES:
        raise RuntimeError("software HSM operations audit file is invalid")
    if os.name != "nt" and (
        file_stat.st_uid != os.geteuid() or stat.S_IMODE(file_stat.st_mode) & 0o077
    ):
        raise RuntimeError("software HSM operations audit ownership or permissions are unsafe")


def append_event(
    path: Path, event: dict[str, Any], *, audit_key: bytes | bytearray,
    signing_key_id: str, minimum_sequence: int = 0,
) -> dict[str, Any]:
    if not path.is_absolute() or not path.parent.is_dir():
        raise RuntimeError("software HSM operations audit path must be absolute with an existing parent")
    if path.is_symlink():
        raise RuntimeError("software HSM operations audit must not be a symbolic link")
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError("software HSM operations audit cannot be opened safely") from exc
    locked = False
    try:
        os.chmod(path, 0o600)
        file_stat = os.fstat(descriptor)
        _validate_file_stat(file_stat)
        if file_stat.st_size == 0 and os.name == "nt":
            os.write(descriptor, b"\n")
            os.fsync(descriptor)
        _lock_file(descriptor)
        locked = True
        current = _read_descriptor(descriptor)
        if os.name == "nt" and current == b"\n":
            current = b""
            os.ftruncate(descriptor, 0)
        records = parse_and_verify(
            current, audit_key=audit_key, signing_key_id=signing_key_id,
            minimum_sequence=minimum_sequence,
        )
        previous_hash = records[-1]["chain_hash"] if records else GENESIS_HASH
        record = create_record(
            event, sequence=len(records) + 1, previous_hash=previous_hash,
            audit_key=audit_key, signing_key_id=signing_key_id,
        )
        encoded = _canonical(record) + b"\n"
        if len(current) + len(encoded) > _MAX_AUDIT_BYTES:
            raise RuntimeError("software HSM operations audit capacity is exhausted")
        os.lseek(descriptor, 0, os.SEEK_END)
        os.write(descriptor, encoded)
        os.fsync(descriptor)
        return record
    finally:
        if locked:
            _unlock_file(descriptor)
        os.close(descriptor)


def verify_audit_file(
    path: Path, *, audit_key: bytes | bytearray, signing_key_id: str,
    minimum_sequence: int = 0,
) -> dict[str, Any]:
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError("software HSM operations audit path is unsafe")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError("software HSM operations audit cannot be read") from exc
    try:
        _validate_file_stat(os.fstat(descriptor))
        document = _read_descriptor(descriptor)
    finally:
        os.close(descriptor)
    records = parse_and_verify(
        document, audit_key=audit_key, signing_key_id=signing_key_id,
        minimum_sequence=minimum_sequence,
    )
    return {
        "schema": SCHEMA,
        "status": "passed",
        "records": len(records),
        "head_sequence": len(records),
        "head_hash": records[-1]["chain_hash"] if records else GENESIS_HASH,
        "signing_key_id": signing_key_id,
    }


def zeroize(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0


__all__ = [
    "GENESIS_HASH", "SCHEMA", "append_event", "audit_config_from_environment",
    "audit_minimum_sequence_from_environment", "create_record", "key_store_identifier",
    "parse_and_verify", "verify_audit_file", "zeroize",
]
