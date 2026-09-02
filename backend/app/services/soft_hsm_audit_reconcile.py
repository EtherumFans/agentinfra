"""Reconcile the local HSM operations spool with its immutable authority."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.soft_hsm_audit_archive import AuditArchive
from app.services.soft_hsm_ops_audit import parse_and_verify, read_audit_document


def _pending_operations(
    records: list[dict[str, Any]], *, now: datetime, max_age_seconds: int,
) -> list[dict[str, Any]]:
    if max_age_seconds < 0:
        raise RuntimeError("audit pending-operation threshold must not be negative")
    pending: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        event = record["event"]
        identity = (
            event["key_store_id"], event["operation"],
            event["expected_generation"], event["change_ticket"],
        )
        if event["phase"] == "started":
            pending.setdefault(identity, []).append(record)
        else:
            candidates = pending.get(identity, [])
            if candidates:
                candidates.pop(0)
    result = []
    for candidates in pending.values():
        for record in candidates:
            age = max(0, int((now - datetime.fromisoformat(record["recorded_at"])).total_seconds()))
            if age >= max_age_seconds:
                result.append({
                    "sequence": record["sequence"], "age_seconds": age,
                    "operation": record["event"]["operation"],
                    "key_store_id": record["event"]["key_store_id"],
                    "change_ticket": record["event"]["change_ticket"],
                })
    return sorted(result, key=lambda item: item["sequence"])


def reconcile_audit_archive(
    audit_path: Path, *, audit_key: bytes | bytearray, signing_key_id: str,
    verification_keys: dict[str, bytes | bytearray], archive: AuditArchive,
    minimum_sequence: int = 0, max_pending_seconds: int = 900,
    now: datetime | None = None,
) -> dict[str, Any]:
    document = read_audit_document(audit_path)
    records = parse_and_verify(
        document, audit_key=audit_key, signing_key_id=signing_key_id,
        verification_keys=verification_keys, minimum_sequence=minimum_sequence,
    )
    local_count = len(records)
    local_head = records[-1]["chain_hash"] if records else "0" * 64
    repaired = False
    try:
        before = archive.verify(verification_keys=verification_keys, minimum_sequence=0)
    except RuntimeError:
        # Replication is safe and create-only.  Genuine tamper/collision still
        # fails during the write or mandatory post-replication verification.
        before = {"records": 0, "head_hash": "0" * 64}
    archive_count = int(before["records"])
    if archive_count > local_count:
        raise RuntimeError("immutable audit archive is ahead of local spool; restore is required")
    if archive_count == local_count and before["head_hash"] != local_head:
        raise RuntimeError("local and immutable audit archive heads diverged")
    lag_before = local_count - archive_count
    if lag_before:
        archive.replicate_records(records)
        repaired = True
    after = archive.verify(
        verification_keys=verification_keys, minimum_sequence=local_count,
    )
    if after["records"] != local_count or after["head_hash"] != local_head:
        raise RuntimeError("immutable audit archive reconciliation did not converge")
    pending = _pending_operations(
        records, now=now or datetime.now(UTC), max_age_seconds=max_pending_seconds,
    )
    alerts = []
    if pending:
        alerts.append("HSM_AUDIT_STARTED_WITHOUT_TERMINAL")
    return {
        "schema": "icoder.software-hsm-audit-reconcile/v1",
        "status": "attention" if alerts else "passed",
        "local_records": local_count, "archive_records": after["records"],
        "checkpoint_lag_before": lag_before, "checkpoint_lag_after": 0,
        "archive_repaired": repaired, "head_hash": local_head,
        "pending_operations": pending, "alerts": alerts,
    }


__all__ = ["reconcile_audit_archive"]
