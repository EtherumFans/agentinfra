"""Strict wire models for the current Corti-compatible Streams protocol.

The public reference is https://docs.corti.ai/api-reference/streams. The
models deliberately reject unknown configuration fields: accepting an option
that the runtime silently ignores is unsafe for clinical audio.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class StreamConfigParticipant(_StrictModel):
    channel: int = Field(..., ge=0, le=15)
    role: str = Field(..., min_length=1, max_length=64)


class StreamConfigTranscription(_StrictModel):
    primaryLanguage: str = Field(..., min_length=2, max_length=32)
    diarize: bool = Field(
        default=False,
        validation_alias=AliasChoices("diarize", "isDiarization"),
        serialization_alias="diarize",
    )
    isMultichannel: bool = False
    participants: list[StreamConfigParticipant] = Field(
        default_factory=list,
        max_length=16,
    )

    @model_validator(mode="after")
    def validate_participants(self) -> "StreamConfigTranscription":
        channels = [item.channel for item in self.participants]
        if len(channels) != len(set(channels)):
            raise ValueError("participant channels must be unique")
        return self


class StreamConfigMode(_StrictModel):
    type: Literal["facts", "transcription"]
    outputLocale: str | None = Field(default=None, min_length=2, max_length=32)
    factGenerationInterval: Literal["fixed", "fast_init"] | None = None

    @model_validator(mode="after")
    def validate_output_locale(self) -> "StreamConfigMode":
        if self.type == "facts" and not self.outputLocale:
            raise ValueError("outputLocale is required in facts mode")
        return self


class StreamAudioEventsConfig(_StrictModel):
    enabled: bool


class StreamReplacement(_StrictModel):
    find: str = Field(..., min_length=1, max_length=200)
    replace: str = Field(..., max_length=200)


class StreamKeyterm(_StrictModel):
    term: str = Field(..., min_length=1, max_length=50)


class StreamKeyterms(_StrictModel):
    terms: list[StreamKeyterm] = Field(default_factory=list, max_length=1000)


class StreamConfig(_StrictModel):
    transcription: StreamConfigTranscription
    mode: StreamConfigMode
    retentionPolicy: Literal["none", "retain"] = Field(
        default="retain",
        validation_alias=AliasChoices("retentionPolicy", "xCortiRetentionPolicy"),
        serialization_alias="retentionPolicy",
    )
    audioFormat: str | None = Field(default=None, min_length=3, max_length=128)
    audioEvents: StreamAudioEventsConfig = Field(
        default_factory=lambda: StreamAudioEventsConfig(enabled=False)
    )
    replacements: list[StreamReplacement] = Field(default_factory=list, max_length=1000)
    keyterms: StreamKeyterms = Field(default_factory=StreamKeyterms)


class StreamConfigMessage(_StrictModel):
    type: Literal["config"]
    configuration: StreamConfig


class StreamConfigAcceptedMessage(_StrictModel):
    type: Literal["CONFIG_ACCEPTED"]
    sessionId: str = Field(..., min_length=36, max_length=36)
    configuration: StreamConfig
    resumed: bool = False
    restoredAudioBytes: int = Field(default=0, ge=0, le=32 * 1024 * 1024)
    restoredTranscriptMessages: int = Field(default=0, ge=0)
    restoredFactMessages: int = Field(default=0, ge=0)


class StreamConfigStatusMessage(_StrictModel):
    type: Literal[
        "CONFIG_DENIED",
        "CONFIG_MISSING",
        "CONFIG_NOT_PROVIDED",
        "CONFIG_ALREADY_RECEIVED",
    ]
    reason: str | None = Field(default=None, max_length=160)
    interactionId: str


class StreamParticipant(_StrictModel):
    channel: int = Field(..., ge=0, le=15)


class StreamTranscriptTime(_StrictModel):
    start: float = Field(..., ge=0.0)
    end: float = Field(..., ge=0.0)


class StreamTranscript(_StrictModel):
    id: str
    transcript: str
    final: bool
    speakerId: int
    participant: StreamParticipant
    time: StreamTranscriptTime


class StreamTranscriptMessage(_StrictModel):
    type: Literal["transcript"]
    data: list[StreamTranscript] = Field(..., min_length=1)


class StreamFact(_StrictModel):
    id: str
    text: str
    group: str
    groupId: str
    isDiscarded: bool
    source: str
    createdAt: datetime
    updatedAt: datetime | None = None
    createdAtTzOffset: str | None = None
    updatedAtTzOffset: str | None = None


class StreamFactsMessage(_StrictModel):
    type: Literal["facts"]
    fact: list[StreamFact] = Field(..., min_length=1)


class StreamFlushMessage(_StrictModel):
    type: Literal["flush"]


class StreamFlushedMessage(_StrictModel):
    type: Literal["flushed"]


class StreamEndMessage(_StrictModel):
    type: Literal["end"]


class StreamEndedMessage(_StrictModel):
    type: Literal["ENDED"]


class StreamUsageMessage(_StrictModel):
    type: Literal["usage"]
    credits: float = Field(..., ge=0.0)


class StreamDeltaUsageMessage(_StrictModel):
    type: Literal["delta_usage"]
    credits: float = Field(..., ge=0.0)


StreamAudioEventName = Literal[
    "speechQualityIssueDetected",
    "speechQualityIssueRecovered",
    "longSilenceDetected",
    "longSilenceRecovered",
]


class StreamAudioEventData(_StrictModel):
    event: StreamAudioEventName
    channel: int = Field(..., ge=0, le=15)
    startTimeMs: int = Field(..., ge=0)


class StreamAudioEventMessage(_StrictModel):
    type: Literal["audioEvent"]
    data: StreamAudioEventData


class StreamErrorDetail(_StrictModel):
    id: str
    title: str
    status: int
    details: str
    doc: str


class StreamErrorMessage(_StrictModel):
    type: Literal["error"]
    error: StreamErrorDetail


ServerMessage = Annotated[
    StreamConfigAcceptedMessage
    | StreamConfigStatusMessage
    | StreamTranscriptMessage
    | StreamFactsMessage
    | StreamFlushedMessage
    | StreamDeltaUsageMessage
    | StreamAudioEventMessage
    | StreamUsageMessage
    | StreamEndedMessage
    | StreamErrorMessage,
    Field(discriminator="type"),
]

ClientMessage = Annotated[
    StreamConfigMessage | StreamFlushMessage | StreamEndMessage,
    Field(discriminator="type"),
]
