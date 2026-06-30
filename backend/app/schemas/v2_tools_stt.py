"""Corti §13.3 Transcripts (STT) — list shape (Cycle 6).

Cycle 6 (2026-07-01) — LIST endpoint for the §13.3 STT family. The full
STT family has 9 endpoints (5 transcripts + 4 recordings); cycle 6
closes only the LIST for transcripts.

Spec source (ground truth, never inferred):
- ``docs/corti-reverse-engineered/stt-list-transcripts.md`` (7,962 bytes,
  fetched 2026-07-01 from
  ``https://docs.corti.ai/api-reference/transcripts/list-transcripts.md``).
  Path: ``GET /interactions/{id}/transcripts/`` → operationId
  ``transcripts_list``. Optional query param: ``full=true|false``.

Cycle 6 deliberately closes **only the read path** (list-transcripts).
The other 8 STT endpoints (create-transcript, delete-transcript,
get-transcript, get-transcript-status; delete-recording,
get-recording, list-recordings, upload-recording) land in cycles 7+.

Notable spec semantics
----------------------
- The response envelope field ``transcripts`` is declared
  ``nullable: true`` (unusual — most envelope arrays are not nullable).
  The walker must honor this.
- Each ``TranscriptsListItem`` requires ``id`` + ``transcriptSample``;
  ``transcript`` (full data) is nullable and only populated when the
  caller passes ``?full=true``.
- The full data includes ``TranscriptsData {metadata, transcripts[]}``
  with each ``CommonTranscriptResponse`` carrying channel/participant/
  speakerId/text/start/end.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ─── CommonTranscriptResponse ───────────────────────────────────────


class CommonTranscriptResponse(BaseModel):
    """``CommonTranscriptResponse`` schema — single transcript utterance row.

    Required: ``channel``, ``participant``, ``speakerId``, ``text``,
    ``start``, ``end`` (all server-set; times in milliseconds).
    """
    channel: int = Field(..., description="Audio channel associated with this phrase/utterance")
    participant: int = Field(..., description="Identifier of the participant")
    speakerId: int = Field(..., description="Identified-speaker tag (auto-increments)")
    text: str = Field(..., description="Spoken phrase or utterance extracted from the audio")
    start: int = Field(..., description="Start time in milliseconds")
    end: int = Field(..., description="End time in milliseconds")


# ─── TranscriptsMetadata + TranscriptsParticipant ────────────────────


class TranscriptsParticipant(BaseModel):
    """``TranscriptsParticipant`` schema — participant role entry.

    Required: ``channel`` (audio channel integer), ``role`` (one of
    ``doctor`` | ``patient`` | ``multiple``).
    """
    channel: int = Field(..., description="Audio channel to associate with this participant role")
    role: Literal["doctor", "patient", "multiple"] = Field(
        ..., description="Participant role: doctor / patient / multiple (single-channel)"
    )


class TranscriptsMetadata(BaseModel):
    """``TranscriptsMetadata`` schema — metadata wrapper around participants."""
    participantsRoles: Optional[List[TranscriptsParticipant]] = Field(
        default=None, description="List of participant role entries (nullable)"
    )


# ─── TranscriptsData (full payload when ?full=true) ─────────────────


class TranscriptsData(BaseModel):
    """``TranscriptsData`` schema — full transcript payload.

    Required: ``metadata``, ``transcripts``.
    """
    metadata: TranscriptsMetadata
    transcripts: List[CommonTranscriptResponse]


# ─── TranscriptsListItem (envelope element) ─────────────────────────


class TranscriptsListItem(BaseModel):
    """``TranscriptsListItem`` schema — single item in the list envelope.

    Required: ``id``, ``transcriptSample``.
    Optional: ``transcript`` (full data; populated when ?full=true).
    """
    id: str = Field(..., description="UUID of the transcript")
    transcriptSample: str = Field(..., description="Short text sample (preview when ?full=false)")
    transcript: Optional[TranscriptsData] = Field(
        default=None, description="Full transcript payload (nullable; populated when ?full=true)"
    )


# ─── TranscriptsListResponse (envelope) ─────────────────────────────


class TranscriptsListResponse(BaseModel):
    """``TranscriptsListResponse`` schema — list-transcripts response envelope.

    Required: ``transcripts``. Per spec, the ``transcripts`` field is
    declared ``nullable: true`` — an empty interaction may return
    ``{transcripts: null}`` (not ``{transcripts: []}``).
    """
    transcripts: Optional[List[TranscriptsListItem]] = Field(
        default=None, description="List of transcripts (nullable per spec)"
    )


# ─── CommonUsageInfo (credits, shared with cycle 3) ─────────────────


class CommonUsageInfo(BaseModel):
    """``CommonUsageInfo`` schema — credits consumed for this request."""
    creditsConsumed: float = Field(..., ge=0.0)


# ─── TranscriptsStatusEnum + TranscriptsResponse (cycle 7 get) ──────


class TranscriptsResponse(BaseModel):
    """``TranscriptsResponse`` schema — single-transcript response (get-transcript).

    Required: ``id``, ``metadata``, ``transcripts``, ``usageInfo``,
    ``recordingId``, ``status``. Per spec, the ``transcripts`` field
    itself is ``nullable: true`` — a transcript whose processing is
    still in progress may return ``{transcripts: null}`` (status
    ``processing``) until it completes.
    """
    id: str = Field(..., description="UUID of the transcript")
    metadata: TranscriptsMetadata
    transcripts: Optional[List[CommonTranscriptResponse]] = Field(
        default=None, description="Transcript utterance rows (nullable while processing)"
    )
    usageInfo: CommonUsageInfo
    recordingId: str = Field(..., description="UUID of the associated recording")
    status: Literal["completed", "processing", "failed"] = Field(
        ..., description="Transcript processing status"
    )