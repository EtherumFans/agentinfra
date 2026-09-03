"""Live PostgreSQL release gate for revision 071 PHI envelopes."""

from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from cryptography.fernet import Fernet
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.models.encounter import Encounter


APP_URL = os.getenv("P1_POSTGRES_TEST_DATABASE_URL", "")
MIGRATION_URL = os.getenv("P1_POSTGRES_MIGRATION_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not (APP_URL.startswith("postgresql") and MIGRATION_URL.startswith("postgresql")),
    reason="P1 PostgreSQL application and migration URLs are not configured",
)


def _sync(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)


def _tenant(connection: sa.Connection, organization_id: str) -> None:
    connection.execute(sa.text(
        "SELECT set_config('icoder.current_organization_id', :org, true)"
    ), {"org": organization_id})


def test_orm_round_trip_raw_ciphertext_plaintext_rejection_and_rls(monkeypatch) -> None:
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    app = sa.create_engine(_sync(APP_URL))
    migration = sa.create_engine(_sync(MIGRATION_URL))
    suffix = uuid.uuid4().hex[:8]
    org_a, org_b = f"e71a{suffix}", f"e71b{suffix}"
    encounter_id = f"enc71{suffix}"
    sentinel = f"张三胸痛-{suffix}"
    try:
        with migration.begin() as connection:
            for org in (org_a, org_b):
                connection.execute(sa.text(
                    "INSERT INTO organizations (id,name,slug,plan,settings,is_active) "
                    "VALUES (:id,:id,:id,'free',CAST('{}' AS json),true)"
                ), {"id": org})

        with Session(app) as session:
            _tenant(session.connection(), org_a)
            row = Encounter(
                organization_id=org_a,
                encounter_id=encounter_id,
                patient_id=f"patient-{suffix}",
                department="cardiology",
                admission_reason=sentinel,
                discharge_summary="症状改善",
                existing_diagnosis_codes=[{"code": "I20.9", "name": "心绞痛"}],
                existing_procedure_codes=[],
            )
            session.add(row)
            session.flush()
            row_id = row.id
            session.commit()

        with migration.begin() as connection:
            _tenant(connection, org_a)
            raw = connection.execute(sa.text(
                "SELECT admission_reason, existing_diagnosis_codes "
                "FROM encounters WHERE id=:id"
            ), {"id": row_id}).one()
            assert raw.admission_reason.startswith("v1:")
            assert raw.existing_diagnosis_codes.startswith("v1:")
            assert sentinel not in raw.admission_reason

        with Session(app) as session:
            _tenant(session.connection(), org_a)
            loaded = session.get(Encounter, row_id)
            assert loaded and loaded.admission_reason == sentinel
            assert loaded.existing_diagnosis_codes[0]["code"] == "I20.9"

        with app.begin() as connection:
            _tenant(connection, org_b)
            assert connection.execute(sa.text(
                "SELECT count(*) FROM encounters WHERE id=:id"
            ), {"id": row_id}).scalar_one() == 0

        for bypass_value in ("plaintext", "v1:not-a-fernet-token"):
            with pytest.raises(DBAPIError, match="ck_phi_envelope"):
                with app.begin() as connection:
                    _tenant(connection, org_a)
                    connection.execute(sa.text(
                        "UPDATE encounters SET admission_reason=:value WHERE id=:id"
                    ), {"id": row_id, "value": bypass_value})
    finally:
        with app.begin() as connection:
            _tenant(connection, org_a)
            connection.execute(sa.text(
                "DELETE FROM encounters WHERE encounter_id=:encounter_id"
            ), {"encounter_id": encounter_id})
        with migration.begin() as connection:
            connection.execute(sa.text(
                "DELETE FROM organizations WHERE id IN (:org_a, :org_b)"
            ), {"org_a": org_a, "org_b": org_b})
        app.dispose()
        migration.dispose()
