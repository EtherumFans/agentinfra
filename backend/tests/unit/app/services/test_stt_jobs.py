"""Durable STT job recovery after an interrupted process."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app import database as database_module
from app.services import stt_service
from app.services.stt_artifact_repository import stt_artifact_repository


@pytest.mark.asyncio
async def test_recover_pending_stt_job_from_database(monkeypatch):
    interaction_id = f"recover-{uuid.uuid4()}"
    scope = {
        "organization_id": "org_default1",
        "owner_id": "u-test-bypass",
        "interaction_id": interaction_id,
    }
    recording_id = f"{interaction_id}-rec-{uuid.uuid4()}"
    transcript_id = str(uuid.uuid4())

    async with database_module.AsyncSessionLocal() as db:
        await stt_artifact_repository.put_recording(
            db,
            **scope,
            recording_id=recording_id,
            media_type="audio/wav",
            content=b"recoverable-audio",
        )
        await stt_artifact_repository.put_transcript(
            db,
            **scope,
            transcript_id=transcript_id,
            recording_id=recording_id,
            participant_roles=((1, "doctor"),),
            status="processing",
            request_data={
                "primaryLanguage": "zh-CN",
                "isDictation": True,
                "replacements": [],
                "keyterms": ["房颤", "Corti Health"],
            },
        )
        await db.commit()

    async def transcribe(content: bytes, media_type: str, *, keyterms):
        assert content == b"recoverable-audio"
        assert media_type == "audio/wav"
        assert keyterms == ("房颤", "Corti Health")
        stt_service._record_stt_inference_telemetry(
            provider="funasr",
            model="iic/paraformer@v2.0.4",
            latency_ms=17,
            status="complete",
            fallback_used=False,
            streaming=False,
        )
        return "恢复后的转录 句号", ""

    monkeypatch.setattr("app.services.stt_jobs.transcribe_bytes", transcribe)
    from app.services.stt_jobs import recover_pending_stt_jobs

    assert await recover_pending_stt_jobs() >= 1
    for _ in range(50):
        await asyncio.sleep(0.01)
        async with database_module.AsyncSessionLocal() as db:
            row = await stt_artifact_repository.get_transcript(
                db, **scope, transcript_id=transcript_id
            )
            if row is not None and row.status == "completed":
                assert stt_artifact_repository.transcript_text(row) == "恢复后的转录。"
                assert stt_artifact_repository.request_data(row)[
                    "_runtimeTelemetry"
                ] == {
                    "schema": "icoder/stt-inference-telemetry/v1",
                    "provider": "funasr",
                    "model": "iic/paraformer@v2.0.4",
                    "status": "complete",
                    "latency_ms": 17,
                    "fallback_used": False,
                    "streaming": False,
                }
                return
    pytest.fail("recovered STT job did not complete")


@pytest.mark.asyncio
async def test_recover_pending_multichannel_job_preserves_structured_rows(monkeypatch):
    from app.services.stt_service import STTChannelTranscript

    interaction_id = f"recover-multichannel-{uuid.uuid4()}"
    scope = {
        "organization_id": "org_default1",
        "owner_id": "u-test-bypass",
        "interaction_id": interaction_id,
    }
    recording_id = f"{interaction_id}-rec-{uuid.uuid4()}"
    transcript_id = str(uuid.uuid4())
    async with database_module.AsyncSessionLocal() as db:
        await stt_artifact_repository.put_recording(
            db,
            **scope,
            recording_id=recording_id,
            media_type="audio/wav",
            content=b"validated-stereo-audio",
        )
        await stt_artifact_repository.put_transcript(
            db,
            **scope,
            transcript_id=transcript_id,
            recording_id=recording_id,
            participant_roles=((0, "doctor"), (1, "patient")),
            status="processing",
            request_data={
                "primaryLanguage": "zh-CN",
                "isMultichannel": True,
                "spokenPunctuation": True,
                "replacements": [],
                "keyterms": ["房颤"],
            },
        )
        await db.commit()

    async def transcribe(content, media_type, *, expected_channels, keyterms):
        assert content == b"validated-stereo-audio"
        assert media_type == "audio/wav"
        assert expected_channels == 2
        assert keyterms == ("房颤",)
        return (
            [
                STTChannelTranscript(0, "医生恢复 句号", 0, 90),
                STTChannelTranscript(1, "患者恢复", 0, 90),
            ],
            "",
            {
                "schema": "icoder/stt-inference-telemetry/v1",
                "provider": "funasr",
                "model": "iic/paraformer@v2.0.4",
                "latency_ms": 23,
                "status": "complete",
                "fallback_used": False,
                "streaming": False,
            },
        )

    monkeypatch.setattr(
        "app.services.stt_jobs.transcribe_multichannel_bytes_with_telemetry",
        transcribe,
    )
    from app.services.stt_jobs import recover_pending_stt_jobs

    assert await recover_pending_stt_jobs() >= 1
    for _ in range(50):
        await asyncio.sleep(0.01)
        async with database_module.AsyncSessionLocal() as db:
            row = await stt_artifact_repository.get_transcript(
                db,
                **scope,
                transcript_id=transcript_id,
            )
            if row is not None and row.status == "completed":
                assert stt_artifact_repository.transcript_segments(row) == (
                    {
                        "channel": 0,
                        "participant": 0,
                        "speakerId": -1,
                        "text": "医生恢复。",
                        "start": 0,
                        "end": 90,
                    },
                    {
                        "channel": 1,
                        "participant": 1,
                        "speakerId": -1,
                        "text": "患者恢复",
                        "start": 0,
                        "end": 90,
                    },
                )
                return
    pytest.fail("recovered multichannel STT job did not complete")
