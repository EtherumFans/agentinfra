from __future__ import annotations

from app.services.soft_hsm_audit_archive import ArchivePolicy, LocalWormAuditArchive
from app.services.soft_hsm_audit_reconcile import reconcile_audit_archive
from app.services.soft_hsm_ops_audit import append_event, key_store_identifier


def _event(path, phase="started", outcome="pending") -> dict:
    return {
        "operation": "rotate", "phase": phase, "outcome": outcome,
        "key_store_id": key_store_identifier(path), "expected_generation": 1,
        "resulting_generation": 2 if phase == "completed" else None,
        "active_key_id": "kek-v2" if phase == "completed" else None,
        "key_states": {"kek-v2": "active"} if phase == "completed" else {},
        "error_type": None, "change_ticket": "SEC-7102",
        "operator_identity": "reconcile-worker", "deployment_environment": "test",
        "release_version": "phase7.1-test",
    }


def _archive(tmp_path):
    root = (tmp_path / "worm").resolve()
    root.mkdir()
    return LocalWormAuditArchive(
        root, checkpoint_key=b"independent-checkpoint-key-material",
        checkpoint_key_id="checkpoint-v1", policy=ArchivePolicy(retention_days=30),
    )


def test_reconcile_repairs_checkpoint_lag_and_converges(tmp_path) -> None:
    journal = (tmp_path / "ops.jsonl").resolve()
    key = b"independent-audit-signing-key-32!"
    first = append_event(journal, _event(journal), audit_key=key, signing_key_id="audit-v1")
    second = append_event(
        journal, _event(journal, "completed", "success"),
        audit_key=key, signing_key_id="audit-v1",
    )
    archive = _archive(tmp_path)
    archive.replicate_records([first])
    report = reconcile_audit_archive(
        journal, audit_key=key, signing_key_id="audit-v1",
        verification_keys={"audit-v1": key}, archive=archive, minimum_sequence=2,
    )
    assert report["status"] == "passed"
    assert report["checkpoint_lag_before"] == 1
    assert report["checkpoint_lag_after"] == 0
    assert report["archive_repaired"] is True
    assert report["head_hash"] == second["chain_hash"]


def test_reconcile_alerts_on_started_without_terminal(tmp_path) -> None:
    journal = (tmp_path / "ops.jsonl").resolve()
    key = b"independent-audit-signing-key-32!"
    append_event(journal, _event(journal), audit_key=key, signing_key_id="audit-v1")
    archive = _archive(tmp_path)
    report = reconcile_audit_archive(
        journal, audit_key=key, signing_key_id="audit-v1",
        verification_keys={"audit-v1": key}, archive=archive,
        max_pending_seconds=0,
    )
    assert report["status"] == "attention"
    assert report["alerts"] == ["HSM_AUDIT_STARTED_WITHOUT_TERMINAL"]
    assert report["pending_operations"][0]["change_ticket"] == "SEC-7102"
