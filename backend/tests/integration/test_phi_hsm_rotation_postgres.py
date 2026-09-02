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

from app.services.phi_encryption import encrypt_phi_v1
from scripts.backfill_phi_envelopes import run as backfill
from scripts.prepare_phi_070_compatibility import run as restore_070
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


def test_v1_v2_online_rotation_and_populated_070_compatibility(monkeypatch, request) -> None:
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
            _alembic("072")
        elif revision == "071":
            _alembic("072")
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
            assert cursor.fetchone()[0] == "072"
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
    monkeypatch.setenv("ICODER_SOFT_HSM_KEY_ID", "integration-kek-v1")
    monkeypatch.setenv("ICODER_SOFT_HSM_MASTER_KEY", hsm_key)

    forward = rotate(MIGRATION_URL, target="v2", execute=True, batch_size=1)
    assert forward["values"] == 3
    assert rotate(MIGRATION_URL, target="v2", execute=False, batch_size=1)["values"] == 0
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
    _alembic("072")
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
