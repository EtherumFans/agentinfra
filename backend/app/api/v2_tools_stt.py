"""iCoDer ``GET /api/v2/tools/interactions/{id}/transcripts/`` — Corti §13.3 STT LIST.

Cycle 6 (2026-07-01) — wire-shape parity for the §13.3 STT list-transcripts
endpoint. The STT family has 9 endpoints total (5 transcripts + 4
recordings); cycle 6 closes only the LIST for transcripts.

Spec source (ground truth, never inferred):
- ``docs/corti-reverse-engineered/stt-list-transcripts.md`` (7,962 bytes,
  fetched 2026-07-01 from
  ``https://docs.corti.ai/api-reference/transcripts/list-transcripts.md``).
  Path: ``GET /interactions/{id}/transcripts/`` → operationId
  ``transcripts_list``.

What this endpoint IS
---------------------
- A read-only LIST endpoint returning the Corti §13.3 transcripts
  envelope ``{transcripts: TranscriptsListItem[] | null}`` for a
  single interaction. Supports ``?full=true`` to include the full
  transcript payload (channel/participant/text/start/end rows).

What this endpoint is NOT
--------------------------
- NOT a real STT surface. Cycle 6 ships stub data only — iCoDer does
  not have actual STT processing yet (the legacy ``/ws/speech-to-text``
  WSS surface is unrelated). Real STT integration is a separate Phase
  1.3 task; until then this LIST is intentionally empty-feeling.
- NOT a CRUD surface. The other 4 transcript endpoints (create, delete,
  get, get-status) and 4 recording endpoints land in cycles 7+.

Stub data
---------
2 transcript items per interaction, deterministic per-UUID:

- ``transcriptSample`` is always populated (it's required).
- ``transcript`` (full data) is only populated when ``?full=true``;
  otherwise it's omitted entirely (caller shouldn't pay for it).
"""

from __future__ import annotations

import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.middleware.auth import get_current_user
from app.models.user import User
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
)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])


# ─── Stub data (Cycle 6; replaced by real STT in a later cycle) ────


def _stub_transcripts_for_interaction(
    interaction_id: str, full: bool
) -> Optional[List[TranscriptsListItem]]:
    """Deterministic stub data per interaction UUID.

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

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    return TranscriptsListResponse(
        transcripts=_stub_transcripts_for_interaction(interaction_id, full=full),
    )


# ─── Stub data (Cycle 7) ─────────────────────────────────────────────


def _stub_single_transcript(
    interaction_id: str, transcript_id: str
) -> TranscriptsResponse:
    """Deterministic stub for a single transcript.

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

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    return _stub_single_transcript(interaction_id, transcript_id)


# ─── Stub data (Cycle 8 — create-transcript) ────────────────────────


def _stub_create_transcript(
    interaction_id: str, body: TranscriptsCreateRequest
) -> TranscriptsResponse:
    """Deterministic stub for create-transcript (sync mode).

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
)
@router.post(
    "/interactions/{interaction_id}/transcripts",
    response_model=TranscriptsResponse,
    status_code=201,
)
async def create_v2_tools_interaction_transcript(
    interaction_id: str,
    body: TranscriptsCreateRequest,
    current_user: User = Depends(get_current_user),
) -> TranscriptsResponse:
    """Corti §13.3 Transcripts — ``POST /interactions/{id}/transcripts/``.

    First STT mutation endpoint. Accepts a JSON body
    (``TranscriptsCreateRequest``) and returns 201 + the canonical
    ``TranscriptsResponse`` shape.

    Required body fields: ``recordingId`` (UUID of a recording uploaded
    via ``/recordings``), ``primaryLanguage`` (e.g. ``"en"``). Optional
    knobs: ``spokenPunctuation``, ``automaticPunctuation``,
    ``isDictation`` (deprecated), ``isMultichannel``, ``diarize``,
    ``participants``, ``async``, ``replacements``, ``keyterms``.

    Per Corti spec, the response echoes ``recordingId`` and synthesizes
    a fresh transcript id. The stub mimics the **synchronous** path —
    real async processing is a separate Phase 1.3 task.
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

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    return _stub_create_transcript(interaction_id, body)


# ─── Stub data (Cycle 9 — list-recordings) ──────────────────────────


def _stub_recordings_for_interaction(interaction_id: str) -> List[str]:
    """Deterministic stub data per interaction UUID.

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

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    return RecordingsListResponse(
        recordings=_stub_recordings_for_interaction(interaction_id),
    )


# ─── Endpoint: upload-recording (cycle 10) ──────────────────────────


# Corti §13.3 hard cap: 120 minutes audio / 150 MB file size.
# We accept and document the limit but stub does not enforce it.
_MAX_RECORDING_BYTES = 150 * 1024 * 1024  # 150 MB


@router.post(
    "/interactions/{interaction_id}/recordings/",
    response_model=RecordingsCreateResponse,
    status_code=201,
)
@router.post(
    "/interactions/{interaction_id}/recordings",
    response_model=RecordingsCreateResponse,
    status_code=201,
)
async def upload_v2_tools_interaction_recording(
    interaction_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> RecordingsCreateResponse:
    """Corti §13.3 Recordings — ``POST /interactions/{id}/recordings/``.

    Accepts an ``application/octet-stream`` body (raw audio binary) and
    returns 201 + the canonical ``RecordingsCreateResponse {recordingId}``
    shape.

    Per spec, max 120 minutes of audio / 150 MB file size. The stub does
    not enforce these limits (real implementation would validate).
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

    body = await request.body()
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
    if len(body) > _MAX_RECORDING_BYTES:
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": f"Recording exceeds 150 MB cap (got {len(body)} bytes).",
            },
        )

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    return RecordingsCreateResponse(
        recordingId=f"{interaction_id}-rec-stub",
    )


# ─── Endpoint: get-recording (cycle 11) ─────────────────────────────


# Per Corti spec, get-recording returns raw binary (text/plain +
# format: binary). The second non-JSON response in iCoDer's v2 surface.
_STUB_RECORDING_BYTES = b"\x00" * 64  # tiny placeholder


@router.get(
    "/interactions/{interaction_id}/recordings/{recording_id}",
    status_code=200,
    response_class=Response,
)
async def get_v2_tools_interaction_recording(
    interaction_id: str,
    recording_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Corti §13.3 Recordings — ``GET /interactions/{id}/recordings/{recordingId}``.

    Returns the raw binary content of the recording file
    (``text/plain`` + ``format: binary`` per Corti spec). The second
    non-JSON response in iCoDer's v2 surface.

    Sentinel pattern:
    - ``missing-{uuid}`` → 404 ``recording_not_found``.
    - Default → 200 + small synthetic audio bytes (real audio storage
      is a separate Phase 1.3 task).
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

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    return Response(
        content=_STUB_RECORDING_BYTES,
        media_type="text/plain",
        headers={
            "X-Stub-Recording-Id": recording_id,
            "X-Stub-Interaction-Id": interaction_id,
        },
    )


# ─── Endpoint: delete-recording (cycle 12) ───────────────────────────


@router.delete(
    "/interactions/{interaction_id}/recordings/{recording_id}",
    status_code=204,
)
async def delete_v2_tools_interaction_recording(
    interaction_id: str,
    recording_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Corti §13.3 Recordings — ``DELETE /interactions/{id}/recordings/{recordingId}``.

    Returns **204 No Content** on success (no body). Stub does not
    actually delete anything (no DB).

    Sentinel pattern:
    - ``missing-{uuid}`` → 404 ``recording_not_found`` (mirrors cycle-11).
    - Default → 204 No Content.

    Closes the **recordings family** (4 of 4 endpoints).
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

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    # Stub: nothing to delete (no DB). Return 204 No Content.
    return Response(status_code=204)


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

    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 503,
                    "type": "service_unavailable",
                    "detail": "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to serve.",
                },
            )

    if transcript_id.startswith("processing-"):
        return TranscriptsStatusResponse(status="processing")
    if transcript_id.startswith("failed-"):
        return TranscriptsStatusResponse(status="failed")
    return TranscriptsStatusResponse(status="completed")