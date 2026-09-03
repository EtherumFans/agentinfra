from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.stt_artifact import (
    STTInteraction,
    STTStreamCheckpoint,
    STTStreamCheckpointChunk,
)
from app.services.stream_checkpoint_repository import (
    StreamCheckpointConfigurationMismatch,
    StreamCheckpointFenceLost,
    StreamCheckpointIntegrityError,
    stream_checkpoint_repository,
)


@pytest_asyncio.fixture
async def checkpoint_store(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'streams-checkpoints.db'}",
        connect_args={"timeout": 30},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(STTInteraction.__table__.create)
        await connection.run_sync(STTStreamCheckpoint.__table__.create)
        await connection.run_sync(STTStreamCheckpointChunk.__table__.create)
    yield factory
    await engine.dispose()


def _scope(**overrides: str) -> dict[str, str]:
    return {
        "organization_id": overrides.get("organization_id", "org-a"),
        "owner_id": overrides.get("owner_id", "owner-a"),
        "interaction_id": overrides.get(
            "interaction_id", "11111111-1111-4111-8111-111111111111"
        ),
    }


def _state(
    *,
    chunks: int = 0,
    audio_bytes: int = 0,
    transcript: str = "",
    retention: str = "retain",
) -> dict:
    return {
        "schema": "icoder/stt-stream-checkpoint/v1",
        "configuration": {
            "transcription": {
                "primaryLanguage": "zh-CN",
                "diarize": False,
                "isMultichannel": False,
                "participants": [{"channel": 0, "role": "multiple"}],
            },
            "mode": {"type": "transcription", "outputLocale": None},
            "retentionPolicy": retention,
            "audioFormat": None,
            "audioEvents": {"enabled": False},
            "replacements": [],
            "keyterms": {"terms": []},
        },
        "recording_id": "22222222-2222-4222-8222-222222222222",
        "started_at": "2026-08-25T02:00:00+08:00",
        "transcript_seq": 1 if transcript else 0,
        "fact_seq": 0,
        "audio_chunk_count": chunks,
        "audio_bytes": audio_bytes,
        "last_processed_bytes": audio_bytes if transcript else 0,
        "transcript_text": transcript,
        "emitted_facts": [],
        "provider_usage": {},
        "resolved_audio_format": "audio/ogg" if audio_bytes else None,
        "audio_format_validated": bool(audio_bytes),
        "audio_event_count": 0,
    }


@pytest.mark.asyncio
async def test_checkpoint_restores_exact_encrypted_audio_and_state(checkpoint_store):
    scope = _scope()
    async with checkpoint_store() as db:
        initialized = await stream_checkpoint_repository.resume_or_initialize(
            db,
            scope=scope,
            session_id="session-a",
            state=_state(),
            enabled=True,
        )
        assert initialized is not None and not initialized.resumed
        await db.commit()

    first = b"OggS" + b"\x00" * 8
    second = b"clinical-audio-fragment"
    async with checkpoint_store() as db:
        await stream_checkpoint_repository.append_chunk(
            db,
            scope=scope,
            session_id="session-a",
            state=_state(chunks=1, audio_bytes=len(first)),
            chunk=first,
        )
        await db.commit()
    async with checkpoint_store() as db:
        await stream_checkpoint_repository.append_chunk(
            db,
            scope=scope,
            session_id="session-a",
            state=_state(
                chunks=2,
                audio_bytes=len(first) + len(second),
                transcript="患者主诉胸痛",
            ),
            chunk=second,
        )
        await db.commit()

    async with checkpoint_store() as db:
        checkpoint = await db.scalar(select(STTStreamCheckpoint))
        chunks = list((await db.execute(
            select(STTStreamCheckpointChunk)
            .order_by(STTStreamCheckpointChunk.sequence)
        )).scalars())
        assert checkpoint is not None
        assert "患者主诉胸痛" not in checkpoint.encrypted_state_json
        assert all(row.encrypted_content not in (first, second) for row in chunks)

        restored = await stream_checkpoint_repository.resume_or_initialize(
            db,
            scope=scope,
            session_id="session-b",
            state=_state(),
            enabled=True,
        )
        await db.commit()
    assert restored is not None and restored.resumed
    assert restored.audio == first + second
    assert restored.state["transcript_text"] == "患者主诉胸痛"


@pytest.mark.asyncio
async def test_checkpoint_fences_stale_writer_after_resume(checkpoint_store):
    scope = _scope()
    async with checkpoint_store() as db:
        await stream_checkpoint_repository.resume_or_initialize(
            db, scope=scope, session_id="old-session", state=_state(), enabled=True
        )
        await db.commit()
    async with checkpoint_store() as db:
        await stream_checkpoint_repository.resume_or_initialize(
            db, scope=scope, session_id="new-session", state=_state(), enabled=True
        )
        await db.commit()
    async with checkpoint_store() as db:
        with pytest.raises(StreamCheckpointFenceLost):
            await stream_checkpoint_repository.append_chunk(
                db,
                scope=scope,
                session_id="old-session",
                state=_state(chunks=1, audio_bytes=4),
                chunk=b"OggS",
            )


@pytest.mark.asyncio
async def test_checkpoint_rejects_changed_or_nonretained_resume(checkpoint_store):
    scope = _scope()
    async with checkpoint_store() as db:
        await stream_checkpoint_repository.resume_or_initialize(
            db, scope=scope, session_id="session-a", state=_state(), enabled=True
        )
        await db.commit()
    changed = _state()
    changed["configuration"]["transcription"]["primaryLanguage"] = "en-US"
    async with checkpoint_store() as db:
        with pytest.raises(StreamCheckpointConfigurationMismatch):
            await stream_checkpoint_repository.resume_or_initialize(
                db,
                scope=scope,
                session_id="session-b",
                state=changed,
                enabled=True,
            )
    async with checkpoint_store() as db:
        with pytest.raises(StreamCheckpointConfigurationMismatch):
            await stream_checkpoint_repository.resume_or_initialize(
                db,
                scope=scope,
                session_id="session-b",
                state=_state(retention="none"),
                enabled=False,
            )


@pytest.mark.asyncio
async def test_checkpoint_detects_tampered_audio_chunk(checkpoint_store):
    scope = _scope()
    async with checkpoint_store() as db:
        await stream_checkpoint_repository.resume_or_initialize(
            db, scope=scope, session_id="session-a", state=_state(), enabled=True
        )
        await stream_checkpoint_repository.append_chunk(
            db,
            scope=scope,
            session_id="session-a",
            state=_state(chunks=1, audio_bytes=4),
            chunk=b"OggS",
        )
        await db.commit()
    async with checkpoint_store() as db:
        row = await db.scalar(select(STTStreamCheckpointChunk))
        assert row is not None
        row.content_sha256 = "0" * 64
        await db.commit()
    async with checkpoint_store() as db:
        with pytest.raises(StreamCheckpointIntegrityError):
            await stream_checkpoint_repository.resume_or_initialize(
                db,
                scope=scope,
                session_id="session-b",
                state=_state(),
                enabled=True,
            )


@pytest.mark.asyncio
async def test_checkpoint_refuses_plaintext_local_fallback(checkpoint_store, monkeypatch):
    monkeypatch.delenv("ICODER_PHI_ENCRYPTION_KEY", raising=False)
    from app.services.stream_checkpoint_repository import (
        StreamCheckpointEncryptionRequired,
    )

    async with checkpoint_store() as db:
        with pytest.raises(StreamCheckpointEncryptionRequired):
            await stream_checkpoint_repository.resume_or_initialize(
                db,
                scope=_scope(interaction_id="33333333-3333-4333-8333-333333333333"),
                session_id="session-a",
                state=_state(),
                enabled=True,
            )
