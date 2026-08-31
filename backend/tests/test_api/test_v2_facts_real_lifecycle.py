"""Real persistence, isolation, validation and PHI-at-rest tests for Facts."""

from __future__ import annotations

import asyncio
import os
import uuid

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")


def _client() -> TestClient:
    from app.main import app

    return TestClient(app)


def test_facts_real_crud_lifecycle_and_interaction_scope():
    interaction_id = f"facts-lifecycle-{uuid.uuid4()}"
    wrong_interaction_id = f"facts-other-{uuid.uuid4()}"

    with _client() as client:
        created = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/facts/",
            json={
                "facts": [
                    {"text": "Penicillin allergy.", "group": "allergies", "source": "core"},
                    {"text": "BP 140/90 mmHg.", "group": "vital-signs", "source": "system"},
                ]
            },
        )
        assert created.status_code == 200, created.text
        created_facts = created.json()["facts"]
        assert len(created_facts) == 2
        assert [fact["source"] for fact in created_facts] == ["core", "system"]
        for fact in created_facts:
            uuid.UUID(fact["id"])
            uuid.UUID(fact["groupId"])

        listed = client.get(f"/api/v2/tools/interactions/{interaction_id}/facts/")
        assert listed.status_code == 200, listed.text
        assert [fact["id"] for fact in listed.json()["facts"]] == [
            fact["id"] for fact in created_facts
        ]

        first_id, second_id = (fact["id"] for fact in created_facts)
        updated = client.patch(
            f"/api/v2/tools/interactions/{interaction_id}/facts/{first_id}",
            json={"text": "Severe penicillin allergy."},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["text"] == "Severe penicillin allergy."
        assert updated.json()["group"] == "allergies"
        assert updated.json()["source"] == "core"

        batch = client.patch(
            f"/api/v2/tools/interactions/{interaction_id}/facts/",
            json={
                "facts": [
                    {"factId": first_id, "isDiscarded": True},
                    {"factId": second_id, "group": "assessment"},
                ]
            },
        )
        assert batch.status_code == 200, batch.text
        assert batch.json()["facts"][0]["isDiscarded"] is True
        assert batch.json()["facts"][1]["group"] == "assessment"
        assert batch.json()["facts"][1]["source"] == "system"

        assert client.patch(
            f"/api/v2/tools/interactions/{wrong_interaction_id}/facts/{first_id}",
            json={"text": "cross-scope mutation"},
        ).status_code == 404
        assert client.patch(
            f"/api/v2/tools/interactions/{interaction_id}/facts/{uuid.uuid4()}",
            json={"text": "missing"},
        ).status_code == 404


def test_facts_batch_update_is_atomic_on_missing_id():
    interaction_id = f"facts-atomic-{uuid.uuid4()}"
    with _client() as client:
        created = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/facts/",
            json={"facts": [{"text": "Original.", "group": "other"}]},
        )
        fact_id = created.json()["facts"][0]["id"]
        response = client.patch(
            f"/api/v2/tools/interactions/{interaction_id}/facts/",
            json={
                "facts": [
                    {"factId": fact_id, "text": "Must not persist."},
                    {"factId": str(uuid.uuid4()), "text": "Missing."},
                ]
            },
        )
        assert response.status_code == 404
        listed = client.get(f"/api/v2/tools/interactions/{interaction_id}/facts/")
        assert listed.json()["facts"][0]["text"] == "Original."


def test_facts_validation_rejects_invalid_rows_and_duplicate_batch_ids():
    interaction_id = f"facts-validation-{uuid.uuid4()}"
    with _client() as client:
        for fact in (
            {"text": "   ", "group": "other"},
            {"text": "Valid", "group": "   "},
            {"text": "Valid", "group": "other", "source": "external"},
        ):
            response = client.post(
                f"/api/v2/tools/interactions/{interaction_id}/facts/",
                json={"facts": [fact]},
            )
            assert response.status_code == 422, response.text

        created = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/facts/",
            json={"facts": [{"text": "Valid", "group": "other"}]},
        )
        fact_id = created.json()["facts"][0]["id"]
        duplicate = client.patch(
            f"/api/v2/tools/interactions/{interaction_id}/facts/",
            json={"facts": [{"factId": fact_id}, {"factId": fact_id}]},
        )
        assert duplicate.status_code == 422


def test_facts_text_is_encrypted_at_rest(monkeypatch):
    from app.database import AsyncSessionLocal
    from app.models.clinical_fact import ClinicalFactRecord
    from app.services.phi_encryption import is_encrypted_value

    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID", raising=False)
    interaction_id = f"facts-encryption-{uuid.uuid4()}"
    phi = f"Patient Zhang sensitive note {uuid.uuid4()}"

    with _client() as client:
        created = client.post(
            f"/api/v2/tools/interactions/{interaction_id}/facts/",
            json={"facts": [{"text": phi, "group": "other"}]},
        )
        assert created.status_code == 200, created.text
        fact_id = created.json()["facts"][0]["id"]

        async def _stored_value() -> str:
            async with AsyncSessionLocal() as db:
                row = await db.scalar(
                    select(ClinicalFactRecord).where(
                        ClinicalFactRecord.interaction_id == interaction_id,
                        ClinicalFactRecord.fact_id == fact_id,
                    )
                )
                assert row is not None
                return row.encrypted_text

        stored = asyncio.run(_stored_value())
        assert phi not in stored
        assert is_encrypted_value(stored)

        listed = client.get(f"/api/v2/tools/interactions/{interaction_id}/facts/")
        assert listed.status_code == 200, listed.text
        assert listed.json()["facts"][0]["text"] == phi
