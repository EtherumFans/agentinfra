import json
import base64
import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.dialects import postgresql, sqlite

from app.services.phi_encryption import (
    EncryptedPHIJSON,
    EncryptedPHIText,
    decrypt_phi,
    decrypt_phi_bytes,
    encrypt_phi,
    encrypt_phi_bytes,
    encrypt_phi_v1,
    is_encrypted_value,
    phi_v2_key_id,
    rewrap_phi_v2,
)
from app.services.soft_hsm import SoftwareHSMKeyring, key_operation_metrics_snapshot


def _soft_hsm(monkeypatch) -> None:
    monkeypatch.delenv("ICODER_SOFT_HSM_KEYSTORE_PATH", raising=False)
    monkeypatch.delenv("ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE", raising=False)
    monkeypatch.setenv("ICODER_PHI_KEY_PROVIDER", "software_hsm")
    monkeypatch.setenv("ICODER_SOFT_HSM_KEY_ID", "test-kek-v1")
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )


def _keyring(monkeypatch, *, old_state: str = "decrypt-only") -> None:
    monkeypatch.delenv("ICODER_SOFT_HSM_KEYSTORE_PATH", raising=False)
    monkeypatch.delenv("ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE", raising=False)
    keys = {
        "test-kek-v1": {
            "key": base64.urlsafe_b64encode(b"1" * 32).decode("ascii"),
            "state": old_state,
        },
        "test-kek-v2": {
            "key": base64.urlsafe_b64encode(b"2" * 32).decode("ascii"),
            "state": "active",
        },
    }
    monkeypatch.setenv("ICODER_PHI_KEY_PROVIDER", "software_hsm")
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_KEYRING_JSON",
        json.dumps({"active_key_id": "test-kek-v2", "keys": keys}),
    )


def test_postgresql_text_envelope_round_trip(monkeypatch) -> None:
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    value = "患者张三：持续胸痛"
    encrypted = EncryptedPHIText().process_bind_param(value, postgresql.dialect())
    assert encrypted.startswith("v1:")
    assert value not in encrypted
    assert EncryptedPHIText().process_result_value(
        encrypted, postgresql.dialect()
    ) == value


def test_postgresql_json_is_one_opaque_canonical_envelope(monkeypatch) -> None:
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    value = {"symptom": "胸痛", "codes": ["I20.9"]}
    encrypted = EncryptedPHIJSON().process_bind_param(value, postgresql.dialect())
    assert encrypted.startswith("v1:")
    assert "symptom" not in encrypted and "胸痛" not in encrypted
    assert EncryptedPHIJSON().process_result_value(
        encrypted, postgresql.dialect()
    ) == value


def test_postgresql_missing_key_and_plaintext_read_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv("ICODER_PHI_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="key is required"):
        EncryptedPHIText().process_bind_param("PHI", postgresql.dialect())
    with pytest.raises(RuntimeError, match="plaintext PHI"):
        EncryptedPHIText().process_result_value("PHI", postgresql.dialect())
    with pytest.raises(RuntimeError, match="plaintext PHI"):
        EncryptedPHIText().process_result_value("v1:not-a-fernet-token", postgresql.dialect())


def test_sqlite_retains_local_development_compatibility(monkeypatch) -> None:
    monkeypatch.delenv("ICODER_PHI_ENCRYPTION_KEY", raising=False)
    assert EncryptedPHIText().process_bind_param("local", sqlite.dialect()) == "local"
    stored = EncryptedPHIJSON().process_bind_param({"a": 1}, sqlite.dialect())
    assert json.loads(stored) == {"a": 1}
    assert EncryptedPHIJSON().process_result_value(stored, sqlite.dialect()) == {"a": 1}


def test_software_hsm_v2_text_json_and_binary_round_trip(monkeypatch) -> None:
    _soft_hsm(monkeypatch)
    text = "患者张三：胸痛"
    encrypted = encrypt_phi(text)
    assert encrypted and encrypted.startswith("v2:")
    assert text not in encrypted and is_encrypted_value(encrypted)
    assert decrypt_phi(encrypted) == text

    value = {"symptom": "胸痛", "codes": ["I20.9"]}
    stored_json = EncryptedPHIJSON().process_bind_param(value, postgresql.dialect())
    assert stored_json.startswith("v2:")
    assert EncryptedPHIJSON().process_result_value(
        stored_json, postgresql.dialect()
    ) == value

    binary = encrypt_phi_bytes(b"binary-phi")
    assert binary.startswith(b"v2:")
    assert decrypt_phi_bytes(binary) == b"binary-phi"


def test_software_hsm_dual_reads_v1_during_online_rotation(monkeypatch) -> None:
    legacy_key = Fernet.generate_key().decode()
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY_V1", legacy_key)
    _soft_hsm(monkeypatch)
    legacy = encrypt_phi_v1("legacy PHI")
    assert legacy and legacy.startswith("v1:")
    assert decrypt_phi(legacy) == "legacy PHI"
    assert encrypt_phi("new PHI").startswith("v2:")


def test_software_hsm_wrong_kek_and_tamper_fail_closed(monkeypatch) -> None:
    _soft_hsm(monkeypatch)
    encrypted = encrypt_phi("sensitive")
    assert encrypted
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_MASTER_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"),
    )
    with pytest.raises(RuntimeError, match="unwrap data key"):
        decrypt_phi(encrypted)

    _soft_hsm(monkeypatch)
    encrypted = encrypt_phi("sensitive")
    tampered = encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B")
    with pytest.raises(RuntimeError, match="authentication failed|unwrap data key|metadata is malformed"):
        decrypt_phi(tampered)


def test_postgresql_bind_authenticates_envelope_shaped_input(monkeypatch) -> None:
    _soft_hsm(monkeypatch)
    with pytest.raises(RuntimeError, match="metadata is malformed"):
        EncryptedPHIText().process_bind_param("v2:" + "A" * 200, postgresql.dialect())


def test_software_hsm_keyring_rewraps_only_dek(monkeypatch) -> None:
    monkeypatch.setenv("ICODER_PHI_KEY_PROVIDER", "software_hsm")
    monkeypatch.setenv("ICODER_SOFT_HSM_KEY_ID", "test-kek-v1")
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_MASTER_KEY",
        base64.urlsafe_b64encode(b"1" * 32).decode("ascii"),
    )
    original = encrypt_phi("PHI that must not be data-reencrypted")
    assert original

    _keyring(monkeypatch)
    rewrapped = rewrap_phi_v2(original)
    assert rewrapped != original
    assert phi_v2_key_id(rewrapped) == "test-kek-v2"
    assert decrypt_phi(rewrapped) == "PHI that must not be data-reencrypted"

    def payload(value: str) -> dict:
        raw = value[3:] + "=" * (-len(value[3:]) % 4)
        return json.loads(base64.urlsafe_b64decode(raw))

    before, after = payload(original), payload(rewrapped)
    assert after["c"] == before["c"]
    assert after["n"] == before["n"]
    assert after["d"] == "test-kek-v1"
    assert after["w"] != before["w"]


def test_software_hsm_key_states_fail_closed_and_emit_safe_metrics(monkeypatch) -> None:
    _keyring(monkeypatch, old_state="retired")
    keyring = SoftwareHSMKeyring.from_environment()
    assert keyring.public_statuses() == {
        "test-kek-v1": "retired", "test-kek-v2": "active",
    }
    with pytest.raises(RuntimeError, match="not enabled for decrypt"):
        keyring.resolve("test-kek-v1", operation="unwrap")
    with pytest.raises(RuntimeError, match="unavailable"):
        keyring.resolve("unknown", operation="unwrap")

    key_operation_metrics_snapshot(reset=True)
    stored = encrypt_phi("metrics PHI")
    assert stored and decrypt_phi(stored) == "metrics PHI"
    metrics = key_operation_metrics_snapshot(reset=True)
    assert {row["operation"] for row in metrics} == {"generate", "unwrap"}
    assert all(set(row) == {"operation", "key_id", "status", "count"} for row in metrics)
