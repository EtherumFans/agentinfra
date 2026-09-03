from __future__ import annotations

import base64
import json
import os

import pytest

from app.services.phi_encryption import decrypt_phi, encrypt_phi
from app.services.soft_hsm import SoftwareHSMKeyring
from app.services.soft_hsm_keystore import seal_keyring, unseal_keyring
from scripts.manage_soft_hsm_keystore import create, inspect, rotate, set_state


def _bootstrap() -> bytearray:
    return bytearray(b"bootstrap-test-key-material-32!!")


def _payload() -> dict:
    return {
        "active_key_id": "kek-v1",
        "keys": {
            "kek-v1": {
                "key": base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
                "state": "active",
            }
        },
    }


def test_encrypted_key_store_authentication_and_rollback_gate() -> None:
    bootstrap = _bootstrap()
    document = seal_keyring(_payload(), bootstrap_key=bootstrap, generation=7)
    payload, generation = unseal_keyring(
        document, bootstrap_key=bootstrap, minimum_generation=7,
    )
    assert payload == _payload() and generation == 7
    assert b"kek-v1" not in document
    assert base64.urlsafe_b64encode(b"k" * 32) not in document

    parsed = json.loads(document)
    parsed["ciphertext"] = parsed["ciphertext"][:-1] + (
        "A" if parsed["ciphertext"][-1] != "A" else "B"
    )
    with pytest.raises(RuntimeError, match="authentication failed"):
        unseal_keyring(
            json.dumps(parsed).encode(), bootstrap_key=bootstrap,
            minimum_generation=7,
        )
    with pytest.raises(RuntimeError, match="authentication failed"):
        unseal_keyring(document, bootstrap_key=b"x" * 32, minimum_generation=7)
    with pytest.raises(RuntimeError, match="rollback detected"):
        unseal_keyring(document, bootstrap_key=bootstrap, minimum_generation=8)


def test_atomic_lifecycle_and_runtime_dual_read(tmp_path, monkeypatch) -> None:
    path = (tmp_path / "software-hsm.keys").resolve()
    bootstrap = _bootstrap()
    report = create(path, key_id="kek-v1", bootstrap_key=bootstrap)
    assert report == {
        "operation": "create",
        "active_key_id": "kek-v1", "generation": 1,
        "source": "encrypted_keystore", "key_states": {"kek-v1": "active"},
    }
    inspected = inspect(path, bootstrap_key=bootstrap)
    assert inspected == {**report, "operation": "inspect"}
    assert b"kek-v1" not in path.read_bytes()

    monkeypatch.setenv("ICODER_PHI_KEY_PROVIDER", "software_hsm")
    monkeypatch.setenv("ICODER_SOFT_HSM_KEYSTORE_PATH", str(path))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_BOOTSTRAP_KEY",
        base64.urlsafe_b64encode(bootstrap).decode("ascii"),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_MIN_GENERATION", "1")
    original = encrypt_phi("encrypted with first KEK")
    assert original

    report = rotate(
        path, new_key_id="kek-v2", expected_generation=1,
        bootstrap_key=bootstrap,
    )
    assert report["generation"] == 2
    assert report["key_states"] == {"kek-v1": "decrypt-only", "kek-v2": "active"}
    monkeypatch.setenv("ICODER_SOFT_HSM_MIN_GENERATION", "2")
    assert decrypt_phi(original) == "encrypted with first KEK"
    current = encrypt_phi("encrypted with second KEK")
    assert current and decrypt_phi(current) == "encrypted with second KEK"

    with pytest.raises(RuntimeError, match="explicit authorization"):
        set_state(
            path, key_id="kek-v1", state="retired", expected_generation=2,
            bootstrap_key=bootstrap, authorization="",
        )
    report = set_state(
        path, key_id="kek-v1", state="retired", expected_generation=2,
        bootstrap_key=bootstrap, authorization="ZERO_REFERENCES_VERIFIED",
    )
    assert report["generation"] == 3
    monkeypatch.setenv("ICODER_SOFT_HSM_MIN_GENERATION", "3")
    with pytest.raises(RuntimeError, match="not enabled for decrypt"):
        decrypt_phi(original)
    assert decrypt_phi(current) == "encrypted with second KEK"


def test_cloud_mode_requires_encrypted_store_and_generation_floor(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "cloud")
    monkeypatch.setenv("ICODER_SOFT_HSM_MASTER_KEY", _payload()["keys"]["kek-v1"]["key"])
    with pytest.raises(RuntimeError, match="encrypted software HSM key store is required"):
        SoftwareHSMKeyring.from_environment()

    path = (tmp_path / "cloud.keys").resolve()
    bootstrap = _bootstrap()
    create(path, key_id="cloud-kek-v1", bootstrap_key=bootstrap)
    monkeypatch.setenv("ICODER_SOFT_HSM_KEYSTORE_PATH", str(path))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_BOOTSTRAP_KEY",
        base64.urlsafe_b64encode(bootstrap).decode("ascii"),
    )
    monkeypatch.delenv("ICODER_SOFT_HSM_MIN_GENERATION", raising=False)
    with pytest.raises(RuntimeError, match="MIN_GENERATION is required"):
        SoftwareHSMKeyring.from_environment()


def test_generation_compare_and_swap_blocks_stale_operator(tmp_path) -> None:
    path = (tmp_path / "generation.keys").resolve()
    bootstrap = _bootstrap()
    create(path, key_id="kek-v1", bootstrap_key=bootstrap)
    rotate(path, new_key_id="kek-v2", expected_generation=1, bootstrap_key=bootstrap)
    with pytest.raises(RuntimeError, match="generation mismatch"):
        rotate(path, new_key_id="kek-v3", expected_generation=1, bootstrap_key=bootstrap)


def test_existing_store_is_never_overwritten_by_create(tmp_path) -> None:
    path = (tmp_path / "existing.keys").resolve()
    bootstrap = _bootstrap()
    create(path, key_id="kek-v1", bootstrap_key=bootstrap)
    original = path.read_bytes()
    with pytest.raises(RuntimeError, match="already exists"):
        create(path, key_id="kek-v2", bootstrap_key=bootstrap)
    assert path.read_bytes() == original


def test_environment_keyring_rejects_duplicates_and_hides_key_repr(monkeypatch) -> None:
    monkeypatch.setenv("ICODER_DEPLOYMENT_MODE", "local")
    monkeypatch.delenv("ICODER_SOFT_HSM_KEYSTORE_PATH", raising=False)
    key = base64.urlsafe_b64encode(b"s" * 32).decode("ascii")
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_KEYRING_JSON",
        '{"active_key_id":"kek-v1","active_key_id":"kek-v2","keys":{}}',
    )
    with pytest.raises(RuntimeError, match="not valid JSON"):
        SoftwareHSMKeyring.from_environment()

    monkeypatch.setenv(
        "ICODER_SOFT_HSM_KEYRING_JSON",
        json.dumps({
            "active_key_id": "kek-v1",
            "keys": {"kek-v1": {"key": key, "state": "active"}},
        }),
    )
    keyring = SoftwareHSMKeyring.from_environment()
    assert key not in repr(keyring)
