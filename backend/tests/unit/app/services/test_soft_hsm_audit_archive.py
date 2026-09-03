from __future__ import annotations

import base64
import json
import shutil
from datetime import UTC, datetime, timedelta

import pytest

import app.services.soft_hsm_ops_audit as audit_module
from app.services.soft_hsm_audit_archive import (
    ArchivePolicy,
    LocalWormAuditArchive,
    archive_from_environment,
)
from app.services.soft_hsm_ops_audit import append_event, key_store_identifier, verify_audit_file
from scripts.manage_soft_hsm_keystore import _archive_is_required, _audited_mutation, create


def _event(path, phase="started", outcome="pending") -> dict:
    return {
        "operation": "create", "phase": phase, "outcome": outcome,
        "key_store_id": key_store_identifier(path), "expected_generation": 0,
        "resulting_generation": 1 if phase == "completed" else None,
        "active_key_id": "kek-v1" if phase == "completed" else None,
        "key_states": {"kek-v1": "active"} if phase == "completed" else {},
        "error_type": None, "change_ticket": "SEC-7001",
        "operator_identity": "ci-security", "deployment_environment": "test",
        "release_version": "phase7-test",
    }


def _archive(tmp_path, *, legal_hold=False):
    root = (tmp_path / "worm").resolve()
    root.mkdir(parents=True)
    return LocalWormAuditArchive(
        root, checkpoint_key=b"checkpoint-independent-key-32-bytes",
        checkpoint_key_id="checkpoint-v1",
        policy=ArchivePolicy(retention_days=30, legal_hold=legal_hold),
    )


def test_legacy_required_flag_remains_an_explicit_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED", raising=False)
    monkeypatch.setenv("ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED", "true")
    assert _archive_is_required() is True


def test_invalid_advanced_archive_flag_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED", "sometimes")
    monkeypatch.delenv("ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED", raising=False)
    with pytest.raises(RuntimeError, match="feature flag is invalid"):
        _archive_is_required()


def test_archive_detects_tamper_missing_duplicate_and_reorder(tmp_path) -> None:
    journal = (tmp_path / "ops.jsonl").resolve()
    key = b"audit-signing-key-material-32-byte"
    first = append_event(journal, _event(journal), audit_key=key, signing_key_id="audit-v1")
    second = append_event(
        journal, _event(journal, "completed", "success"),
        audit_key=key, signing_key_id="audit-v1",
    )
    archive = _archive(tmp_path)
    archive.replicate_records([first, second])
    assert archive.verify(verification_keys={"audit-v1": key}, minimum_sequence=2)["status"] == "passed"

    checkpoint_path = sorted((archive.root / "checkpoints").glob("*.json"))[-1]
    original_checkpoint = checkpoint_path.read_bytes()
    checkpoint = json.loads(original_checkpoint)
    checkpoint["chain_hash"] = "0" * 64
    checkpoint_path.chmod(0o600)
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(RuntimeError, match="checkpoint verification"):
        archive.verify(verification_keys={"audit-v1": key}, minimum_sequence=2)
    checkpoint_path.write_bytes(original_checkpoint)

    object_paths = sorted((archive.root / "objects").glob("*.json"))
    original_second = object_paths[1].read_bytes()
    changed = json.loads(original_second)
    changed["record"]["event"]["change_ticket"] = "TAMPERED"
    object_paths[1].chmod(0o600)
    object_paths[1].write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(RuntimeError, match="verification"):
        archive.verify(verification_keys={"audit-v1": key}, minimum_sequence=2)
    object_paths[1].write_bytes(original_second)

    object_paths[0].chmod(0o600)
    object_paths[0].unlink()
    with pytest.raises(RuntimeError, match="verification|tail rollback"):
        archive.verify(verification_keys={"audit-v1": key}, minimum_sequence=2)
    duplicate = archive.root / "objects" / ("9" * 20 + "-" + second["chain_hash"] + ".json")
    duplicate.write_bytes(original_second)
    with pytest.raises(RuntimeError, match="integrity"):
        archive.verify(verification_keys={"audit-v1": key})


def test_signing_key_rotation_and_host_journal_recovery(tmp_path) -> None:
    journal = (tmp_path / "ops.jsonl").resolve()
    old_key = b"old-audit-signing-key-32-bytes!!!"
    new_key = b"new-audit-signing-key-32-bytes!!!"
    first = append_event(journal, _event(journal), audit_key=old_key, signing_key_id="audit-v1")
    second = append_event(
        journal, _event(journal, "completed", "success"), audit_key=new_key,
        signing_key_id="audit-v2", verification_keys={"audit-v1": old_key, "audit-v2": new_key},
    )
    archive = _archive(tmp_path)
    archive.replicate_records([first, second])
    report = archive.verify(
        verification_keys={"audit-v1": old_key, "audit-v2": new_key}, minimum_sequence=2,
    )
    assert report["signing_key_ids"] == ["audit-v1", "audit-v2"]

    restored_root = (tmp_path / "cross-region-restore").resolve()
    shutil.copytree(archive.root, restored_root)
    restored = LocalWormAuditArchive(
        restored_root, checkpoint_key=b"checkpoint-independent-key-32-bytes",
        checkpoint_key_id="checkpoint-v1", policy=ArchivePolicy(retention_days=30),
    )
    assert restored.verify(
        verification_keys={"audit-v1": old_key, "audit-v2": new_key}, minimum_sequence=2,
    )["head_hash"] == second["chain_hash"]

    journal.unlink()
    evidence = json.loads(archive.export_evidence())
    recovered = (tmp_path / "recovered.jsonl").resolve()
    recovered.write_bytes(b"".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        for record in evidence["records"]
    ))
    recovered.chmod(0o600)
    assert verify_audit_file(
        recovered, audit_key=new_key, signing_key_id="audit-v2",
        verification_keys={"audit-v1": old_key, "audit-v2": new_key}, minimum_sequence=2,
    )["records"] == 2


def test_local_journal_rolls_over_with_global_chain_continuity(tmp_path, monkeypatch) -> None:
    journal = (tmp_path / "ops.jsonl").resolve()
    key = b"audit-signing-key-material-32-byte"
    monkeypatch.setattr(audit_module, "_MAX_SEGMENT_BYTES", 1100)
    append_event(journal, _event(journal), audit_key=key, signing_key_id="audit-v1")
    append_event(
        journal, _event(journal, "completed", "success"),
        audit_key=key, signing_key_id="audit-v1",
    )
    report = verify_audit_file(
        journal, audit_key=key, signing_key_id="audit-v1", minimum_sequence=2,
    )
    assert report["records"] == 2
    assert report["segments"] == 2
    assert (tmp_path / "ops.jsonl.000002").exists()


def test_retention_legal_hold_and_minimum_necessary_export(tmp_path) -> None:
    journal = (tmp_path / "ops.jsonl").resolve()
    key = b"audit-signing-key-material-32-byte"
    record = append_event(journal, _event(journal), audit_key=key, signing_key_id="audit-v1")
    archive = _archive(tmp_path, legal_hold=True)
    archive.replicate_records([record])
    with pytest.raises(RuntimeError, match="legal hold"):
        archive.delete_object(
            sequence=1, chain_hash=record["chain_hash"],
            now=datetime.now(UTC) + timedelta(days=365),
        )
    retained = _archive(tmp_path / "retained")
    retained.replicate_records([record])
    with pytest.raises(RuntimeError, match="retention"):
        retained.delete_object(sequence=1, chain_hash=record["chain_hash"])
    exported = retained.export_evidence()
    assert b"checkpoint-independent-key" not in exported
    assert b"audit-signing-key" not in exported
    assert b"SYNTHETIC-PHI" not in exported


def test_archive_unavailable_blocks_key_store_mutation(tmp_path, monkeypatch) -> None:
    key_store = (tmp_path / "software-hsm.keys").resolve()
    audit_path = (tmp_path / "ops.jsonl").resolve()
    audit_key = b"independent-audit-key-material-32!"
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_PATH", str(audit_path))
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_KEY", base64.urlsafe_b64encode(audit_key).decode())
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID", "audit-v1")
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE", "0")
    monkeypatch.setenv("ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED", "true")
    monkeypatch.setenv("ICODER_SOFT_HSM_AUDIT_ARCHIVE_ADAPTER", "local_worm_simulator")
    monkeypatch.setenv("ICODER_SOFT_HSM_AUDIT_ARCHIVE_ROOT", str(tmp_path / "missing"))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY",
        base64.urlsafe_b64encode(b"checkpoint-independent-key-32-bytes").decode(),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY_ID", "checkpoint-v1")
    bootstrap = bytearray(b"bootstrap-test-key-material-32!!")
    with pytest.raises(RuntimeError, match="archive root"):
        _audited_mutation(
            operation="create", path=key_store, expected_generation=0,
            change_ticket="SEC-7002", bootstrap_key=bootstrap,
            callback=lambda: create(key_store, key_id="kek-v1", bootstrap_key=bootstrap),
        )
    assert not key_store.exists()


def test_enabled_archive_is_replicated_before_and_after_mutation(tmp_path, monkeypatch) -> None:
    key_store = (tmp_path / "software-hsm.keys").resolve()
    audit_path = (tmp_path / "ops.jsonl").resolve()
    archive_root = (tmp_path / "worm").resolve()
    archive_root.mkdir()
    audit_key = b"independent-audit-key-material-32!"
    checkpoint_key = b"checkpoint-independent-key-32-bytes"
    settings = {
        "ICODER_SOFT_HSM_OPS_AUDIT_PATH": str(audit_path),
        "ICODER_SOFT_HSM_OPS_AUDIT_KEY": base64.urlsafe_b64encode(audit_key).decode(),
        "ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID": "audit-v1",
        "ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED": "true",
        "ICODER_SOFT_HSM_AUDIT_ARCHIVE_ADAPTER": "local_worm_simulator",
        "ICODER_SOFT_HSM_AUDIT_ARCHIVE_ROOT": str(archive_root),
        "ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY": base64.urlsafe_b64encode(checkpoint_key).decode(),
        "ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY_ID": "checkpoint-v1",
        "ICODER_OPERATOR_IDENTITY": "ci-security", "ICODER_DEPLOYMENT_ENVIRONMENT": "ci",
        "ICODER_RELEASE_VERSION": "phase7-test",
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    bootstrap = bytearray(b"bootstrap-test-key-material-32!!")
    result = _audited_mutation(
        operation="create", path=key_store, expected_generation=0,
        change_ticket="SEC-7003", bootstrap_key=bootstrap,
        callback=lambda: create(key_store, key_id="kek-v1", bootstrap_key=bootstrap),
    )
    assert result["audit_archive"]["records"] == 2
    assert len(list((archive_root / "objects").glob("*.json"))) == 2
    assert LocalWormAuditArchive(
        archive_root, checkpoint_key=checkpoint_key, checkpoint_key_id="checkpoint-v1",
        policy=ArchivePolicy(retention_days=2555),
    ).verify(verification_keys={"audit-v1": audit_key}, minimum_sequence=2)["records"] == 2


def test_cloud_mode_does_not_implicitly_enable_advanced_archive(
    tmp_path, monkeypatch,
) -> None:
    key_store = (tmp_path / "software-hsm.keys").resolve()
    audit_path = (tmp_path / "ops.jsonl").resolve()
    audit_key = b"independent-audit-key-material-32!"
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    monkeypatch.setenv("ICODER_IMMUTABLE_AUDIT_ARCHIVE_ENABLED", "false")
    monkeypatch.delenv("ICODER_SOFT_HSM_AUDIT_ARCHIVE_REQUIRED", raising=False)
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_PATH", str(audit_path))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_OPS_AUDIT_KEY", base64.urlsafe_b64encode(audit_key).decode(),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID", "audit-v1")
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_MIN_SEQUENCE", "0")
    monkeypatch.setenv("ICODER_OPERATOR_IDENTITY", "cloud-operator")
    monkeypatch.setenv("ICODER_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setenv("ICODER_RELEASE_VERSION", "optional-archive-test")
    bootstrap = bytearray(b"bootstrap-test-key-material-32!!")

    result = _audited_mutation(
        operation="create", path=key_store, expected_generation=0,
        change_ticket="SEC-7004", bootstrap_key=bootstrap,
        callback=lambda: create(key_store, key_id="kek-v1", bootstrap_key=bootstrap),
    )

    assert result["audit_archive"] is None
    assert key_store.exists()
    assert verify_audit_file(
        audit_path, audit_key=audit_key, signing_key_id="audit-v1",
        minimum_sequence=2,
    )["records"] == 2


def test_local_worm_simulator_is_forbidden_in_cloud_mode(tmp_path, monkeypatch) -> None:
    root = (tmp_path / "worm").resolve()
    root.mkdir()
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    monkeypatch.setenv("ICODER_SOFT_HSM_AUDIT_ARCHIVE_ADAPTER", "local_worm_simulator")
    monkeypatch.setenv("ICODER_SOFT_HSM_AUDIT_ARCHIVE_ROOT", str(root))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY",
        base64.urlsafe_b64encode(b"checkpoint-independent-key-32-bytes").decode(),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_AUDIT_CHECKPOINT_KEY_ID", "checkpoint-v1")
    with pytest.raises(RuntimeError, match="forbidden in cloud"):
        archive_from_environment()
