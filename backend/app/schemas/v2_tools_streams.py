"""Corti §13.3/§13.4 Streams WSS request/response schemas.

Cycle 2 (2026-06-30) — wire-shape parity with the Corti AsyncAPI definition at
``docs/corti-reverse-engineered/stream-asyncapi.json``. This is the **single
source of truth** for field names, types, and required/optional semantics
used by ``POST/WS /api/v2/tools/streams``. Any change here MUST be matched
against that AsyncAPI file (and vice-versa).

Why each name matches the spec verbatim:
- Corti SDK + browser client parse the wire directly; renaming a key
  (e.g. ``outputLanguage`` -> ``outputLocale``) breaks every consumer.
- The spec uses CamelCase throughout (e.g. ``primaryLanguage``,
  ``outputLocale``, ``isMultichannel``); we keep that casing verbatim.

Field sources (per message type) and their schema refs:
  configuration        -> StreamConfigMessage / StreamConfig /
                          StreamConfigTranscription / StreamConfigMode
  configStatus         -> StreamConfigStatusMessage
  transcript           -> StreamTranscriptMessage / StreamTranscript /
                          StreamParticipant / StreamTranscriptTime
  facts                -> StreamFactsMessage / StreamFact
  end / ended          -> StreamEndMessage / StreamEndedMessage
  usage                -> StreamUsageMessage
  error                -> StreamErrorMessage / StreamErrorDetail
  audio                -> binary (webm/opus)
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ─── Client → Server: configuration ─────────────────────────────────


class StreamConfigParticipant(BaseModel):
    """StreamConfigParticipant schema.

    Channels audio and assigns a role. Required when ``isMultichannel=true``;
    omitted otherwise. Roles are an enum per the Corti schema.
    """
    channel: int = Field(..., ge=0, description="Audio channel number (e.g. 0 or 1)")
    role: Literal["doctor", "patient", "multiple"] = Field(
        ..., description="Role of the participant (e.g. doctor, patient, or multiple)"
    )


class StreamConfigTranscription(BaseModel):
    """StreamConfigTranscription schema — speech-to-text config block."""
    primaryLanguage: str = Field(
        ..., description="Primary spoken language code (Corti SupportedLanguage string)"
    )
    isDiarization: bool = Field(
        default=False, description="Enable speaker diarization (legacy alias: `diarize`)"
    )
    isMultichannel: bool = Field(
        default=False, description="Enable multi-channel audio processing"
    )
    participants: List[StreamConfigParticipant] = Field(
        default_factory=list,
        description="List of participants with roles assigned to a channel; minItems=1 when isMultichannel=true",
    )


class StreamConfigMode(BaseModel):
    """StreamConfigMode schema — output mode block."""
    type: Literal["facts", "transcription", "documentation"] = Field(
        ..., description="Processing mode (real-time output selector)"
    )
    outputLocale: Optional[str] = Field(
        default=None, description="Output language locale for facts (required when type='facts')"
    )
    templateId: Optional[str] = Field(
        default=None, description="Template identifier for processing configuration (documentation mode)"
    )


class StreamConfig(BaseModel):
    """StreamConfig schema — inner configuration block."""
    transcription: StreamConfigTranscription
    mode: StreamConfigMode


class StreamConfigMessage(BaseModel):
    """StreamConfigMessage schema — client→server setup message.

    Must be sent within 15 seconds of opening the WSS per the AsyncAPI doc.
    """
    type: Literal["config"] = Field(..., description="Discriminator; always 'config'")
    configuration: StreamConfig


# ─── Server → Client: configStatus ───────────────────────────────────


class StreamConfigStatusMessage(BaseModel):
    """StreamConfigStatusMessage schema — server→client ack/nack."""
    type: Literal[
        "CONFIG_ACCEPTED",
        "CONFIG_DENIED",
        "CONFIG_MISSING",
        "CONFIG_NOT_PROVIDED",
        "CONFIG_ALREADY_RECEIVED",
        "CONFIG_TIMEOUT",
    ] = Field(..., description="Configuration status result")
    reason: Optional[str] = Field(
        default=None, description="Optional reason for rejection (e.g. 'language unavailable')"
    )


# ─── Server → Client: transcript ─────────────────────────────────────


class StreamParticipant(BaseModel):
    """StreamParticipant schema — embedded in transcript items."""
    channel: int = Field(..., ge=0, description="Audio channel number (e.g. 0 or 1)")


class StreamTranscriptTime(BaseModel):
    """StreamTranscriptTime schema — segment timing."""
    start: float = Field(..., ge=0.0, description="Start time of the transcript segment")
    end: float = Field(..., ge=0.0, description="End time of the transcript segment")


class StreamTranscript(BaseModel):
    """StreamTranscript schema — one segment."""
    id: str = Field(..., description="Unique identifier for the transcript segment")
    transcript: str = Field(..., description="The transcribed text")
    final: bool = Field(..., description="True when the transcript is final; False for interim")
    speakerId: int = Field(..., description="Speaker identifier (-1 when diarization is off)")
    participant: StreamParticipant
    time: StreamTranscriptTime


class StreamTranscriptMessage(BaseModel):
    """StreamTranscriptMessage schema — server→client transcript batch."""
    type: Literal["transcript"] = Field(..., description="Discriminator; always 'transcript'")
    data: List[StreamTranscript] = Field(..., min_length=1, description="Transcript segments")


# ─── Server → Client: facts ──────────────────────────────────────────


class StreamFact(BaseModel):
    """StreamFact schema — one extracted clinical fact."""
    id: str = Field(..., description="Unique identifier for the fact")
    text: str = Field(..., description="Text description of the fact")
    group: str = Field(..., description="Categorization (e.g. 'medical-history')")
    groupId: str = Field(..., description="Unique identifier for the group")
    isDiscarded: bool = Field(..., description="Whether the fact was discarded")
    source: str = Field(..., description="Source of the fact (e.g. 'core' for LLM-generated)")
    createdAt: datetime = Field(..., description="Timestamp when the fact was created")
    updatedAt: Optional[datetime] = Field(default=None, description="Last-update timestamp")
    createdAtTzOffset: Optional[str] = Field(
        default=None, description="Timezone offset for createdAt (e.g. '+00:00')"
    )
    updatedAtTzOffset: Optional[str] = Field(
        default=None, description="Timezone offset for updatedAt"
    )


class StreamFactsMessage(BaseModel):
    """StreamFactsMessage schema — server→client facts batch."""
    type: Literal["facts"] = Field(..., description="Discriminator; always 'facts'")
    fact: List[StreamFact] = Field(..., min_length=1, description="Extracted facts (Corti uses singular 'fact' per the schema)")


# ─── Client → Server: end / Server → Client: ended ───────────────────


class StreamEndMessage(BaseModel):
    """StreamEndMessage schema — client→server end-of-stream signal."""
    type: Literal["end"] = Field(..., description="Discriminator; always 'end'")


class StreamEndedMessage(BaseModel):
    """StreamEndedMessage schema — server→client stream-has-ended ack."""
    type: Literal["ENDED"] = Field(..., description="Discriminator; always 'ENDED'")


# ─── Server → Client: usage / error ──────────────────────────────────


class StreamUsageMessage(BaseModel):
    """StreamUsageMessage schema — server→client credits-billed notice."""
    type: Literal["usage"] = Field(..., description="Discriminator; always 'usage'")
    credits: float = Field(..., ge=0.0, description="The amount of credits used for this stream")


class StreamErrorDetail(BaseModel):
    """StreamErrorDetail schema — embedded error block."""
    id: str = Field(..., description="Error identifier")
    title: str = Field(..., description="Error title")
    status: int = Field(..., description="HTTP status code or similar error code")
    details: str = Field(..., description="Detailed error message")
    doc: str = Field(..., description="Link to documentation or further information")


class StreamErrorMessage(BaseModel):
    """StreamErrorMessage schema — server→client error notice."""
    type: Literal["error"] = Field(..., description="Discriminator; always 'error'")
    error: StreamErrorDetail


# ─── Discriminator union (for typed send/recv) ───────────────────────

# Receivable from server (in spec-defined order of arrival):
ServerMessage = (
    StreamConfigStatusMessage
    | StreamTranscriptMessage
    | StreamFactsMessage
    | StreamEndedMessage
    | StreamUsageMessage
    | StreamErrorMessage
)

# Sendable from client:
ClientMessage = StreamConfigMessage | StreamEndMessage