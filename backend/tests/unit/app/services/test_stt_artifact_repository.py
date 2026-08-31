"""Security and concurrency invariants for durable STT artifacts."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select

from app import database as database_module
from app.models.stt_artifact import STTInteraction, STTRecording
from app.services.stt_artifact_repository import stt_artifact_repository


def _scope(*, organization_id: str = "org-stt-a", owner_id: str = "user-stt-a"):
    return {
        "organization_id": organization_id,
        "owner_id": owner_id,
        "interaction_id": f"secure-stt-{uuid.uuid4()}",
    }


@pytest.mark.asyncio
async def test_recordings_are_invisible_across_tenant_and_principal_boundaries():
    scope = _scope()
    recording_id = f"recording-{uuid.uuid4()}"
    async with database_module.AsyncSessionLocal() as db:
        await stt_artifact_repository.put_recording(
            db,
            **scope,
            recording_id=recording_id,
            media_type="audio/wav",
            content=b"tenant-private-audio",
        )
        await db.commit()

    async with database_module.AsyncSessionLocal() as db:
        assert await stt_artifact_repository.get_recording(
            db, **scope, recording_id=recording_id
        ) is not None
        assert await stt_artifact_repository.get_recording(
            db,
            **{**scope, "organization_id": "org-stt-b"},
            recording_id=recording_id,
        ) is None
        assert await stt_artifact_repository.get_recording(
            db,
            **{**scope, "owner_id": "user-stt-b"},
            recording_id=recording_id,
        ) is None
        assert await stt_artifact_repository.list_recordings(
            db, **{**scope, "organization_id": "org-stt-b"}
        ) == []


@pytest.mark.asyncio
async def test_encrypted_recording_detects_ciphertext_and_digest_tampering(monkeypatch):
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID", "1")
    scope = _scope()
    plaintext = b"patient-audio-phi"
    recording_id = f"recording-{uuid.uuid4()}"

    async with database_module.AsyncSessionLocal() as db:
        row = await stt_artifact_repository.put_recording(
            db,
            **scope,
            recording_id=recording_id,
            media_type="audio/wav",
            content=plaintext,
        )
        assert plaintext not in row.encrypted_content
        assert row.encrypted_content.startswith(b"v1:")
        await db.commit()

    async with database_module.AsyncSessionLocal() as db:
        row = await stt_artifact_repository.get_recording(
            db, **scope, recording_id=recording_id
        )
        assert row is not None
        row.encrypted_content = row.encrypted_content[:-1] + bytes(
            [row.encrypted_content[-1] ^ 1]
        )
        await db.commit()

    async with database_module.AsyncSessionLocal() as db:
        row = await stt_artifact_repository.get_recording(
            db, **scope, recording_id=recording_id
        )
        assert row is not None
        with pytest.raises(InvalidToken):
            stt_artifact_repository.recording_content(row)

        # Re-encrypt valid bytes but leave the original digest inconsistent:
        # authenticated encryption succeeds, then the independent SHA-256
        # integrity check must still reject the substituted payload.
        from app.services.phi_encryption import encrypt_phi_bytes

        row.encrypted_content = encrypt_phi_bytes(b"substituted-audio")
        await db.commit()

    async with database_module.AsyncSessionLocal() as db:
        row = await stt_artifact_repository.get_recording(
            db, **scope, recording_id=recording_id
        )
        assert row is not None
        with pytest.raises(RuntimeError, match="integrity_check_failed"):
            stt_artifact_repository.recording_content(row)


@pytest.mark.asyncio
async def test_concurrent_first_writes_create_one_interaction_and_two_recordings():
    scope = _scope()

    async def writer(index: int) -> None:
        async with database_module.AsyncSessionLocal() as db:
            await stt_artifact_repository.put_recording(
                db,
                **scope,
                recording_id=f"concurrent-recording-{index}-{uuid.uuid4()}",
                media_type="audio/wav",
                content=f"audio-{index}".encode(),
            )
            await db.commit()

    await asyncio.gather(writer(1), writer(2))

    async with database_module.AsyncSessionLocal() as db:
        interaction_count = await db.scalar(
            select(func.count()).select_from(STTInteraction).where(
                STTInteraction.organization_id == scope["organization_id"],
                STTInteraction.owner_id == scope["owner_id"],
                STTInteraction.interaction_id == scope["interaction_id"],
            )
        )
        recording_count = await db.scalar(
            select(func.count()).select_from(STTRecording).where(
                STTRecording.organization_id == scope["organization_id"],
                STTRecording.owner_id == scope["owner_id"],
                STTRecording.interaction_id == scope["interaction_id"],
            )
        )
        assert interaction_count == 1
        assert recording_count == 2


@pytest.mark.asyncio
async def test_structured_multichannel_transcript_is_encrypted_and_round_trips(monkeypatch):
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY_ACTIVE_ID", "1")
    scope = _scope()
    transcript_id = f"transcript-{uuid.uuid4()}"
    segments = (
        {
            "channel": 0,
            "participant": 0,
            "speakerId": -1,
            "text": "医生询问症状",
            "start": 0,
            "end": 1200,
        },
        {
            "channel": 1,
            "participant": 1,
            "speakerId": -1,
            "text": "患者回答胸痛",
            "start": 0,
            "end": 1200,
        },
    )
    async with database_module.AsyncSessionLocal() as db:
        row = await stt_artifact_repository.put_transcript(
            db,
            **scope,
            transcript_id=transcript_id,
            recording_id=f"recording-{uuid.uuid4()}",
            participant_roles=((0, "doctor"), (1, "patient")),
            transcript_segments=segments,
            request_data={"isMultichannel": True},
            status="completed",
        )
        assert "医生询问症状" not in (row.encrypted_text or "")
        await db.commit()

    async with database_module.AsyncSessionLocal() as db:
        row = await stt_artifact_repository.get_transcript(
            db,
            **scope,
            transcript_id=transcript_id,
        )
        assert row is not None
        assert stt_artifact_repository.transcript_segments(row) == segments
        assert stt_artifact_repository.transcript_text(row) == "医生询问症状\n患者回答胸痛"
