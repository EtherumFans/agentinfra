"""Populated PostgreSQL lifecycle gate for HSM v2 rotation and 070 rollback."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from cryptography.fernet import Fernet

from app.services.phi_encryption import decrypt_phi, encrypt_phi_v1
from app.services.soft_hsm_keystore import seal_keyring
from scripts.backfill_phi_envelopes import run as backfill
from scripts.manage_soft_hsm_keystore import (
    inspect as inspect_key_store,
    rotate as rotate_key_store,
    rotate_bootstrap,
)
from scripts.prepare_phi_070_compatibility import run as restore_070
from scripts.rewrap_phi_deks import run as rewrap_deks
from scripts.rotate_phi_envelopes import run as rotate


APP_URL = os.getenv("P1_POSTGRES_TEST_DATABASE_URL", "")
MIGRATION_URL = os.getenv("P1_POSTGRES_MIGRATION_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not (APP_URL.startswith("postgresql") and MIGRATION_URL.startswith("postgresql")),
    reason="P1 PostgreSQL application and migration URLs are not configured",
)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _raw(url: str) -> str:
    for driver in ("+asyncpg", "+psycopg", "+psycopg2"):
        url = url.replace(driver, "", 1)
    return url


def _alembic(target: str, *, expect_failure: bool = False) -> str:
    env = dict(os.environ, DATABASE_URL=MIGRATION_URL)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade" if target.startswith("-") else "upgrade",
         target.removeprefix("-")],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True,
    )
    output = result.stdout + result.stderr
    if expect_failure:
        assert result.returncode != 0
    else:
        assert result.returncode == 0, output[-3000:]
    return output


def _set_tenant(cursor, organization_id: str) -> None:
    cursor.execute(
        "SELECT set_config('icoder.current_organization_id', %s, true)",
        (organization_id,),
    )


def test_v1_v2_online_rotation_and_populated_070_compatibility(
    monkeypatch, request, tmp_path,
) -> None:
    suffix = uuid.uuid4().hex[:8]
    organization_id = f"h72{suffix}"
    row_id = f"e72{suffix}"
    legacy_key = Fernet.generate_key().decode("ascii")
    hsm_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY_V1", legacy_key)
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", legacy_key)
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID", "1")

    def cleanup() -> None:
        with psycopg.connect(_raw(MIGRATION_URL)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                revision = str(cursor.fetchone()[0])
        if revision == "070":
            backfill(MIGRATION_URL, execute=True)
        if revision != "074":
            _alembic("074")
        with psycopg.connect(_raw(APP_URL)) as connection:
            with connection.cursor() as cursor:
                _set_tenant(cursor, organization_id)
                cursor.execute("DELETE FROM encounters WHERE organization_id=%s", (organization_id,))
            connection.commit()
        with psycopg.connect(_raw(MIGRATION_URL)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM organizations WHERE id=%s", (organization_id,))
            connection.commit()

    request.addfinalizer(cleanup)

    def legacy(value: str) -> str:
        result = encrypt_phi_v1(value)
        assert result
        return result

    with psycopg.connect(_raw(MIGRATION_URL)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM alembic_version")
            assert cursor.fetchone()[0] == "074"
            cursor.execute(
                "INSERT INTO organizations (id,name,slug,plan,settings,is_active) "
                "VALUES (%s,%s,%s,'free','{}'::json,true)",
                (organization_id, organization_id, organization_id),
            )
        connection.commit()
    with psycopg.connect(_raw(APP_URL)) as connection:
        with connection.cursor() as cursor:
            _set_tenant(cursor, organization_id)
            cursor.execute(
                "INSERT INTO encounters "
                "(id,organization_id,encounter_id,patient_id,department,admission_reason,"
                "existing_diagnosis_codes,existing_procedure_codes,status) "
                "VALUES (%s,%s,%s,%s,'cardiology',%s,%s,%s,'pending')",
                (
                    row_id, organization_id, f"enc-{suffix}", f"patient-{suffix}",
                    legacy("rollback symptom"),
                    legacy(json.dumps([{"code": "I20.9", "name": "angina"}])),
                    legacy("[]"),
                ),
            )
        connection.commit()

    monkeypatch.setenv("ICODER_PHI_KEY_PROVIDER", "software_hsm")
    monkeypatch.delenv("ICODER_SOFT_HSM_KEYSTORE_PATH", raising=False)
    monkeypatch.delenv("ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE", raising=False)
    monkeypatch.setenv("ICODER_SOFT_HSM_KEY_ID", "integration-kek-v1")
    monkeypatch.setenv("ICODER_SOFT_HSM_MASTER_KEY", hsm_key)

    forward = rotate(MIGRATION_URL, target="v2", execute=True, batch_size=1)
    assert forward["values"] == 3
    assert rotate(MIGRATION_URL, target="v2", execute=False, batch_size=1)["values"] == 0

    with psycopg.connect(_raw(MIGRATION_URL)) as connection:
        with connection.cursor() as cursor:
            _set_tenant(cursor, organization_id)
            cursor.execute("SELECT admission_reason FROM encounters WHERE id=%s", (row_id,))
            before_rewrap = str(cursor.fetchone()[0])
    bootstrap_key = bytearray(os.urandom(32))
    key_store = (tmp_path / "integration-software-hsm.keys").resolve()
    key_store.write_bytes(seal_keyring(
        {
            "active_key_id": "integration-kek-v1",
            "keys": {
                "integration-kek-v1": {"key": hsm_key, "state": "active"},
            },
        },
        bootstrap_key=bootstrap_key,
        generation=1,
    ))
    os.chmod(key_store, 0o600)
    rotation = rotate_key_store(
        key_store, new_key_id="integration-kek-v2", expected_generation=1,
        bootstrap_key=bootstrap_key,
    )
    assert rotation["generation"] == 2
    monkeypatch.setenv("ICODER_SOFT_HSM_KEYSTORE_PATH", str(key_store))
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_BOOTSTRAP_KEY",
        base64.urlsafe_b64encode(bootstrap_key).decode("ascii"),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_MIN_GENERATION", "2")
    monkeypatch.setenv("ICODER_SOFT_HSM_REQUIRE_ENCRYPTED_KEYSTORE", "true")
    preview_rewrap = rewrap_deks(MIGRATION_URL, execute=False, batch_size=1)
    assert preview_rewrap["values_to_rewrap"] == 3
    applied_rewrap = rewrap_deks(MIGRATION_URL, execute=True, batch_size=1)
    assert applied_rewrap["values_to_rewrap"] == 3
    assert rewrap_deks(MIGRATION_URL, execute=False, batch_size=1)["retirement_ready"]
    with psycopg.connect(_raw(MIGRATION_URL)) as connection:
        with connection.cursor() as cursor:
            _set_tenant(cursor, organization_id)
            cursor.execute("SELECT admission_reason FROM encounters WHERE id=%s", (row_id,))
            after_rewrap = str(cursor.fetchone()[0])

    def envelope(value: str) -> dict:
        encoded = value[3:] + "=" * (-len(value[3:]) % 4)
        return json.loads(base64.urlsafe_b64decode(encoded))

    before_payload, after_payload = envelope(before_rewrap), envelope(after_rewrap)
    assert before_payload["c"] == after_payload["c"]
    assert before_payload["n"] == after_payload["n"]
    assert after_payload["k"] == "integration-kek-v2"
    assert after_payload["d"] == "integration-kek-v1"

    new_bootstrap_key = bytearray(os.urandom(32))
    bootstrap_rotation = rotate_bootstrap(
        key_store, expected_generation=2, bootstrap_key=bootstrap_key,
        new_bootstrap_key=new_bootstrap_key,
    )
    assert bootstrap_rotation["generation"] == 3
    with pytest.raises(RuntimeError, match="authentication failed"):
        inspect_key_store(key_store, bootstrap_key=bootstrap_key)
    monkeypatch.setenv(
        "ICODER_SOFT_HSM_BOOTSTRAP_KEY",
        base64.urlsafe_b64encode(new_bootstrap_key).decode("ascii"),
    )
    monkeypatch.setenv("ICODER_SOFT_HSM_MIN_GENERATION", "3")
    assert decrypt_phi(after_rewrap) == "rollback symptom"
    with psycopg.connect(_raw(MIGRATION_URL)) as connection:
        with connection.cursor() as cursor:
            _set_tenant(cursor, organization_id)
            cursor.execute("SELECT admission_reason FROM encounters WHERE id=%s", (row_id,))
            assert str(cursor.fetchone()[0]) == after_rewrap
    blocked = _alembic("-071", expect_failure=True)
    assert "refuses downgrade while HSM v2 PHI remains" in blocked

    reverse = rotate(MIGRATION_URL, target="v1", execute=True, batch_size=1)
    assert reverse["values"] == 3
    _alembic("-070")
    preview = restore_070(MIGRATION_URL, execute=False)
    assert preview["values"] == 3 and not preview["plaintext_at_rest"]
    restored = restore_070(MIGRATION_URL, execute=True)
    assert restored["values"] == 3 and restored["plaintext_at_rest"]

    with psycopg.connect(_raw(MIGRATION_URL)) as connection:
        with connection.cursor() as cursor:
            _set_tenant(cursor, organization_id)
            cursor.execute(
                "SELECT admission_reason, existing_diagnosis_codes "
                "FROM encounters WHERE id=%s", (row_id,),
            )
            reason, diagnoses = cursor.fetchone()
            assert reason == "rollback symptom"
            assert diagnoses == [{"code": "I20.9", "name": "angina"}]

    migrated = backfill(MIGRATION_URL, execute=True)
    assert migrated["updated_values"] >= 3
    _alembic("074")
    assert rotate(MIGRATION_URL, target="v2", execute=True, batch_size=2)["values"] >= 3

    with psycopg.connect(_raw(APP_URL)) as connection:
        with connection.cursor() as cursor:
            _set_tenant(cursor, organization_id)
            cursor.execute("DELETE FROM encounters WHERE id=%s", (row_id,))
        connection.commit()
    with psycopg.connect(_raw(MIGRATION_URL)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM organizations WHERE id=%s", (organization_id,))
        connection.commit()
