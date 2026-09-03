"""Corti-compatible v2 recordings and transcripts API.

The original Cycle 6-12 implementation provided deterministic protocol
fixtures only.  The current development runtime keeps those fixtures solely
for untouched legacy contract IDs and adds a real, authenticated lifecycle:
uploaded audio and transcript artifacts are encrypted in the database,
tenant/principal scoped, passed to the FunASR/Whisper pipeline, and exposed
through list/get/status/delete endpoints.  Synchronous and asynchronous jobs
share the same durable repository, and unfinished jobs are recovered after a
normal application restart.  STT engine failure is explicit; the real path
never fabricates transcript text.

Spec source (ground truth, never inferred):
- ``docs/corti-reverse-engineered/stt-list-transcripts.md`` (7,962 bytes,
  fetched 2026-07-01 from
  ``https://docs.corti.ai/api-reference/transcripts/list-transcripts.md``).
  Path: ``GET /interactions/{id}/transcripts/`` → operationId
  ``transcripts_list``.

What this module provides
-------------------------
- Corti-compatible recordings and transcript create/list/get/status/delete
  routes, including ``202 Accepted`` plus ``Location`` for asynchronous jobs.
- The Corti §13.3 list envelope
  ``{transcripts: TranscriptsListItem[] | null}``; ``?full=true`` includes the
  channel/participant/text/start/end rows.

Current development limitations
-------------------------------
- Binary payloads currently live in encrypted database rows; production-scale
  deployments still require external encrypted object storage, retention jobs,
  replication and disaster-recovery evidence.
- The verified model path is Chinese-only.  English/multilingual accuracy,
  diarization, multichannel timing and clinical acoustic benchmarks remain
  unverified.
- Asynchronous execution is an in-process task runner backed by durable job
  state and restart recovery, not a horizontally scalable external queue.

Legacy contract fixtures
------------------------
2 transcript items per interaction, deterministic per-UUID:

- ``transcriptSample`` is always populated (it's required).
- ``transcript`` (full data) is only populated when ``?full=true``;
  otherwise it's omitted entirely (caller shouldn't pay for it).
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.models.stt_artifact import STTTranscript
from app.config import settings
from app.services.phi_encryption import is_encryption_enabled
from app.services.stt_artifact_repository import stt_artifact_repository
from app.schemas.v2_tools_stt import (
    CommonTranscriptResponse,
    CommonUsageInfo,
    RecordingsCreateResponse,
    RecordingsListResponse,
    TranscriptsCreateRequest,
    TranscriptsData,
    TranscriptsListItem,
    TranscriptsListResponse,
    TranscriptsMetadata,
    TranscriptsParticipant,
    TranscriptsResponse,
    TranscriptsStatusResponse,
    STTReadinessResponse,
)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])

_SUPPORTED_RECORDING_MEDIA_TYPES = frozenset(
    {
        "application/octet-stream",
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
        "audio/mpeg",
        "audio/mp3",
        "audio/mpeg3",
        "audio/mp4",
        "audio/m4a",
        "audio/ogg",
        "audio/opus",
        "audio/vorbis",
        "audio/flac",
    }
)


@router.get("/stt/readiness", response_model=STTReadinessResponse)
async def get_stt_readiness(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> STTReadinessResponse:
    """Return tenant-scoped aggregate STT readiness without transcript content."""
    pending = int((await db.execute(
        select(func.count(STTTranscript.id)).where(
            STTTranscript.organization_id == current_org.id,
            STTTranscript.owner_id == current_user.id,
            STTTranscript.status == "processing",
        )
    )).scalar_one())
    local_enabled = bool(settings.ICODER_ENABLE_LOCAL_STT)
    whisper_configured = bool(settings.STT_WHISPER_MODEL.strip())
    return STTReadinessResponse(
        configuration_status=(
            "configured_not_live_verified"
            if local_enabled or whisper_configured
            else "unavailable"
        ),
        verified_languages=["zh-CN"],
        local_engine_enabled=local_enabled,
        whisper_fallback_configured=whisper_configured,
        batch_provider_priority=["funasr", "whisper"],
        recording_storage_backend="encrypted_database",
        external_object_storage_configured=False,
        at_rest_encryption_enabled=is_encryption_enabled(),
        durable_job_state=True,
        restart_recovery=True,
        queue_backend="in_process",
        horizontally_scalable_queue=False,
        pending_transcript_count=pending,
        live_health_verified=False,
        maximum_recording_bytes=150 * 1024 * 1024,
        production_ready=False,
    )


def _protocol_fixtures_enabled() -> bool:
    """Enable frozen protocol fixtures only inside an explicit pytest run.

    The fixtures contain synthetic recordings and transcript text.  An
    environment variable alone must never make those resources appear in a
    developer-started Uvicorn process, because callers could mistake them for
    persisted STT output.  Protocol conformance tests still opt in explicitly.
    """
    app_env = os.environ.get("APP_ENV", "").strip().casefold()
    return (
        app_env in {"development", "dev", "test", "testing"}
        and os.environ.get("ICODER_ENABLE_PROTOCOL_FIXTURES", "") == "1"
        and "pytest" in sys.modules
    )


def _resource_not_found(resource: str, resource_id: str, interaction_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "requestid": str(uuid.uuid4()),
            "status": 404,
            "type": f"{resource}_not_found",
            "detail": (
                f"{resource.capitalize()} {resource_id} not found for "
                f"interaction {interaction_id}."
            ),
        },
    )


def _validate_transcription_capabilities(body: TranscriptsCreateRequest) -> None:
    """Reject options the current recognizer cannot honor faithfully.

    Accepting these fields and returning a single synthetic speaker/channel
    would be worse than an explicit capability error.  The response detail is
    stable so SDK and UI clients can disable unsupported controls.
    """
    unsupported: list[str] = []
    if body.diarize:
        unsupported.append("diarize")
    spoken_punctuation, _automatic_punctuation = _resolve_punctuation_preferences(body)
    if body.automaticPunctuation is False and not spoken_punctuation:
        unsupported.append("automaticPunctuation=false")
    if body.isMultichannel:
        roles = body.participants or []
        channels = [role.channel for role in roles]
        if len(roles) != 2 or sorted(channels) != [0, 1]:
            raise HTTPException(
                status_code=422,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 422,
                    "type": "invalid_multichannel_configuration",
                    "detail": (
                        "Verified prerecorded multichannel transcription requires "
                        "exactly one participant for each channel 0 and 1."
                    ),
                },
            )
    else:
        if body.participants and len(body.participants) > 1:
            unsupported.append("participants>1")
        if body.participants and body.participants[0].channel not in {0, 1}:
            unsupported.append("participants.channel")
    if unsupported:
        raise HTTPException(
            status_code=422,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 422,
                "type": "unsupported_stt_feature",
                "detail": (
                    "The current verified Chinese STT runtime cannot faithfully "
                    "honor: " + ", ".join(unsupported) + "."
                ),
                "unsupported": unsupported,
            },
        )


def _resolve_punctuation_preferences(
    body: TranscriptsCreateRequest,
) -> tuple[bool, bool]:
    """Resolve Corti's current punctuation fields and legacy fallback.

    ``isDictation`` is ignored whenever either current field is explicitly
    supplied. Spoken punctuation takes precedence over automatic punctuation.
    """
    current_field_supplied = (
        body.spokenPunctuation is not None
        or body.automaticPunctuation is not None
    )
    spoken = (
        body.spokenPunctuation is True
        if current_field_supplied
        else body.isDictation is True
    )
    automatic = False if spoken else body.automaticPunctuation is not False
    return spoken, automatic


def _owner_id(current_user: User) -> str:
    """Return the authenticated principal scope for durable artifacts."""
    return str(getattr(current_user, "id", "anonymous"))


def _artifact_scope(
    current_user: User,
    current_org: Organization,
    interaction_id: str,
) -> dict[str, str]:
    # Organization is resolved from the verified bearer token's org_id by
    # get_current_organization. User rows intentionally do not carry a single
    # organization_id because one user may belong to multiple tenants.
    organization_id = str(getattr(current_org, "id", "") or "")
    if not organization_id:
        # get_current_user is tenant-bound in normal requests. Keep the scope
        # fail-closed even for custom dependency implementations.
        raise HTTPException(status_code=403, detail="organization_context_required")
    return {
        "organization_id": organization_id,
        "owner_id": _owner_id(current_user),
        "interaction_id": interaction_id,
    }


def _participant_models(
    roles: tuple[tuple[int, str], ...],
) -> list[TranscriptsParticipant]:
    return [TranscriptsParticipant(channel=channel, role=role) for channel, role in roles]


def _stored_transcript_response(transcript: STTTranscript) -> TranscriptsResponse:
    roles = _participant_models(stt_artifact_repository.participant_roles(transcript))
    text = stt_artifact_repository.transcript_text(transcript)
    rows = None
    if transcript.status == "completed":
        stored_segments = stt_artifact_repository.transcript_segments(transcript)
        if stored_segments:
            rows = [CommonTranscriptResponse.model_validate(item) for item in stored_segments]
        else:
            rows = [
                CommonTranscriptResponse(
                    channel=roles[0].channel if roles else 1,
                    participant=1,
                    speakerId=1,
                    text=text,
                    start=0,
                    end=0,
                )
            ]
    return TranscriptsResponse(
        id=transcript.transcript_id,
        metadata=TranscriptsMetadata(participantsRoles=roles or None),
        transcripts=rows,
        usageInfo=CommonUsageInfo(creditsConsumed=0.0),
        recordingId=transcript.recording_id,
        status=transcript.status,
    )


def _stored_transcript_list_item(
    transcript: STTTranscript,
    *,
    full: bool,
) -> TranscriptsListItem:
    response = _stored_transcript_response(transcript)
    data = None
    if full:
        data = TranscriptsData(
            metadata=response.metadata,
            transcripts=response.transcripts or [],
        )
    return TranscriptsListItem(
        id=transcript.transcript_id,
        transcriptSample=stt_artifact_repository.transcript_text(transcript)[:240],
        transcript=data,
    )


# ─── Frozen legacy contract fixtures (never used for new stored artifacts) ────


def _protocol_fixture_transcripts(
    interaction_id: str, full: bool
) -> Optional[List[TranscriptsListItem]]:
    """Deterministic OpenAPI contract fixture for explicit dev tests.

    Returns ``None`` when the interaction_id is the special sentinel
    ``empty-{uuid}`` so callers can verify the spec's nullable
    envelope field. Otherwise returns a 2-item list with full data
    populated iff ``full=True``.
    """
    if interaction_id.startswith("empty-"):
        # Spec says transcripts field is nullable — exercise that path.
        return None

    items: List[TranscriptsListItem] = [
        TranscriptsListItem(
            id=f"{interaction_id}-tr-0001",
            transcriptSample="Patient reports chest tightness for the past 3 days.",
            transcript=TranscriptsData(
                metadata=TranscriptsMetadata(
                    participantsRoles=[
                        TranscriptsParticipant(channel=1, role="patient"),
                        TranscriptsParticipant(channel=1, role="doctor"),
                    ],
                ),
                transcripts=[
                    CommonTranscriptResponse(
                        channel=1, participant=1, speakerId=1,
                        text="I've been having chest tightness for about three days now.",
                        start=0, end=4200,
                    ),
                    CommonTranscriptResponse(
                        channel=1, participant=2, speakerId=2,
                        text="Can you describe the pain — is it sharp or dull?",
                        start=4500, end=7200,
                    ),
                ],
            ) if full else None,
        ),
        TranscriptsListItem(
            id=f"{interaction_id}-tr-0002",
            transcriptSample="Doctor orders EKG and recommends follow-up.",
            transcript=TranscriptsData(
                metadata=TranscriptsMetadata(
                    participantsRoles=[
                        TranscriptsParticipant(channel=1, role="patient"),
                        TranscriptsParticipant(channel=1, role="doctor"),
                    ],
                ),
                transcripts=[
                    CommonTranscriptResponse(
                        channel=1, participant=2, speakerId=2,
                        text="Let's get an EKG and schedule a follow-up in two weeks.",
                        start=15000, end=18500,
                    ),
                ],
            ) if full else None,
        ),
    ]
    return items


# ─── Endpoint ────────────────────────────────────────────────────────


@router.get(
    "/interactions/{interaction_id}/transcripts/",
    response_model=TranscriptsListResponse,
    status_code=200,
)
@router.get(
    "/interactions/{interaction_id}/transcripts",
    response_model=TranscriptsListResponse,
    status_code=200,
)
async def list_v2_tools_interaction_transcripts(
    interaction_id: str,
    full: bool = Query(default=False, description="Display full transcripts in listing"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TranscriptsListResponse:
    """Corti §13.3 Transcripts — ``GET /interactions/{id}/transcripts/``.

    Path-scoped to a single interaction UUID. Supports ``?full=true``
    to include the full transcript payload (channel/participant/text/
    start/end rows) alongside the always-present ``transcriptSample``.

    Per spec, ``transcripts`` may be ``null`` (e.g. for an interaction
    with no transcripts). The walker test verifies this nullable
    contract.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )

    scope = _artifact_scope(current_user, current_org, interaction_id)
    if await stt_artifact_repository.is_materialized(db, **scope):
        transcripts = await stt_artifact_repository.list_transcripts(db, **scope)
        return TranscriptsListResponse(
            transcripts=[
                _stored_transcript_list_item(item, full=full)
                for item in transcripts
            ]
        )

    if _protocol_fixtures_enabled():
        return TranscriptsListResponse(
            transcripts=_protocol_fixture_transcripts(interaction_id, full=full),
        )
    return TranscriptsListResponse(transcripts=[])


# ─── Frozen protocol fixtures (explicit dev-test mode only) ─────────


def _protocol_fixture_transcript(
    interaction_id: str, transcript_id: str
) -> TranscriptsResponse:
    """Deterministic single-transcript OpenAPI fixture.

    Three transcript states are exercised via transcript_id sentinel:
    - ``completed`` (or any non-sentinel) → status=completed with full
      transcripts[] rows.
    - ``processing-{uuid}`` → status=processing, transcripts=null
      (exercises the nullable contract while not-yet-finalized).
    - ``failed-{uuid}`` → status=failed, transcripts=null.

    The path UUIDs are echoed into id/recordingId so SDK callers can
    verify the contract.
    """
    if transcript_id.startswith("processing-"):
        return TranscriptsResponse(
            id=transcript_id,
            metadata=TranscriptsMetadata(
                participantsRoles=[
                    TranscriptsParticipant(channel=1, role="patient"),
                    TranscriptsParticipant(channel=1, role="doctor"),
                ],
            ),
            transcripts=None,
            usageInfo=CommonUsageInfo(creditsConsumed=0.0),
            recordingId=f"{interaction_id}-rec-stub",
            status="processing",
        )
    if transcript_id.startswith("failed-"):
        return TranscriptsResponse(
            id=transcript_id,
            metadata=TranscriptsMetadata(participantsRoles=None),
            transcripts=None,
            usageInfo=CommonUsageInfo(creditsConsumed=0.0),
            recordingId=f"{interaction_id}-rec-stub",
            status="failed",
        )
    # default: completed with full transcript payload
    return TranscriptsResponse(
        id=transcript_id,
        metadata=TranscriptsMetadata(
            participantsRoles=[
                TranscriptsParticipant(channel=1, role="patient"),
                TranscriptsParticipant(channel=1, role="doctor"),
            ],
        ),
        transcripts=[
            CommonTranscriptResponse(
                channel=1, participant=1, speakerId=1,
                text="I've been having chest tightness for about three days now.",
                start=0, end=4200,
            ),
            CommonTranscriptResponse(
                channel=1, participant=2, speakerId=2,
                text="Can you describe the pain — is it sharp or dull?",
                start=4500, end=7200,
            ),
            CommonTranscriptResponse(
                channel=1, participant=2, speakerId=2,
                text="Let's get an EKG and schedule a follow-up in two weeks.",
                start=15000, end=18500,
            ),
        ],
        usageInfo=CommonUsageInfo(creditsConsumed=0.018),
        recordingId=f"{interaction_id}-rec-stub",
        status="completed",
    )


# ─── Endpoint: get-transcript (cycle 7) ──────────────────────────────


@router.get(
    "/interactions/{interaction_id}/transcripts/{transcript_id}",
    response_model=TranscriptsResponse,
    status_code=200,
)
async def get_v2_tools_interaction_transcript(
    interaction_id: str,
    transcript_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TranscriptsResponse:
    """Corti §13.3 Transcripts — ``GET /interactions/{id}/transcripts/{transcriptId}``.

    Returns the single full transcript envelope (always-full payload,
    no ``?full=`` toggle — the cycle-6 LIST endpoint is for discovery;
    cycle-7 get returns the canonical single-transcript body).

    The ``status`` field reflects processing state. ``transcripts`` is
    ``null`` while status is ``processing`` or ``failed`` per spec.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )
    if not transcript_id or not transcript_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "transcript_id is required.",
            },
        )

    scope = _artifact_scope(current_user, current_org, interaction_id)
    stored = await stt_artifact_repository.get_transcript(
        db, **scope, transcript_id=transcript_id
    )
    if stored is not None:
        return _stored_transcript_response(stored)
    if _protocol_fixtures_enabled():
        return _protocol_fixture_transcript(interaction_id, transcript_id)
    raise _resource_not_found("transcript", transcript_id, interaction_id)


# ─── Frozen create-transcript protocol fixture ──────────────────────


def _protocol_fixture_created_transcript(
    interaction_id: str, body: TranscriptsCreateRequest
) -> TranscriptsResponse:
    """Deterministic create-transcript OpenAPI fixture.

    Cycle 8 stub mimics the synchronous path: 201 + populated
    TranscriptsResponse. Echoes ``recordingId`` from the request body
    so callers can verify the body→response contract. Generates a fresh
    transcript id derived from the interaction_id + recordingId so the
    contract is testable.

    Async mode (``async: true``) is not yet wired — the stub still
    returns 201 synchronously. The async dispatch path is a separate
    Phase 1.3 task.
    """
    return TranscriptsResponse(
        id=f"{interaction_id}-tr-{body.recordingId[-12:]}",
        metadata=TranscriptsMetadata(
            participantsRoles=body.participants or [
                TranscriptsParticipant(channel=1, role="doctor"),
                TranscriptsParticipant(channel=2, role="patient"),
            ],
        ),
        transcripts=[
            CommonTranscriptResponse(
                channel=1, participant=1, speakerId=1,
                text="(stub) Created transcript from recording — replace with real STT in a later cycle.",
                start=0, end=1500,
            ),
        ],
        usageInfo=CommonUsageInfo(creditsConsumed=0.024),
        recordingId=body.recordingId,
        status="completed",
    )


# ─── Endpoint: create-transcript (cycle 8) ──────────────────────────


@router.post(
    "/interactions/{interaction_id}/transcripts/",
    response_model=TranscriptsResponse,
    status_code=201,
    responses={
        202: {
            "model": TranscriptsResponse,
            "description": "Accepted for asynchronous transcription",
        }
    },
)
@router.post(
    "/interactions/{interaction_id}/transcripts",
    response_model=TranscriptsResponse,
    status_code=201,
    responses={
        202: {
            "model": TranscriptsResponse,
            "description": "Accepted for asynchronous transcription",
        }
    },
)
async def create_v2_tools_interaction_transcript(
    interaction_id: str,
    body: TranscriptsCreateRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TranscriptsResponse:
    """Corti §13.3 Transcripts — ``POST /interactions/{id}/transcripts/``.

    First STT mutation endpoint. Accepts a JSON body
    (``TranscriptsCreateRequest``) and returns 201 + the canonical
    ``TranscriptsResponse`` shape.

    Required body fields: ``recordingId`` (UUID of a recording uploaded
    via ``/recordings``), ``primaryLanguage`` (e.g. ``"en"``). Optional
    knobs: ``spokenPunctuation``, ``automaticPunctuation``,
    ``isDictation``, ``isMultichannel``, ``diarize``,
    ``participants``, ``async``, ``replacements``, ``keyterms``.

    Per Corti spec, the response echoes ``recordingId`` and synthesizes
    a fresh transcript id. Stored recordings use the real synchronous or
    durable asynchronous path; the fixture branch is explicit dev-test only.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )

    scope = _artifact_scope(current_user, current_org, interaction_id)
    recording = await stt_artifact_repository.get_recording(
        db, **scope, recording_id=body.recordingId
    )
    if recording is not None:
        _validate_transcription_capabilities(body)
        if not body.primaryLanguage.lower().startswith("zh"):
            raise HTTPException(
                status_code=422,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 422,
                    "type": "unsupported_language",
                    "detail": "The local verified STT pipeline currently supports Chinese audio only.",
                },
            )

        # Do not invent clinician/patient roles without diarization evidence.
        roles = body.participants or []
        spoken_punctuation, automatic_punctuation = _resolve_punctuation_preferences(body)
        request_data = {
            "primaryLanguage": body.primaryLanguage,
            "automaticPunctuation": automatic_punctuation,
            "spokenPunctuation": spoken_punctuation,
            "isDictation": bool(body.isDictation),
            "isMultichannel": body.isMultichannel is True,
            "replacements": [
                {"find": item.find, "replace": item.replace}
                for item in body.replacements or []
            ],
            # Keyterms can include names and clinical vocabulary. Keep them
            # only inside the encrypted request payload and never log them.
            "keyterms": [item.term for item in body.keyterms.terms]
            if body.keyterms is not None
            else [],
        }
        recording_content = stt_artifact_repository.recording_content(recording)
        if body.isMultichannel:
            from app.services.prerecorded_media_decoder import (
                PrerecordedMediaDecoderError,
            )
            from app.services.stt_service import (
                validate_prerecorded_multichannel_audio,
            )

            try:
                await validate_prerecorded_multichannel_audio(
                    recording_content,
                    recording.media_type,
                    expected_channels=2,
                )
            except PrerecordedMediaDecoderError as exc:
                status_code = 503 if exc.transient else 422
                raise HTTPException(
                    status_code=status_code,
                    detail={
                        "requestid": str(uuid.uuid4()),
                        "status": status_code,
                        "type": (
                            "stt_media_decoder_unavailable"
                            if exc.transient
                            else "invalid_multichannel_audio"
                        ),
                        "detail": (
                            "The isolated prerecorded media decoder is temporarily unavailable."
                            if exc.transient
                            else (
                                "Multichannel audio must be a supported declared container "
                                "with exactly two aligned audio channels and no more than "
                                "120 minutes of duration."
                            )
                        ),
                        "reason": exc.reason,
                    },
                ) from None
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "requestid": str(uuid.uuid4()),
                        "status": 422,
                        "type": "invalid_multichannel_audio",
                        "detail": (
                            "PCM WAV multichannel transcription requires aligned stereo "
                            "16 kHz, 16-bit audio. Supported encoded containers are probed "
                            "and decoded by the isolated media worker."
                        ),
                        "reason": str(exc),
                    },
                ) from None
        if body.async_:
            transcript = await stt_artifact_repository.put_transcript(
                db,
                **scope,
                transcript_id=str(uuid.uuid4()),
                recording_id=body.recordingId,
                text=None,
                status="processing",
                participant_roles=tuple((role.channel, role.role) for role in roles),
                request_data=request_data,
            )
            # The background worker opens a fresh session and therefore needs
            # the durable job row committed before it is scheduled.
            await db.commit()
            from app.services.stt_jobs import process_stt_transcript_job

            background_tasks.add_task(
                process_stt_transcript_job,
                scope["organization_id"],
                scope["owner_id"],
                interaction_id,
                transcript.transcript_id,
            )
            response.status_code = 202
            response.headers["Location"] = (
                f"/api/v2/tools/interactions/{interaction_id}/transcripts/"
                f"{transcript.transcript_id}/status"
            )
            return _stored_transcript_response(transcript)

        from app.services.stt_service import (
            apply_dictation_punctuation,
            apply_requested_replacements,
            transcribe_bytes_with_telemetry,
            transcribe_multichannel_bytes_with_telemetry,
        )

        transcript_segments: tuple[dict[str, object], ...] | None = None
        text: str | None = None
        if body.isMultichannel:
            channel_rows, error, runtime_telemetry = (
                await transcribe_multichannel_bytes_with_telemetry(
                    recording_content,
                    recording.media_type,
                    expected_channels=2,
                    keyterms=tuple(request_data["keyterms"]),
                )
            )
            if channel_rows:
                transcript_segments = tuple(
                    {
                        "channel": item.channel,
                        "participant": item.channel,
                        "speakerId": -1,
                        "text": apply_requested_replacements(
                            apply_dictation_punctuation(
                                item.text,
                                primary_language=request_data["primaryLanguage"],
                                enabled=request_data["spokenPunctuation"],
                            ),
                            request_data["replacements"],
                        ),
                        "start": item.start_ms,
                        "end": item.end_ms,
                    }
                    for item in channel_rows
                )
        else:
            text, error, runtime_telemetry = await transcribe_bytes_with_telemetry(
                recording_content,
                recording.media_type,
                keyterms=tuple(request_data["keyterms"]),
            )
            if text:
                text = apply_dictation_punctuation(
                    text,
                    primary_language=request_data["primaryLanguage"],
                    enabled=request_data["spokenPunctuation"],
                )
                text = apply_requested_replacements(text, request_data["replacements"])
        if not text and not transcript_segments:
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "stt_unavailable",
                    "detail": error or "The configured STT engine returned no transcript.",
                },
            )

        transcript = await stt_artifact_repository.put_transcript(
            db,
            **scope,
            transcript_id=str(uuid.uuid4()),
            recording_id=body.recordingId,
            text=text,
            transcript_segments=transcript_segments,
            status="completed",
            participant_roles=tuple((role.channel, role.role) for role in roles),
            request_data=request_data,
        )
        await stt_artifact_repository.set_transcript_runtime_telemetry(
            db, transcript, runtime_telemetry
        )
        return _stored_transcript_response(transcript)
    if (
        await stt_artifact_repository.is_materialized(db, **scope)
        and body.recordingId.startswith(f"{interaction_id}-rec-")
    ):
        raise HTTPException(
            status_code=404,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 404,
                "type": "recording_not_found",
                "detail": f"Recording {body.recordingId} not found for interaction {interaction_id}.",
            },
        )

    if _protocol_fixtures_enabled():
        return _protocol_fixture_created_transcript(interaction_id, body)
    raise _resource_not_found("recording", body.recordingId, interaction_id)


# ─── Frozen list-recordings protocol fixture ────────────────────────


def _protocol_fixture_recordings(interaction_id: str) -> List[str]:
    """Deterministic OpenAPI fixture recordings per interaction UUID.

    Returns an empty list when ``interaction_id`` is the special
    sentinel ``empty-{uuid}`` (exercises the spec's array-empty contract).
    Otherwise returns 2 deterministic UUIDs derived from the
    interaction_id (path-echo pattern, mirrors cycle-6 transcripts).

    Unlike transcripts list (cycle 6), this envelope's ``recordings``
    field is NOT ``nullable: true`` per spec — empty list is the
    canonical "no recordings" signal.
    """
    if interaction_id.startswith("empty-"):
        return []

    # Two deterministic UUIDs — first segment echoes the interaction_id
    # so the path-scoping contract is testable.
    prefix = interaction_id.replace("-", "")[:8]
    return [
        f"{prefix}-1111-2222-3333-444444444444",
        f"{prefix}-aaaa-bbbb-cccc-dddddddddddd",
    ]


# ─── Endpoint: list-recordings (cycle 9) ────────────────────────────


@router.get(
    "/interactions/{interaction_id}/recordings/",
    response_model=RecordingsListResponse,
    status_code=200,
)
@router.get(
    "/interactions/{interaction_id}/recordings",
    response_model=RecordingsListResponse,
    status_code=200,
)
async def list_v2_tools_interaction_recordings(
    interaction_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> RecordingsListResponse:
    """Corti §13.3 Recordings — ``GET /interactions/{id}/recordings/``.

    Returns the canonical list of recording UUIDs for the interaction.
    Per spec, the envelope's ``recordings`` field is a non-nullable
    array of UUID strings (empty list when the interaction has no
    recordings; ``null`` is not valid).

    Path-scoped to a single interaction UUID.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )

    scope = _artifact_scope(current_user, current_org, interaction_id)
    if await stt_artifact_repository.is_materialized(db, **scope):
        recordings = await stt_artifact_repository.list_recordings(db, **scope)
        return RecordingsListResponse(
            recordings=[recording.recording_id for recording in recordings]
        )

    if _protocol_fixtures_enabled():
        return RecordingsListResponse(
            recordings=_protocol_fixture_recordings(interaction_id),
        )
    return RecordingsListResponse(recordings=[])


# ─── Endpoint: upload-recording (cycle 10) ──────────────────────────


# Corti §13.3 hard cap: 120 minutes audio / 150 MB file size.
# The upload handler enforces this limit before persisting encrypted bytes.
_MAX_RECORDING_BYTES = 150 * 1024 * 1024  # 150 MB


@router.post(
    "/interactions/{interaction_id}/recordings/",
    response_model=RecordingsCreateResponse,
    status_code=201,
    responses={
        413: {"description": "Recording exceeds the 150 MB upload limit"},
        415: {"description": "Unsupported recording media type"},
    },
)
@router.post(
    "/interactions/{interaction_id}/recordings",
    response_model=RecordingsCreateResponse,
    status_code=201,
    responses={
        413: {"description": "Recording exceeds the 150 MB upload limit"},
        415: {"description": "Unsupported recording media type"},
    },
)
async def upload_v2_tools_interaction_recording(
    interaction_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> RecordingsCreateResponse:
    """Corti §13.3 Recordings — ``POST /interactions/{id}/recordings/``.

    Accepts an ``application/octet-stream`` body (raw audio binary) and
    returns 201 + the canonical ``RecordingsCreateResponse {recordingId}``
    shape.

    Per spec, max 120 minutes of audio / 150 MB file size. The real handler
    enforces the byte cap before encrypted persistence.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )

    raw_media_type = request.headers.get("content-type", "application/octet-stream")
    media_type = raw_media_type.split(";", 1)[0].strip().casefold()
    if media_type not in _SUPPORTED_RECORDING_MEDIA_TYPES:
        raise HTTPException(
            status_code=415,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 415,
                "type": "unsupported_media_type",
                "detail": f"Unsupported recording Content-Type: {media_type or '<empty>'}.",
            },
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_length = int(content_length)
        except ValueError:
            declared_length = -1
        if declared_length < 0:
            raise HTTPException(status_code=400, detail="invalid_content_length")
        if declared_length > _MAX_RECORDING_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 413,
                    "type": "recording_too_large",
                    "detail": "Recording exceeds 150 MB cap.",
                },
            )

    chunks: list[bytes] = []
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > _MAX_RECORDING_BYTES:
            raise HTTPException(
                status_code=413,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 413,
                    "type": "recording_too_large",
                    "detail": "Recording exceeds 150 MB cap.",
                },
            )
        chunks.append(chunk)
    body = b"".join(chunks)
    if not body:
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "Recording body is required (application/octet-stream).",
            },
        )
    recording_id = f"{interaction_id}-rec-{uuid.uuid4()}"
    await stt_artifact_repository.put_recording(
        db,
        **_artifact_scope(current_user, current_org, interaction_id),
        recording_id=recording_id,
        content=body,
        media_type=media_type,
    )
    return RecordingsCreateResponse(recordingId=recording_id)


# ─── Endpoint: get-recording (cycle 11) ─────────────────────────────


# Per Corti spec, get-recording returns raw binary (text/plain +
# format: binary). The second non-JSON response in iCoDer's v2 surface.
_PROTOCOL_FIXTURE_RECORDING_BYTES = b"\x00" * 64


@router.get(
    "/interactions/{interaction_id}/recordings/{recording_id}",
    status_code=200,
    response_class=Response,
)
async def get_v2_tools_interaction_recording(
    interaction_id: str,
    recording_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Corti §13.3 Recordings — ``GET /interactions/{id}/recordings/{recordingId}``.

    Returns the raw binary content of the recording file
    (``text/plain`` + ``format: binary`` per Corti spec). The second
    non-JSON response in iCoDer's v2 surface.

    Unknown resources return 404. Synthetic bytes are available only when the
    explicitly enabled development-only protocol fixture mode is active.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )
    if not recording_id or not recording_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "recording_id is required.",
            },
        )

    scope = _artifact_scope(current_user, current_org, interaction_id)
    stored = await stt_artifact_repository.get_recording(
        db, **scope, recording_id=recording_id
    )
    if stored is not None:
        return Response(
            content=stt_artifact_repository.recording_content(stored),
            media_type=stored.media_type,
            headers={
                "X-Recording-Id": recording_id,
                "X-Interaction-Id": interaction_id,
                "Cache-Control": "no-store",
            },
        )
    if (
        await stt_artifact_repository.is_materialized(db, **scope)
        and recording_id.startswith(f"{interaction_id}-rec-")
    ):
        raise HTTPException(
            status_code=404,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 404,
                "type": "recording_not_found",
                "detail": f"Recording {recording_id} not found for interaction {interaction_id}.",
            },
        )

    if recording_id.startswith("missing-"):
        raise HTTPException(
            status_code=404,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 404,
                "type": "recording_not_found",
                "detail": f"Recording {recording_id} not found for interaction {interaction_id}.",
            },
        )

    if _protocol_fixtures_enabled():
        return Response(
            content=_PROTOCOL_FIXTURE_RECORDING_BYTES,
            media_type="text/plain",
            headers={
                "X-Stub-Recording-Id": recording_id,
                "X-Stub-Interaction-Id": interaction_id,
            },
        )
    raise _resource_not_found("recording", recording_id, interaction_id)


# ─── Endpoint: delete-recording (cycle 12) ───────────────────────────


@router.delete(
    "/interactions/{interaction_id}/recordings/{recording_id}",
    status_code=204,
)
async def delete_v2_tools_interaction_recording(
    interaction_id: str,
    recording_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Corti §13.3 Recordings — ``DELETE /interactions/{id}/recordings/{recordingId}``.

    Returns **204 No Content** after deleting the tenant-scoped database row.

    Unknown materialized resources return 404; explicit dev fixtures retain
    their legacy idempotent contract behavior.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )
    if not recording_id or not recording_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "recording_id is required.",
            },
        )

    scope = _artifact_scope(current_user, current_org, interaction_id)
    if await stt_artifact_repository.delete_recording(
        db, **scope, recording_id=recording_id
    ):
        return Response(status_code=204)
    if (
        await stt_artifact_repository.is_materialized(db, **scope)
        and recording_id.startswith(f"{interaction_id}-rec-")
    ):
        raise HTTPException(
            status_code=404,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 404,
                "type": "recording_not_found",
                "detail": f"Recording {recording_id} not found for interaction {interaction_id}.",
            },
        )

    if recording_id.startswith("missing-"):
        raise HTTPException(
            status_code=404,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 404,
                "type": "recording_not_found",
                "detail": f"Recording {recording_id} not found for interaction {interaction_id}.",
            },
        )

    if _protocol_fixtures_enabled():
        return Response(status_code=204)
    raise _resource_not_found("recording", recording_id, interaction_id)


# ─── Endpoint: get-transcript-status (cycle 12.1) ────────────────────


@router.get(
    "/interactions/{interaction_id}/transcripts/{transcript_id}/status",
    response_model=TranscriptsStatusResponse,
    status_code=200,
)
async def get_v2_tools_interaction_transcript_status(
    interaction_id: str,
    transcript_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TranscriptsStatusResponse:
    """Corti §13.3 Transcripts — ``GET /interactions/{id}/transcripts/{transcriptId}/status``.

    Polls the transcript processing status. Lighter-weight than cycle-7's
    get-transcript (only returns ``status``, not the full transcript body).
    Designed for polling async transcription jobs (cycle-8's
    create-transcript with ``async: true``).

    Sentinel pattern (reuses cycle-7's transcript state sentinels):
    - ``processing-{uuid}`` → status="processing"
    - ``failed-{uuid}`` → status="failed"
    - ``missing-{uuid}`` → 404 (new for cycle 12.1)
    - default → status="completed"
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )
    if not transcript_id or not transcript_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "transcript_id is required.",
            },
        )

    scope = _artifact_scope(current_user, current_org, interaction_id)
    stored = await stt_artifact_repository.get_transcript(
        db, **scope, transcript_id=transcript_id
    )
    if stored is not None:
        return TranscriptsStatusResponse(status=stored.status)
    if transcript_id.startswith("missing-"):
        raise HTTPException(
            status_code=404,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 404,
                "type": "transcript_not_found",
                "detail": f"Transcript {transcript_id} not found for interaction {interaction_id}.",
            },
        )

    if _protocol_fixtures_enabled():
        if transcript_id.startswith("processing-"):
            return TranscriptsStatusResponse(status="processing")
        if transcript_id.startswith("failed-"):
            return TranscriptsStatusResponse(status="failed")
        return TranscriptsStatusResponse(status="completed")
    raise _resource_not_found("transcript", transcript_id, interaction_id)


# ─── Endpoint: delete-transcript (cycle 12.2, last STT endpoint) ────


@router.delete(
    "/interactions/{interaction_id}/transcripts/{transcript_id}",
    status_code=204,
)
async def delete_v2_tools_interaction_transcript(
    interaction_id: str,
    transcript_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Corti §13.3 Transcripts — ``DELETE /interactions/{id}/transcripts/{transcriptId}``.

    Returns **204 No Content** after deleting the tenant-scoped database row.
    Explicit development-only protocol fixtures retain idempotent deletion;
    normal runtime never fabricates a transcript resource.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )
    if not transcript_id or not transcript_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "transcript_id is required.",
            },
        )

    scope = _artifact_scope(current_user, current_org, interaction_id)
    if await stt_artifact_repository.delete_transcript(
        db, **scope, transcript_id=transcript_id
    ):
        return Response(status_code=204)
    if await stt_artifact_repository.is_materialized(db, **scope):
        return Response(status_code=204)

    if _protocol_fixtures_enabled():
        return Response(status_code=204)
    raise _resource_not_found("transcript", transcript_id, interaction_id)
