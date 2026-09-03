from __future__ import annotations

import base64
import json

import pytest

from app.services.phi_encryption import decrypt_phi, encrypt_phi
from app.services.soft_hsm_ops_audit import (
    append_event,
    key_store_identifier,
    verify_audit_file,
)
from scripts.manage_soft_hsm_keystore import (
    _audited_mutation,
    create,
    inspect,
    rotate_bootstrap,
)


def _event(path, *, phase: str, outcome: str) -> dict:
    return {
        "operation": "rotate-bootstrap",
        "phase": phase,
        "outcome": outcome,
        "key_store_id": key_store_identifier(path),
        "expected_generation": 1,
        "resulting_generation": 2 if phase == "completed" else None,
        "active_key_id": "kek-v1" if phase == "completed" else None,
        "key_states": {"kek-v1": "active"} if phase == "completed" else {},
        "error_type": "RuntimeError" if phase == "failed" else None,
        "change_ticket": "DR-TEST-001",
    }


def test_append_verify_tamper_and_tail_rollback(tmp_path) -> None:
    path = (tmp_path / "ops-audit.jsonl").resolve()
    key = bytearray(b"audit-test-key-material-32-bytes!")
    first = append_event(
        path, _event(path, phase="started", outcome="pending"),
        audit_key=key, signing_key_id="audit-v1",
    )
    second = append_event(
        path, _event(path, phase="completed", outcome="success"),
        audit_key=key, signing_key_id="audit-v1",
    )
    report = verify_audit_file(
        path, audit_key=key, signing_key_id="audit-v1", minimum_sequence=2,
    )
    assert report["records"] == 2
    assert report["head_hash"] == second["chain_hash"]
    assert first["previous_hash"] == "0" * 64

    original = path.read_bytes()
    lines = original.splitlines()
    with pytest.raises(RuntimeError, match="tail rollback"):
        truncated = (tmp_path / "truncated.jsonl").resolve()
        truncated.write_bytes(lines[0] + b"\n")
        truncated.chmod(0o600)
        verify_audit_file(
            truncated, audit_key=key, signing_key_id="audit-v1", minimum_sequence=2,
        )
    with pytest.raises(RuntimeError, match="tail rollback"):
        append_event(
            truncated, _event(path, phase="started", outcome="pending"),
            audit_key=key, signing_key_id="audit-v1", minimum_sequence=2,
        )

    record = json.loads(lines[1])
    record["recorded_at"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    path.chmod(0o600)
    with pytest.raises(RuntimeError, match="verification failed"):
        verify_audit_file(path, audit_key=key, signing_key_id="audit-v1")
    path.write_bytes(original)
    path.chmod(0o600)
    with pytest.raises(RuntimeError, match="verification failed"):
        verify_audit_file(path, audit_key=b"x" * 32, signing_key_id="audit-v1")


def test_audited_mutation_records_success_and_failure(tmp_path, monkeypatch) -> None:
    key_store = (tmp_path / "software-hsm.keys").resolve()
    audit_path = (tmp_path / "ops-audit.jsonl").resolve()
    bootstrap = bytearray(b"bootstrap-test-key-material-32!!")
    audit_key = b"independent-audit-key-material-32!"
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_PATH", str(audit_path))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_OPS_AUDIT_KEY",
        base64.urlsafe_b64encode(audit_key).decode("ascii"),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID", "ops-audit-v1")

    report = _audited_mutation(
        operation="create", path=key_store, expected_generation=0,
        change_ticket="CHANGE-001", bootstrap_key=bootstrap,
        callback=lambda: create(key_store, key_id="kek-v1", bootstrap_key=bootstrap),
    )
    assert report["audit_sequence"] == 2
    with pytest.raises(RuntimeError, match="deliberate failure"):
        _audited_mutation(
            operation="rotate", path=key_store, expected_generation=1,
            change_ticket="CHANGE-002", bootstrap_key=bootstrap,
            callback=lambda: (_ for _ in ()).throw(RuntimeError("deliberate failure")),
        )
    records = [json.loads(line) for line in audit_path.read_text().splitlines()]
    assert [record["event"]["phase"] for record in records] == [
        "started", "completed", "started", "failed",
    ]
    assert "deliberate failure" not in audit_path.read_text()
    assert verify_audit_file(
        audit_path, audit_key=audit_key, signing_key_id="ops-audit-v1",
        minimum_sequence=4,
    )["status"] == "passed"


def test_operations_audit_key_must_be_independent(tmp_path, monkeypatch) -> None:
    key_store = (tmp_path / "software-hsm.keys").resolve()
    audit_path = (tmp_path / "ops-audit.jsonl").resolve()
    bootstrap = bytearray(b"bootstrap-test-key-material-32!!")
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_PATH", str(audit_path))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_OPS_AUDIT_KEY",
        base64.urlsafe_b64encode(bootstrap).decode("ascii"),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_OPS_AUDIT_KEY_ID", "ops-audit-v1")
    with pytest.raises(RuntimeError, match="must differ from bootstrap"):
        _audited_mutation(
            operation="create", path=key_store, expected_generation=0,
            change_ticket="CHANGE-003", bootstrap_key=bootstrap,
            callback=lambda: create(
                key_store, key_id="kek-v1", bootstrap_key=bootstrap,
            ),
        )
    assert not key_store.exists()


def test_bootstrap_rotation_preserves_keks_and_phi(tmp_path, monkeypatch) -> None:
    path = (tmp_path / "bootstrap-rotation.keys").resolve()
    old_key = bytearray(b"bootstrap-test-key-material-32!!")
    new_key = bytearray(b"n" * 32)
    create(path, key_id="kek-v1", bootstrap_key=old_key)
    monkeypatch.setenv("ICODER_PHI_KEY_PROVIDER", "software_hsm")
    monkeypatch.setenv("ICODER_SOFT_HSM_KEYSTORE_PATH", str(path))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_BOOTSTRAP_KEY",
        base64.urlsafe_b64encode(old_key).decode("ascii"),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_MIN_GENERATION", "1")
    stored = encrypt_phi("PHI survives bootstrap rotation")
    assert stored

    result = rotate_bootstrap(
        path, expected_generation=1, bootstrap_key=old_key,
        new_bootstrap_key=new_key,
    )
    assert result["generation"] == 2
    with pytest.raises(RuntimeError, match="authentication failed"):
        inspect(path, bootstrap_key=old_key)
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_BOOTSTRAP_KEY",
        base64.urlsafe_b64encode(new_key).decode("ascii"),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_MIN_GENERATION", "2")
    assert decrypt_phi(stored) == "PHI survives bootstrap rotation"
