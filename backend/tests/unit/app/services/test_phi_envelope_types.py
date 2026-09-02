import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.dialects import postgresql, sqlite

from app.services.phi_encryption import EncryptedPHIJSON, EncryptedPHIText


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
