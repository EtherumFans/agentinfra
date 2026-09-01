"""Tenant-safe Corti-compatible Streams WebSocket runtime.

This endpoint implements the currently verified Chinese mono and declared
PCM multichannel subset of Corti Streams. Unsupported clinical capabilities are rejected during the
configuration handshake instead of being accepted and silently ignored.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app import database
from app.middleware.audit import log_action
from app.middleware.auth import (
    decode_token,
    get_current_client,
    get_current_organization,
    get_current_user,
)
from app.models.organization import Organization
from app.schemas.v2_tools_streams import (
    StreamConfigAcceptedMessage,
    StreamAudioEventData,
    StreamAudioEventMessage,
    StreamConfigMessage,
    StreamConfigStatusMessage,
    StreamDeltaUsageMessage,
    StreamEndMessage,
    StreamEndedMessage,
    StreamErrorDetail,
    StreamErrorMessage,
    StreamFact,
    StreamFactsMessage,
    StreamFlushedMessage,
    StreamFlushMessage,
    StreamTranscript,
    StreamTranscriptMessage,
    StreamUsageMessage,
)
from app.services.ambient_processing import (
    ExtractedStreamFact,
    deinterleave_pcm_s16le,
    extract_stream_facts_with_usage,
    transcribe_stream_audio,
)
from app.services.clinical_fact_repository import clinical_fact_repository
from app.services.database_tenancy import bind_tenant_to_transaction
from app.services.stt_artifact_repository import stt_artifact_repository
from app.services.stt_service import apply_requested_replacements
from app.services.stream_audio_format import (
    DeclaredStreamAudioFormat,
    StreamAudioProbeStatus,
    parse_declared_stream_audio_format,
    probe_stream_audio,
)
from app.services.stream_audio_health import (
    PcmS16leMonoHealthMonitor,
    PcmS16leMultichannelHealthMonitor,
)
from app.services.stream_media_decoder import (
    StreamMediaDecodeStatus,
    validate_stream_audio_decode,
)
from app.services.stream_checkpoint_repository import (
    StreamCheckpointConfigurationMismatch,
    StreamCheckpointEncryptionRequired,
    StreamCheckpointError,
    StreamCheckpointIntegrityError,
    stream_checkpoint_repository,
)
from app.services.stream_session_lease import (
    StreamLeaseScope,
    acquire_stream_lease as _acquire_stream_lease,
    configured_lease_seconds,
    release_stream_lease as _release_stream_lease,
    renew_stream_lease as _renew_stream_lease,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])

_SUPPORTED_ENVIRONMENTS = frozenset({"cn", "eu", "us"})
_MAX_AUDIO_CHUNK_BYTES = 64_000
_MAX_STREAM_AUDIO_BYTES = 32 * 1024 * 1024
_CONFIG_TIMEOUT_SECONDS = 10.0


class _StreamMediaDecodeFailure(RuntimeError):
    def __init__(self, status: StreamMediaDecodeStatus):
        super().__init__(status.value)
        self.status = status


@dataclass(frozen=True, slots=True)
class _StreamPrincipal:
    organization_id: str
    owner_id: str
    username: str
    tenant_names: frozenset[str]
    token_type: str


@dataclass(slots=True)
class _StreamState:
    interaction_id: str
    session_id: str
    principal: _StreamPrincipal
    configuration: StreamConfigMessage | None = None
    transcript_seq: int = 0
    fact_seq: int = 0
    fact_generation_attempts: int = 0
    audio_chunk_count: int = 0
    audio_bytes: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    audio_buffer: bytearray = field(default_factory=bytearray)
    last_processed_bytes: int = 0
    transcript_text: str = ""
    channel_transcript_text: dict[int, str] = field(default_factory=dict)
    emitted_facts: set[tuple[str, str]] = field(default_factory=set)
    recording_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    provider_usage: dict[str, int | float | str] = field(default_factory=dict)
    declared_audio_format: DeclaredStreamAudioFormat | None = None
    resolved_audio_format: str | None = None
    audio_format_validated: bool = False
    audio_health_monitor: (
        PcmS16leMonoHealthMonitor | PcmS16leMultichannelHealthMonitor | None
    ) = None
    audio_event_count: int = 0
    lease_lost: bool = False
    checkpoint_enabled: bool = False
    checkpoint_resumed: bool = False
    checkpoint_recoverable: bool = True
    ended: bool = False

    @property
    def config(self):
        if self.configuration is None:
            raise RuntimeError("stream_configuration_unavailable")
        return self.configuration.configuration

    @property
    def scope(self) -> dict[str, str]:
        return {
            "organization_id": self.principal.organization_id,
            "owner_id": self.principal.owner_id,
            "interaction_id": self.interaction_id,
        }

    @property
    def lease_scope(self) -> StreamLeaseScope:
        return StreamLeaseScope(**self.scope)


_active_streams: dict[tuple[str, str, str], _StreamState] = {}


def _stream_key(state: _StreamState) -> tuple[str, str, str]:
    return (
        state.principal.organization_id,
        state.principal.owner_id,
        state.interaction_id,
    )


def _json(model: Any) -> str:
    return json.dumps(model.model_dump(mode="json", by_alias=True), ensure_ascii=False)


def _err_payload(code: str, title: str, http_status: int, details: str) -> dict[str, Any]:
    return StreamErrorMessage(
        type="error",
        error=StreamErrorDetail(
            id=code,
            title=title,
            status=http_status,
            details=details,
            doc=f"https://docs.corti.ai/api-reference/streams#{code.lower()}",
        ),
    ).model_dump(mode="json")


def _config_status(
    message_type: str,
    interaction_id: str,
    reason: str,
) -> StreamConfigStatusMessage:
    return StreamConfigStatusMessage(
        type=message_type,
        reason=reason,
        interactionId=interaction_id,
    )


def _validate_config(raw: Any) -> tuple[StreamConfigMessage | None, str]:
    if not isinstance(raw, dict) or raw.get("type") != "config":
        return None, "configuration_message_invalid"
    try:
        parsed = StreamConfigMessage.model_validate(raw)
    except Exception:
        return None, "configuration_schema_invalid"

    cfg = parsed.configuration
    transcription = cfg.transcription
    if not transcription.primaryLanguage.casefold().startswith("zh"):
        return None, "unsupported_primary_language"
    if transcription.diarize:
        return None, "diarization_not_available"
    try:
        declared = parse_declared_stream_audio_format(cfg.audioFormat)
    except ValueError:
        return None, "audio_format_not_supported"
    if declared is not None and declared.container == "pcm" and (
        declared.rate != 16000
        or declared.channels is None
        or not 1 <= declared.channels <= 8
        or declared.bits != 16
        or declared.endian != "little"
        or declared.encoding != "sint"
    ):
        return None, "raw_pcm_profile_not_available"
    participant_channels = {item.channel for item in transcription.participants}
    if transcription.isMultichannel:
        if declared is None or declared.container != "pcm" or (declared.channels or 0) < 2:
            return None, "multichannel_pcm_format_required"
        if participant_channels != set(range(declared.channels or 0)):
            return None, "multichannel_participants_must_match_channels"
    else:
        if declared is not None and declared.container == "pcm" and declared.channels != 1:
            return None, "multichannel_flag_required"
        if any(item.channel != 0 for item in transcription.participants):
            return None, "mono_participant_channel_required"
    if cfg.audioEvents.enabled and (
        declared is None or declared.container != "pcm"
    ):
        return None, "audio_events_require_pcm"
    replacement_keys = [item.find.casefold() for item in cfg.replacements]
    if len(replacement_keys) != len(set(replacement_keys)):
        return None, "replacement_find_values_must_be_unique"
    return parsed, ""


def _configured_environment_allowed(environment: str) -> bool:
    normalized = environment.strip().casefold()
    if normalized not in _SUPPORTED_ENVIRONMENTS:
        return False
    configured = str(settings.ICODER_ENVIRONMENT or "").strip().casefold()
    return not configured or normalized == configured


async def _authenticate_stream(
    token: str,
    tenant_name: str,
    environment: str,
) -> _StreamPrincipal:
    if not token:
        raise HTTPException(status_code=401, detail="stream_token_required")
    if not tenant_name or len(tenant_name) > 128:
        raise HTTPException(status_code=403, detail="stream_tenant_required")
    if not _configured_environment_allowed(environment):
        raise HTTPException(status_code=403, detail="stream_environment_mismatch")

    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="stream_token_invalid") from exc
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    async with database.AsyncSessionLocal() as db:
        token_type = str(payload.get("type") or "")
        if token_type == "access":
            user = await get_current_user(credentials, db)
            organization = await get_current_organization(credentials, db)
            owner_id = str(user.id)
            username = str(user.username)
        elif token_type == "client_credentials":
            client = await get_current_client(credentials, db)
            if "streams" not in set(client.get("scopes") or []):
                raise HTTPException(status_code=403, detail="stream_scope_required")
            organization = await db.get(Organization, str(client.get("org_id") or ""))
            if organization is None or not organization.is_active:
                raise HTTPException(status_code=403, detail="stream_tenant_unavailable")
            owner_id = str(client.get("owner_id") or "")
            username = "api-client"
        else:
            raise HTTPException(status_code=401, detail="stream_access_token_required")

        names = frozenset(
            item for item in (str(organization.id), str(organization.slug)) if item
        )
        if tenant_name not in names:
            raise HTTPException(status_code=403, detail="stream_tenant_mismatch")
        if not owner_id:
            raise HTTPException(status_code=403, detail="stream_owner_required")
        return _StreamPrincipal(
            organization_id=str(organization.id),
            owner_id=owner_id,
            username=username,
            tenant_names=names,
            token_type=token_type,
        )


async def _audit_state(
    state: _StreamState,
    action: str,
    *,
    status: str = "success",
    details: dict[str, Any] | None = None,
) -> None:
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        await log_action(
            db,
            user_id=state.principal.owner_id,
            username=state.principal.username,
            action=action,
            resource_type="stt_stream",
            resource_id=state.interaction_id,
            organization_id=state.principal.organization_id,
            status=status,
            details={
                "session_id": state.session_id,
                "token_type": state.principal.token_type,
                "audio_bytes": state.audio_bytes,
                "audio_chunks": state.audio_chunk_count,
                **(details or {}),
            },
        )
        await db.commit()


async def _persist_transcript(
    state: _StreamState,
    segment: StreamTranscript,
) -> None:
    if state.config.retentionPolicy == "none":
        return
    participant_roles = tuple(
        (item.channel, item.role) for item in state.config.transcription.participants
    )
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        await stt_artifact_repository.put_transcript(
            db,
            **state.scope,
            transcript_id=segment.id,
            recording_id=state.recording_id,
            status="completed",
            participant_roles=participant_roles,
            text=segment.transcript,
            request_data={
                "source": "streams",
                "primaryLanguage": state.config.transcription.primaryLanguage,
                "participant_channel": segment.participant.channel,
                "speaker_id": segment.speakerId,
                "stream_message_sequence": state.transcript_seq + 1,
                "time": segment.time.model_dump(mode="json"),
                "final": segment.final,
            },
        )
        await db.commit()


async def _persist_fact(state: _StreamState, fact: StreamFact) -> None:
    if state.config.retentionPolicy == "none":
        return
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        await clinical_fact_repository.create(
            db,
            **state.scope,
            fact_id=fact.id,
            text=fact.text,
            group_key=fact.group,
            source=fact.source,
        )
        await db.commit()


async def _persist_recording(state: _StreamState) -> None:
    if state.config.retentionPolicy == "none" or not state.audio_buffer:
        return
    if not state.audio_format_validated or state.resolved_audio_format is None:
        raise RuntimeError("stream_audio_format_unvalidated")
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        existing = await stt_artifact_repository.get_recording(
            db,
            **state.scope,
            recording_id=state.recording_id,
        )
        if existing is not None:
            if (
                existing.media_type != state.resolved_audio_format
                or stt_artifact_repository.recording_content(existing)
                != bytes(state.audio_buffer)
            ):
                raise RuntimeError("stream_recording_idempotency_conflict")
            return
        await stt_artifact_repository.put_recording(
            db,
            **state.scope,
            recording_id=state.recording_id,
            media_type=state.resolved_audio_format,
            content=bytes(state.audio_buffer),
        )
        await db.commit()


def _checkpoint_state_payload(state: _StreamState) -> dict[str, Any]:
    return {
        "schema": "icoder/stt-stream-checkpoint/v1",
        "configuration": state.config.model_dump(mode="json", by_alias=True),
        "recording_id": state.recording_id,
        "started_at": state.started_at.isoformat(),
        "transcript_seq": state.transcript_seq,
        "fact_seq": state.fact_seq,
        "fact_generation_attempts": state.fact_generation_attempts,
        "audio_chunk_count": state.audio_chunk_count,
        "audio_bytes": state.audio_bytes,
        "last_processed_bytes": state.last_processed_bytes,
        "transcript_text": state.transcript_text,
        "channel_transcript_text": {
            str(channel): text
            for channel, text in sorted(state.channel_transcript_text.items())
        },
        "emitted_facts": [list(item) for item in sorted(state.emitted_facts)],
        "provider_usage": state.provider_usage,
        "resolved_audio_format": state.resolved_audio_format,
        "audio_format_validated": state.audio_format_validated,
        "audio_event_count": state.audio_event_count,
    }


def _apply_checkpoint_state(
    state: _StreamState,
    payload: dict[str, Any],
    audio: bytes,
) -> None:
    try:
        started_at = datetime.fromisoformat(str(payload["started_at"]))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        emitted = payload.get("emitted_facts") or []
        emitted_facts = {
            (str(item[0]), str(item[1]))
            for item in emitted
            if isinstance(item, list) and len(item) == 2
        }
        audio_chunk_count = int(payload["audio_chunk_count"])
        audio_bytes = int(payload["audio_bytes"])
        last_processed = int(payload["last_processed_bytes"])
        transcript_seq = int(payload["transcript_seq"])
        fact_seq = int(payload["fact_seq"])
        fact_generation_attempts = int(payload.get("fact_generation_attempts") or 0)
        audio_event_count = int(payload.get("audio_event_count") or 0)
    except Exception as exc:
        raise StreamCheckpointIntegrityError(
            "stream checkpoint runtime state is invalid"
        ) from exc
    if (
        audio_bytes != len(audio)
        or audio_bytes < 0
        or audio_bytes > _stream_max_audio_bytes()
        or audio_chunk_count < 0
        or last_processed < 0
        or last_processed > audio_bytes
        or transcript_seq < 0
        or fact_seq < 0
        or fact_generation_attempts < 0
        or audio_event_count < 0
    ):
        raise StreamCheckpointIntegrityError(
            "stream checkpoint runtime accounting is invalid"
        )
    transcript_text = payload.get("transcript_text")
    raw_channel_transcripts = payload.get("channel_transcript_text") or {}
    provider_usage = payload.get("provider_usage")
    resolved_audio_format = payload.get("resolved_audio_format")
    if (
        not isinstance(transcript_text, str)
        or not isinstance(provider_usage, dict)
        or not isinstance(raw_channel_transcripts, dict)
    ):
        raise StreamCheckpointIntegrityError(
            "stream checkpoint text or usage state is invalid"
        )
    if resolved_audio_format is not None and not isinstance(resolved_audio_format, str):
        raise StreamCheckpointIntegrityError(
            "stream checkpoint audio format state is invalid"
        )
    state.recording_id = str(payload["recording_id"])
    state.started_at = started_at
    state.transcript_seq = transcript_seq
    state.fact_seq = fact_seq
    state.fact_generation_attempts = fact_generation_attempts
    state.audio_chunk_count = audio_chunk_count
    state.audio_bytes = audio_bytes
    state.last_processed_bytes = last_processed
    state.transcript_text = transcript_text
    try:
        state.channel_transcript_text = {
            int(channel): str(text)
            for channel, text in raw_channel_transcripts.items()
            if 0 <= int(channel) <= 7 and isinstance(text, str)
        }
    except (TypeError, ValueError, OverflowError) as exc:
        raise StreamCheckpointIntegrityError(
            "stream checkpoint channel transcript state is invalid"
        ) from exc
    if not state.channel_transcript_text and transcript_text:
        state.channel_transcript_text = {0: transcript_text}
    state.emitted_facts = emitted_facts
    state.provider_usage = dict(provider_usage)
    state.resolved_audio_format = resolved_audio_format
    state.audio_format_validated = bool(payload.get("audio_format_validated"))
    state.audio_event_count = audio_event_count
    state.audio_buffer = bytearray(audio)


async def _rehydrate_retained_outputs(state: _StreamState) -> None:
    """Make persisted transcript/fact writes authoritative after a crash."""

    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        transcript_rows = await stt_artifact_repository.list_transcripts(
            db, **state.scope
        )
        stream_rows = []
        for row in transcript_rows:
            if row.recording_id != state.recording_id:
                continue
            request_data = stt_artifact_repository.request_data(row)
            if request_data.get("source") == "streams" and row.status == "completed":
                stream_rows.append(row)
        if stream_rows:
            channel_transcripts: dict[int, str] = {}
            for row in stream_rows:
                request_data = stt_artifact_repository.request_data(row)
                channel = request_data.get("participant_channel", 0)
                if isinstance(channel, int) and 0 <= channel <= 7:
                    channel_transcripts[channel] = stt_artifact_repository.transcript_text(row)
            state.channel_transcript_text = channel_transcripts
            state.transcript_text = _aggregate_channel_transcripts(state)
            message_sequences = []
            for row in stream_rows:
                sequence = stt_artifact_repository.request_data(row).get(
                    "stream_message_sequence"
                )
                if isinstance(sequence, int) and sequence > 0:
                    message_sequences.append(sequence)
            state.transcript_seq = max(
                state.transcript_seq,
                max(message_sequences, default=len(stream_rows)),
            )

        fact_rows = await clinical_fact_repository.list(db, **state.scope)
        retained_facts = {
            (row.group_key, clinical_fact_repository.text(row))
            for row in fact_rows
            if row.source == "core" and not row.is_discarded
        }
        state.emitted_facts.update(retained_facts)
        state.fact_seq = max(state.fact_seq, len(retained_facts))


async def _resume_or_initialize_checkpoint(state: _StreamState) -> None:
    state.checkpoint_enabled = state.config.retentionPolicy == "retain"
    initial = _checkpoint_state_payload(state)
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        restored = await stream_checkpoint_repository.resume_or_initialize(
            db,
            scope=state.scope,
            session_id=state.session_id,
            state=initial,
            enabled=state.checkpoint_enabled,
        )
        await db.commit()
    if restored is None:
        return
    state.checkpoint_enabled = True
    state.checkpoint_resumed = restored.resumed
    if restored.resumed:
        _apply_checkpoint_state(state, restored.state, restored.audio)
        await _rehydrate_retained_outputs(state)
        await _save_checkpoint_state(state)


async def _append_checkpoint_chunk(state: _StreamState, chunk: bytes) -> None:
    if not state.checkpoint_enabled:
        return
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        await stream_checkpoint_repository.append_chunk(
            db,
            scope=state.scope,
            session_id=state.session_id,
            state=_checkpoint_state_payload(state),
            chunk=chunk,
        )
        await db.commit()


async def _save_checkpoint_state(state: _StreamState) -> None:
    if not state.checkpoint_enabled:
        return
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        await stream_checkpoint_repository.save_state(
            db,
            scope=state.scope,
            session_id=state.session_id,
            state=_checkpoint_state_payload(state),
        )
        await db.commit()


async def _discard_checkpoint(state: _StreamState) -> bool:
    if not state.checkpoint_enabled:
        return False
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, state.principal.organization_id)
        discarded = await stream_checkpoint_repository.discard(
            db,
            scope=state.scope,
            session_id=state.session_id,
        )
        await db.commit()
        return discarded


def _stream_asr_min_bytes() -> int:
    if os.environ.get("ICODER_TEST_MODE") == "1":
        return 1
    try:
        return max(1, int(os.environ.get("ICODER_STREAM_ASR_MIN_BYTES", "32000")))
    except ValueError:
        return 32000


def _stream_max_audio_bytes() -> int:
    try:
        requested = int(os.environ.get("ICODER_STREAM_MAX_AUDIO_BYTES", str(_MAX_STREAM_AUDIO_BYTES)))
    except ValueError:
        requested = _MAX_STREAM_AUDIO_BYTES
    return max(1, min(requested, _MAX_STREAM_AUDIO_BYTES))


async def _stream_lease_heartbeat(websocket: WebSocket, state: _StreamState) -> None:
    """Keep the cross-worker ownership fence alive or terminate safely."""

    interval = max(1.0, configured_lease_seconds() / 3)
    while True:
        await asyncio.sleep(interval)
        try:
            renewed = await _renew_stream_lease(state.lease_scope, state.session_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "streams lease heartbeat unavailable session_id=%s", state.session_id
            )
            renewed = False
        if renewed:
            continue
        state.lease_lost = True
        try:
            await websocket.close(code=1013, reason="stream coordination unavailable")
        except Exception:
            pass
        return


async def _confirm_stream_lease(state: _StreamState) -> bool:
    """Fence flush/end side effects against an expired or reclaimed lease."""

    try:
        return await _renew_stream_lease(state.lease_scope, state.session_id)
    except Exception:
        logger.warning("streams lease confirmation failed session_id=%s", state.session_id)
        return False


def _validate_stream_audio_buffer(
    state: _StreamState,
    *,
    final: bool,
) -> tuple[bool, str | None]:
    if state.audio_format_validated:
        if (
            final
            and state.declared_audio_format is not None
            and state.declared_audio_format.container == "pcm"
            and len(state.audio_buffer) % (state.declared_audio_format.frame_bytes or 1)
        ):
            return False, "AUDIO_FORMAT_INVALID"
        return True, None
    probe = probe_stream_audio(
        bytes(state.audio_buffer[:512]),
        declared=state.declared_audio_format,
        final=final,
    )
    if probe.status == StreamAudioProbeStatus.NEED_MORE:
        return False, None
    if probe.status == StreamAudioProbeStatus.MISMATCH:
        return False, "AUDIO_FORMAT_MISMATCH"
    if probe.status == StreamAudioProbeStatus.INVALID:
        return False, "AUDIO_FORMAT_INVALID"
    state.audio_format_validated = True
    state.resolved_audio_format = probe.resolved_mime_type
    return True, None


async def _reject_invalid_stream_audio(
    websocket: WebSocket,
    error_code: str,
) -> None:
    await websocket.send_text(json.dumps(_err_payload(
        error_code,
        "Invalid audio stream",
        422,
        "The audio payload does not match the declared supported stream format.",
    )))
    await websocket.close(code=4400, reason="audio format invalid")


async def _emit_audio_health_events(
    websocket: WebSocket,
    state: _StreamState,
    chunk: bytes,
) -> None:
    monitor = state.audio_health_monitor
    if monitor is None:
        return
    for event in monitor.process(chunk):
        state.audio_event_count += 1
        data = StreamAudioEventData(
            event=event.event,
            channel=event.channel,
            startTimeMs=event.start_time_ms,
        )
        await _audit_state(
            state,
            "stt.stream.audio_event",
            details={
                "event": event.event,
                "channel": event.channel,
                "start_time_ms": event.start_time_ms,
                "audio_event_count": state.audio_event_count,
            },
        )
        await websocket.send_text(_json(StreamAudioEventMessage(
            type="audioEvent",
            data=data,
        )))


async def _emit_real_transcript(websocket: WebSocket, state: _StreamState) -> bool:
    if not state.audio_buffer or len(state.audio_buffer) <= state.last_processed_bytes:
        return False
    if not state.audio_format_validated or state.resolved_audio_format is None:
        raise RuntimeError("stream_audio_format_unvalidated")
    audio = bytes(state.audio_buffer)
    decode = await validate_stream_audio_decode(
        audio,
        media_type=state.resolved_audio_format,
    )
    if decode.status != StreamMediaDecodeStatus.VALID:
        raise _StreamMediaDecodeFailure(decode.status)
    transcription = state.config.transcription
    keyterms = tuple(item.term for item in state.config.keyterms.terms)
    transcription_options: dict[str, Any] = {
        "primary_language": transcription.primaryLanguage,
    }
    if keyterms:
        transcription_options["keyterms"] = keyterms
    declared = state.declared_audio_format
    if transcription.isMultichannel:
        if declared is None or declared.channels is None:
            raise RuntimeError("stream_multichannel_format_unavailable")
        channel_audio = deinterleave_pcm_s16le(audio, channels=declared.channels)
        channel_results = []
        mono_media_type = (
            "audio/pcm; rate=16000; channels=1; bits=16; "
            "endian=little; encoding=sint"
        )
        for channel, payload in enumerate(channel_audio):
            text, error = await transcribe_stream_audio(
                payload,
                media_type=mono_media_type,
                **transcription_options,
            )
            channel_results.append((channel, text, error))
    else:
        text, error = await transcribe_stream_audio(
            audio,
            media_type=state.resolved_audio_format,
            **transcription_options,
        )
        channel_results = [(0, text, error)]
    state.last_processed_bytes = len(audio)
    if not any(text for _, text, _ in channel_results):
        error = next((error for _, _, error in channel_results if error), "")
        await _save_checkpoint_state(state)
        await websocket.send_text(json.dumps(_err_payload(
            "UNSUPPORTED_LANGUAGE" if error == "unsupported_language" else "STT_UNAVAILABLE",
            "Transcription unavailable",
            503,
            "The configured ASR engine could not produce a transcript.",
        )))
        return False

    replacements = [item.model_dump(mode="json") for item in state.config.replacements]
    elapsed_seconds = max(
        0.0,
        (datetime.now(timezone.utc) - state.started_at).total_seconds(),
    )
    segments: list[StreamTranscript] = []
    for channel, text, _error in channel_results:
        if not text:
            continue
        normalized = apply_requested_replacements(text, replacements)
        if normalized == state.channel_transcript_text.get(channel):
            continue
        state.channel_transcript_text[channel] = normalized
        segment = StreamTranscript(
            id=str(uuid.uuid4()),
            transcript=normalized,
            final=True,
            speakerId=-1,
            participant={"channel": channel},
            time={"start": 0.0, "end": round(elapsed_seconds, 3)},
        )
        await _persist_transcript(state, segment)
        segments.append(segment)
    if not segments:
        await _save_checkpoint_state(state)
        return False
    state.transcript_text = _aggregate_channel_transcripts(state)
    state.transcript_seq += 1
    await _save_checkpoint_state(state)
    await websocket.send_text(_json(StreamTranscriptMessage(type="transcript", data=segments)))
    return True


def _aggregate_channel_transcripts(state: _StreamState) -> str:
    roles = {
        participant.channel: participant.role
        for participant in state.config.transcription.participants
    }
    lines = []
    for channel, text in sorted(state.channel_transcript_text.items()):
        normalized = text.strip()
        if not normalized:
            continue
        if state.config.transcription.isMultichannel:
            label = roles.get(channel) or f"channel-{channel}"
            lines.append(f"[{label}] {normalized}")
        else:
            lines.append(normalized)
    return "\n".join(lines)


def _fact_generation_interval_seconds(attempts: int, mode: str | None) -> float:
    """Return the documented approximate Corti schedule without claiming exact timing."""
    if mode != "fast_init":
        return 60.0
    if attempts <= 0:
        return 10.0
    if attempts == 1:
        return 20.0
    return float(min(60, round(26 + 12 * math.log2(attempts - 1 or 1))))


def _merge_provider_usage(
    current: dict[str, int | float | str],
    incoming: dict[str, int | float | str],
) -> None:
    for key, value in incoming.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            prior = current.get(key, 0)
            if isinstance(prior, (int, float)) and not isinstance(prior, bool):
                current[key] = prior + value
        elif isinstance(value, str):
            current[key] = value


async def _emit_real_facts(websocket: WebSocket, state: _StreamState) -> int:
    if state.config.mode.type != "facts" or not state.transcript_text.strip():
        return 0
    state.fact_generation_attempts += 1
    try:
        extraction = await extract_stream_facts_with_usage(
            state.transcript_text,
            output_language=state.config.mode.outputLocale or "zh-CN",
        )
    except Exception as exc:
        logger.warning("Ambient fact extraction failed type=%s", type(exc).__name__)
        await websocket.send_text(json.dumps(_err_payload(
            "FACTS_UNAVAILABLE",
            "Fact extraction unavailable",
            503,
            "The configured fact extraction engine is unavailable.",
        )))
        return 0

    _merge_provider_usage(state.provider_usage, extraction.usage)
    facts: list[StreamFact] = []
    for item in extraction.facts:
        if not isinstance(item, ExtractedStreamFact):
            continue
        identity = (item.group, item.text)
        if identity in state.emitted_facts:
            continue
        now = datetime.now(timezone.utc)
        fact = StreamFact(
            id=str(uuid.uuid4()),
            text=item.text,
            group=item.group,
            groupId="",
            isDiscarded=False,
            source="core",
            createdAt=now,
            updatedAt=now,
            createdAtTzOffset="+00:00",
            updatedAtTzOffset="+00:00",
        )
        await _persist_fact(state, fact)
        state.emitted_facts.add(identity)
        state.fact_seq += 1
        facts.append(fact)
    await _save_checkpoint_state(state)
    if facts:
        await websocket.send_text(_json(StreamFactsMessage(type="facts", fact=facts)))
    return len(facts)


async def _handle_flush(websocket: WebSocket, state: _StreamState) -> None:
    await _emit_real_transcript(websocket, state)
    await _emit_real_facts(websocket, state)
    await websocket.send_text(_json(StreamFlushedMessage(type="flushed")))
    # iCoDer development/runtime credits actually charged by this endpoint.
    # Provider token/cost telemetry is audited separately; it is never mapped
    # to Corti credits by an invented conversion formula.
    await websocket.send_text(_json(StreamDeltaUsageMessage(type="delta_usage", credits=0.0)))


async def _handle_end(websocket: WebSocket, state: _StreamState) -> None:
    await _emit_real_transcript(websocket, state)
    await _emit_real_facts(websocket, state)
    await _persist_recording(state)
    await _audit_state(
        state,
        "stt.stream.ended",
        details={
            "retention_policy": state.config.retentionPolicy,
            "transcript_messages": state.transcript_seq,
            "fact_messages": state.fact_seq,
            "provider_usage": state.provider_usage,
            "credits_charged": 0.0,
        },
    )
    if state.checkpoint_enabled and not await _discard_checkpoint(state):
        raise RuntimeError("stream_checkpoint_completion_fence_lost")
    state.ended = True
    # Current Corti order is usage then ENDED, after which the socket closes.
    await websocket.send_text(_json(StreamUsageMessage(type="usage", credits=0.0)))
    await websocket.send_text(_json(StreamEndedMessage(type="ENDED")))


@router.websocket("/streams/{interaction_id}")
async def streams_websocket(
    websocket: WebSocket,
    interaction_id: str,
    token: str = Query(..., min_length=1, max_length=8192),
    tenant_name: str = Query(..., alias="tenant-name", min_length=1, max_length=128),
    environment: str = Query(..., min_length=2, max_length=8),
) -> None:
    try:
        normalized_interaction_id = str(uuid.UUID(interaction_id))
    except (TypeError, ValueError, AttributeError):
        await websocket.close(code=4400, reason="invalid interaction id")
        return

    try:
        principal = await _authenticate_stream(token, tenant_name, environment)
    except HTTPException as exc:
        code = 4401 if exc.status_code == 401 else 4403
        await websocket.close(code=code, reason="stream authorization failed")
        return
    except Exception:
        await websocket.close(code=4401, reason="stream authorization failed")
        return

    state = _StreamState(
        interaction_id=normalized_interaction_id,
        session_id=str(uuid.uuid4()),
        principal=principal,
    )
    key = _stream_key(state)
    if key in _active_streams:
        await websocket.close(code=4409, reason="stream already active")
        return

    try:
        lease_acquired = await _acquire_stream_lease(
            state.lease_scope,
            state.session_id,
        )
    except Exception:
        logger.warning("streams lease acquisition unavailable session_id=%s", state.session_id)
        await websocket.close(code=1013, reason="stream coordination unavailable")
        return
    if not lease_acquired:
        await websocket.close(code=4409, reason="stream already active")
        return

    try:
        await websocket.accept()
    except Exception:
        try:
            await _release_stream_lease(state.lease_scope, state.session_id)
        except Exception:
            logger.warning("streams pre-accept lease release failed session_id=%s", state.session_id)
        return
    _active_streams[key] = state
    lease_heartbeat = asyncio.create_task(
        _stream_lease_heartbeat(websocket, state),
        name=f"streams-lease-heartbeat-{state.session_id}",
    )
    logger.info("streams WSS opened session_id=%s", state.session_id)

    try:
        try:
            first_raw = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=_CONFIG_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            await websocket.send_text(_json(_config_status(
                "CONFIG_NOT_PROVIDED",
                state.interaction_id,
                "configuration_not_provided",
            )))
            await websocket.close(code=4408, reason="configuration not provided")
            return
        except WebSocketDisconnect:
            return

        try:
            config_payload = json.loads(first_raw) if first_raw else {}
        except (json.JSONDecodeError, TypeError):
            config_payload = {}
        parsed, reason = _validate_config(config_payload)
        if parsed is None:
            await websocket.send_text(_json(_config_status(
                "CONFIG_DENIED",
                state.interaction_id,
                reason,
            )))
            await websocket.close(code=4400, reason="configuration denied")
            return

        state.configuration = parsed
        state.declared_audio_format = parse_declared_stream_audio_format(
            state.config.audioFormat
        )
        if state.config.audioEvents.enabled:
            channels = state.declared_audio_format.channels if state.declared_audio_format else 1
            state.audio_health_monitor = (
                PcmS16leMultichannelHealthMonitor(
                    sample_rate=16000,
                    channels=channels or 1,
                )
                if (channels or 1) > 1
                else PcmS16leMonoHealthMonitor(sample_rate=16000)
            )
        try:
            await _resume_or_initialize_checkpoint(state)
        except StreamCheckpointConfigurationMismatch as exc:
            await websocket.send_text(_json(_config_status(
                "CONFIG_DENIED",
                state.interaction_id,
                exc.code,
            )))
            await websocket.close(code=4409, reason="resume configuration mismatch")
            return
        except StreamCheckpointEncryptionRequired as exc:
            await websocket.send_text(_json(_config_status(
                "CONFIG_DENIED",
                state.interaction_id,
                exc.code,
            )))
            await websocket.close(code=4403, reason="stream encryption required")
            return
        except StreamCheckpointIntegrityError:
            await websocket.send_text(json.dumps(_err_payload(
                "STREAM_CHECKPOINT_CORRUPT",
                "Stream checkpoint unavailable",
                500,
                "The retained stream state failed its integrity check.",
            )))
            await websocket.close(code=1011, reason="stream checkpoint corrupt")
            return
        except StreamCheckpointError:
            await websocket.send_text(json.dumps(_err_payload(
                "STREAM_CHECKPOINT_UNAVAILABLE",
                "Stream checkpoint unavailable",
                503,
                "The retained stream state could not be opened.",
            )))
            await websocket.close(code=1013, reason="stream checkpoint unavailable")
            return
        if state.audio_health_monitor is not None and state.audio_buffer:
            for offset in range(0, len(state.audio_buffer), _MAX_AUDIO_CHUNK_BYTES):
                state.audio_health_monitor.process(
                    bytes(state.audio_buffer[offset:offset + _MAX_AUDIO_CHUNK_BYTES])
                )
        await _audit_state(
            state,
            "stt.stream.configured",
            details={
                "environment": environment.casefold(),
                "mode": state.config.mode.type,
                "retention_policy": state.config.retentionPolicy,
                "primary_language": state.config.transcription.primaryLanguage,
                "is_diarization": state.config.transcription.diarize,
                "is_multichannel": state.config.transcription.isMultichannel,
                "participant_channels": [
                    participant.channel
                    for participant in state.config.transcription.participants
                ],
                "fact_generation_interval": (
                    state.config.mode.factGenerationInterval or "fixed"
                ),
                "keyterm_count": len(state.config.keyterms.terms),
                "audio_events_enabled": state.config.audioEvents.enabled,
                "audio_format": (
                    state.declared_audio_format.canonical_media_type
                    if state.declared_audio_format is not None
                    else "auto_detect"
                ),
                "checkpoint_resumed": state.checkpoint_resumed,
                "restored_audio_bytes": state.audio_bytes if state.checkpoint_resumed else 0,
                "restored_transcript_messages": (
                    state.transcript_seq if state.checkpoint_resumed else 0
                ),
                "restored_fact_messages": state.fact_seq if state.checkpoint_resumed else 0,
            },
        )
        await websocket.send_text(_json(StreamConfigAcceptedMessage(
            type="CONFIG_ACCEPTED",
            sessionId=state.session_id,
            configuration=state.config,
            resumed=state.checkpoint_resumed,
            restoredAudioBytes=state.audio_bytes if state.checkpoint_resumed else 0,
            restoredTranscriptMessages=(
                state.transcript_seq if state.checkpoint_resumed else 0
            ),
            restoredFactMessages=state.fact_seq if state.checkpoint_resumed else 0,
        )))

        last_emit_transcript = asyncio.get_running_loop().time()
        last_emit_fact = last_emit_transcript
        while True:
            try:
                message = await websocket.receive()
            except WebSocketDisconnect:
                break
            if message.get("type") == "websocket.disconnect":
                break

            if message.get("text") is not None:
                try:
                    obj = json.loads(message.get("text") or "")
                except (json.JSONDecodeError, TypeError):
                    obj = None
                if isinstance(obj, dict) and obj.get("type") == "end":
                    try:
                        StreamEndMessage.model_validate(obj)
                    except Exception:
                        await websocket.send_text(json.dumps(_err_payload(
                            "INVALID_END", "Invalid end message", 400, "Expected an exact end message.",
                        )))
                        continue
                    if not await _confirm_stream_lease(state):
                        state.lease_lost = True
                        await websocket.send_text(json.dumps(_err_payload(
                            "STREAM_COORDINATION_LOST",
                            "Stream coordination unavailable",
                            503,
                            "The stream no longer owns its interaction lease.",
                        )))
                        await websocket.close(
                            code=1013,
                            reason="stream coordination unavailable",
                        )
                        break
                    if state.audio_buffer:
                        _, audio_error = _validate_stream_audio_buffer(
                            state,
                            final=True,
                        )
                        if audio_error is not None:
                            state.checkpoint_recoverable = False
                            await _reject_invalid_stream_audio(websocket, audio_error)
                            break
                    await _handle_end(websocket, state)
                    break
                if isinstance(obj, dict) and obj.get("type") == "flush":
                    try:
                        StreamFlushMessage.model_validate(obj)
                    except Exception:
                        await websocket.send_text(json.dumps(_err_payload(
                            "INVALID_FLUSH", "Invalid flush message", 400, "Expected an exact flush message.",
                        )))
                        continue
                    if not await _confirm_stream_lease(state):
                        state.lease_lost = True
                        await websocket.send_text(json.dumps(_err_payload(
                            "STREAM_COORDINATION_LOST",
                            "Stream coordination unavailable",
                            503,
                            "The stream no longer owns its interaction lease.",
                        )))
                        await websocket.close(
                            code=1013,
                            reason="stream coordination unavailable",
                        )
                        break
                    if state.audio_buffer:
                        _, audio_error = _validate_stream_audio_buffer(
                            state,
                            final=True,
                        )
                        if audio_error is not None:
                            state.checkpoint_recoverable = False
                            await _reject_invalid_stream_audio(websocket, audio_error)
                            break
                    await _handle_flush(websocket, state)
                    continue
                if isinstance(obj, dict) and obj.get("type") == "config":
                    await websocket.send_text(_json(_config_status(
                        "CONFIG_ALREADY_RECEIVED",
                        state.interaction_id,
                        "configuration_already_received",
                    )))
                    continue
                await websocket.send_text(json.dumps(_err_payload(
                    "INVALID_CONTROL_MESSAGE",
                    "Invalid control message",
                    400,
                    "Only flush or end is accepted after configuration.",
                )))
                continue

            chunk = message.get("bytes")
            if chunk is None:
                continue
            if not chunk:
                await websocket.send_text(json.dumps(_err_payload(
                    "EMPTY_AUDIO_CHUNK", "Empty audio chunk", 400, "Audio chunks must not be empty.",
                )))
                continue
            if len(chunk) > _MAX_AUDIO_CHUNK_BYTES:
                state.checkpoint_recoverable = False
                await websocket.send_text(json.dumps(_err_payload(
                    "AUDIO_CHUNK_TOO_LARGE",
                    "Audio chunk too large",
                    413,
                    "A single audio chunk exceeds 64000 bytes.",
                )))
                break
            if len(state.audio_buffer) + len(chunk) > _stream_max_audio_bytes():
                state.checkpoint_recoverable = False
                await websocket.send_text(json.dumps(_err_payload(
                    "AUDIO_TOO_LARGE",
                    "Audio stream too large",
                    413,
                    "The accumulated audio stream exceeds the configured limit.",
                )))
                break
            state.audio_chunk_count += 1
            state.audio_bytes += len(chunk)
            state.audio_buffer.extend(chunk)
            await _emit_audio_health_events(websocket, state, chunk)
            audio_ready, audio_error = _validate_stream_audio_buffer(
                state,
                final=False,
            )
            if audio_error is not None:
                state.checkpoint_recoverable = False
                await _reject_invalid_stream_audio(websocket, audio_error)
                break
            try:
                await _append_checkpoint_chunk(state, chunk)
            except StreamCheckpointError:
                await websocket.send_text(json.dumps(_err_payload(
                    "STREAM_CHECKPOINT_UNAVAILABLE",
                    "Stream checkpoint unavailable",
                    503,
                    "The audio chunk could not be durably checkpointed.",
                )))
                await websocket.close(code=1013, reason="stream checkpoint unavailable")
                break
            if not audio_ready:
                continue
            now = asyncio.get_running_loop().time()
            test_mode = os.environ.get("ICODER_TEST_MODE") == "1"
            enough_new_audio = (
                len(state.audio_buffer) - state.last_processed_bytes >= _stream_asr_min_bytes()
            )
            transcript_due = enough_new_audio and (
                (test_mode and state.audio_chunk_count % 30 == 0)
                or (not test_mode and now - last_emit_transcript >= 3.0)
            )
            if transcript_due:
                await _emit_real_transcript(websocket, state)
                last_emit_transcript = now
            fact_interval = _fact_generation_interval_seconds(
                state.fact_generation_attempts,
                state.config.mode.factGenerationInterval,
            )
            test_chunk_interval = (
                30
                if state.config.mode.factGenerationInterval == "fast_init"
                and state.fact_generation_attempts == 0
                else 100
            )
            facts_due = state.config.mode.type == "facts" and state.transcript_text and (
                (test_mode and state.audio_chunk_count % test_chunk_interval == 0)
                or (not test_mode and now - last_emit_fact >= fact_interval)
            )
            if facts_due:
                await _emit_real_facts(websocket, state)
                last_emit_fact = now
    except _StreamMediaDecodeFailure as exc:
        state.checkpoint_recoverable = False
        if exc.status == StreamMediaDecodeStatus.INVALID:
            code = "AUDIO_DECODE_INVALID"
            status = 422
            close_code = 4400
            close_reason = "audio decode invalid"
        elif exc.status == StreamMediaDecodeStatus.TIMEOUT:
            code = "AUDIO_VALIDATION_TIMEOUT"
            status = 503
            close_code = 1013
            close_reason = "audio validation timeout"
        elif exc.status == StreamMediaDecodeStatus.BUSY:
            code = "AUDIO_VALIDATION_BUSY"
            status = 503
            close_code = 1013
            close_reason = "audio validation busy"
        else:
            code = "AUDIO_VALIDATION_UNAVAILABLE"
            status = 503
            close_code = 1013
            close_reason = "audio validation unavailable"
        try:
            await websocket.send_text(json.dumps(_err_payload(
                code,
                "Audio validation failed",
                status,
                "The encoded audio could not pass the isolated decoder validation.",
            )))
            await websocket.close(code=close_code, reason=close_reason)
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("streams WSS failed type=%s", type(exc).__name__)
        try:
            await websocket.send_text(json.dumps(_err_payload(
                "STREAMS_INTERNAL",
                "Internal error",
                500,
                "The stream could not be processed.",
            )))
        except Exception:
            pass
    finally:
        lease_heartbeat.cancel()
        await asyncio.gather(lease_heartbeat, return_exceptions=True)
        if _active_streams.get(key) is state:
            _active_streams.pop(key, None)
        if not state.ended:
            try:
                await _audit_state(state, "stt.stream.disconnected", status="failure")
            except Exception:
                logger.warning("streams disconnect audit failed session_id=%s", state.session_id)
        if (
            state.checkpoint_enabled
            and not state.ended
            and not state.checkpoint_recoverable
            and not state.lease_lost
        ):
            try:
                await _discard_checkpoint(state)
            except Exception:
                logger.warning(
                    "streams failed checkpoint discard session_id=%s",
                    state.session_id,
                )
        try:
            await _release_stream_lease(state.lease_scope, state.session_id)
        except Exception:
            logger.warning("streams lease release failed session_id=%s", state.session_id)
        if state.audio_buffer:
            state.audio_buffer[:] = b"\x00" * len(state.audio_buffer)
            state.audio_buffer.clear()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(
            "streams WSS closed session_id=%s audio_chunks=%d bytes=%d ended=%s",
            state.session_id,
            state.audio_chunk_count,
            state.audio_bytes,
            state.ended,
        )
