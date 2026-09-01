"""Durable STT background jobs and startup recovery."""

from __future__ import annotations

import asyncio
import logging

from app import database as database_module
from app.services.stt_artifact_repository import stt_artifact_repository
from app.services.stt_service import (
    apply_dictation_punctuation,
    apply_requested_replacements,
    get_stt_inference_telemetry,
    reset_stt_inference_telemetry,
    transcribe_bytes,
    transcribe_multichannel_bytes_with_telemetry,
)

logger = logging.getLogger(__name__)

# asyncio keeps only weak references to scheduled tasks. Retain recovery jobs
# until completion so a busy startup cannot collect them before persisted STT
# work reaches a terminal state.
_recovery_tasks: set[asyncio.Task[None]] = set()


def _schedule_recovery_job(identity: tuple[str, str, str, str]) -> None:
    task = asyncio.create_task(
        process_stt_transcript_job(*identity),
        name=f"stt-recovery:{identity[3]}",
    )
    _recovery_tasks.add(task)
    task.add_done_callback(_recovery_tasks.discard)


async def process_stt_transcript_job(
    organization_id: str,
    owner_id: str,
    interaction_id: str,
    transcript_id: str,
) -> None:
    """Resume one persisted transcript job entirely from database state."""
    scope = {
        "organization_id": organization_id,
        "owner_id": owner_id,
        "interaction_id": interaction_id,
    }
    async with database_module.AsyncSessionLocal() as db:
        from app.services.database_tenancy import bind_tenant_to_transaction
        await bind_tenant_to_transaction(db, organization_id)
        transcript = await stt_artifact_repository.get_transcript(
            db, **scope, transcript_id=transcript_id
        )
        if transcript is None or transcript.status != "processing":
            return
        recording = await stt_artifact_repository.get_recording(
            db, **scope, recording_id=transcript.recording_id
        )
        if recording is None:
            await stt_artifact_repository.set_transcript_failed(
                db, transcript, "recording_not_found", "Source recording no longer exists."
            )
            await db.commit()
            return
        try:
            content = stt_artifact_repository.recording_content(recording)
            request_data = stt_artifact_repository.request_data(transcript)
            keyterms = tuple(
                item
                for item in request_data.get("keyterms", [])
                if isinstance(item, str) and item
            )
            is_multichannel = request_data.get("isMultichannel") is True
            channel_rows = []
            if is_multichannel:
                channel_rows, error, runtime_telemetry = (
                    await transcribe_multichannel_bytes_with_telemetry(
                        content,
                        recording.media_type,
                        expected_channels=2,
                        keyterms=keyterms,
                    )
                )
                text = ""
            else:
                reset_stt_inference_telemetry()
                if keyterms:
                    text, error = await transcribe_bytes(
                        content,
                        recording.media_type,
                        keyterms=keyterms,
                    )
                else:
                    # Preserve compatibility with pre-keyterm rows and adapters
                    # that implement the original two-argument boundary.
                    text, error = await transcribe_bytes(content, recording.media_type)
                runtime_telemetry = get_stt_inference_telemetry()
            await stt_artifact_repository.set_transcript_runtime_telemetry(
                db, transcript, runtime_telemetry
            )
            if not text and not channel_rows:
                await stt_artifact_repository.set_transcript_failed(
                    db,
                    transcript,
                    "stt_unavailable",
                    error or "STT engine returned no transcript.",
                )
            elif channel_rows:
                segments = tuple(
                    {
                        "channel": item.channel,
                        "participant": item.channel,
                        "speakerId": -1,
                        "text": apply_requested_replacements(
                            apply_dictation_punctuation(
                                item.text,
                                primary_language=str(
                                    request_data.get("primaryLanguage", "zh-CN")
                                ),
                                enabled=(
                                    bool(request_data.get("spokenPunctuation"))
                                    if "spokenPunctuation" in request_data
                                    else bool(request_data.get("isDictation"))
                                ),
                            ),
                            list(request_data.get("replacements", [])),
                        ),
                        "start": item.start_ms,
                        "end": item.end_ms,
                    }
                    for item in channel_rows
                )
                await stt_artifact_repository.set_transcript_completed_segments(
                    db,
                    transcript,
                    segments,
                )
            else:
                text = apply_dictation_punctuation(
                    text,
                    primary_language=str(request_data.get("primaryLanguage", "zh-CN")),
                    enabled=(
                        bool(request_data.get("spokenPunctuation"))
                        if "spokenPunctuation" in request_data
                        else bool(request_data.get("isDictation"))
                    ),
                )
                text = apply_requested_replacements(
                    text,
                    list(request_data.get("replacements", [])),
                )
                await stt_artifact_repository.set_transcript_completed(db, transcript, text)
            await db.commit()
        except Exception as exc:
            logger.error(
                "STT job failed type=%s transcript_id=%s",
                type(exc).__name__,
                transcript_id,
            )
            await db.rollback()
            async with database_module.AsyncSessionLocal() as failure_db:
                from app.services.database_tenancy import (
                    bind_tenant_to_transaction,
                )
                await bind_tenant_to_transaction(failure_db, organization_id)
                row = await stt_artifact_repository.get_transcript(
                    failure_db, **scope, transcript_id=transcript_id
                )
                if row is not None:
                    await stt_artifact_repository.set_transcript_runtime_telemetry(
                        failure_db, row, get_stt_inference_telemetry()
                    )
                    await stt_artifact_repository.set_transcript_failed(
                        failure_db,
                        row,
                        "stt_job_failed",
                        "The STT background job failed.",
                    )
                    await failure_db.commit()


async def recover_pending_stt_jobs() -> int:
    """Schedule all persisted processing jobs after application restart."""
    async with database_module.AsyncSessionLocal() as db:
        pending = await stt_artifact_repository.list_processing(db)
        identities = [
            (row.organization_id, row.owner_id, row.interaction_id, row.transcript_id)
            for row in pending
        ]
    for identity in identities:
        _schedule_recovery_job(identity)
    if identities:
        logger.info("Recovered %d pending STT transcript jobs", len(identities))
    return len(identities)
