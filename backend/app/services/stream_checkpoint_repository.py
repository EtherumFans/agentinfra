"""Encrypted, fenced checkpoints for unfinished retained Streams sessions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stt_artifact import (
    STTStreamCheckpoint,
    STTStreamCheckpointChunk,
)
from app.services.phi_encryption import (
    decrypt_phi,
    decrypt_phi_bytes,
    encrypt_phi,
    encrypt_phi_bytes,
    is_encryption_enabled,
)
from app.services.stt_artifact_repository import stt_artifact_repository


_STATE_SCHEMA = "icoder/stt-stream-checkpoint/v1"
_MAX_STATE_BYTES = 1024 * 1024
_MAX_CHUNK_BYTES = 64_000
_MAX_AUDIO_BYTES = 32 * 1024 * 1024


class StreamCheckpointError(RuntimeError):
    code = "stream_checkpoint_error"


class StreamCheckpointConfigurationMismatch(StreamCheckpointError):
    code = "stream_checkpoint_configuration_mismatch"


class StreamCheckpointIntegrityError(StreamCheckpointError):
    code = "stream_checkpoint_integrity_failed"


class StreamCheckpointFenceLost(StreamCheckpointError):
    code = "stream_checkpoint_fence_lost"


class StreamCheckpointEncryptionRequired(StreamCheckpointError):
    code = "stream_checkpoint_encryption_required"


@dataclass(frozen=True, slots=True)
class RestoredStreamCheckpoint:
    state: dict[str, Any]
    audio: bytes
    resumed: bool


def _scope_filter(model, scope: dict[str, str]):
    return (
        model.organization_id == scope["organization_id"],
        model.owner_id == scope["owner_id"],
        model.interaction_id == scope["interaction_id"],
    )


def _canonical_state(state: dict[str, Any]) -> str:
    payload = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(payload.encode("utf-8")) > _MAX_STATE_BYTES:
        raise StreamCheckpointIntegrityError("stream checkpoint state is too large")
    return payload


def _encode_state(state: dict[str, Any]) -> tuple[str, str]:
    payload = _canonical_state(state)
    return encrypt_phi(payload) or "", hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _decode_state(row: STTStreamCheckpoint) -> dict[str, Any]:
    try:
        payload = decrypt_phi(row.encrypted_state_json)
        if not payload or hashlib.sha256(payload.encode("utf-8")).hexdigest() != row.state_sha256:
            raise StreamCheckpointIntegrityError("stream checkpoint state digest mismatch")
        state = json.loads(payload)
    except StreamCheckpointIntegrityError:
        raise
    except Exception as exc:
        raise StreamCheckpointIntegrityError("stream checkpoint state is unreadable") from exc
    if not isinstance(state, dict) or state.get("schema") != _STATE_SCHEMA:
        raise StreamCheckpointIntegrityError("stream checkpoint schema is invalid")
    return state


class StreamCheckpointRepository:
    async def resume_or_initialize(
        self,
        db: AsyncSession,
        *,
        scope: dict[str, str],
        session_id: str,
        state: dict[str, Any],
        enabled: bool,
    ) -> RestoredStreamCheckpoint | None:
        row = await db.scalar(
            select(STTStreamCheckpoint).where(*_scope_filter(STTStreamCheckpoint, scope))
        )
        if enabled and not is_encryption_enabled():
            raise StreamCheckpointEncryptionRequired(
                "retained stream recovery requires PHI encryption"
            )
        if row is None:
            if not enabled:
                return None
            encrypted, digest = _encode_state(state)
            await stt_artifact_repository.ensure_interaction(db, **scope)
            db.add(STTStreamCheckpoint(
                **scope,
                session_id=session_id,
                recording_id=str(state["recording_id"]),
                encrypted_state_json=encrypted,
                state_sha256=digest,
                audio_bytes=0,
                audio_chunk_count=0,
            ))
            await db.flush()
            return RestoredStreamCheckpoint(state=state, audio=b"", resumed=False)

        if not enabled:
            raise StreamCheckpointConfigurationMismatch(
                "a retained unfinished stream cannot resume with retention disabled"
            )
        restored = _decode_state(row)
        if restored.get("configuration") != state.get("configuration"):
            raise StreamCheckpointConfigurationMismatch(
                "resume configuration differs from the retained checkpoint"
            )

        result = await db.execute(
            select(STTStreamCheckpointChunk)
            .where(*_scope_filter(STTStreamCheckpointChunk, scope))
            .order_by(STTStreamCheckpointChunk.sequence)
        )
        chunks = list(result.scalars())
        if len(chunks) != row.audio_chunk_count:
            raise StreamCheckpointIntegrityError("stream checkpoint chunk count mismatch")
        audio_parts: list[bytes] = []
        for expected_sequence, chunk_row in enumerate(chunks, start=1):
            if chunk_row.sequence != expected_sequence:
                raise StreamCheckpointIntegrityError("stream checkpoint chunk sequence mismatch")
            try:
                content = decrypt_phi_bytes(chunk_row.encrypted_content)
            except Exception as exc:
                raise StreamCheckpointIntegrityError(
                    "stream checkpoint chunk is unreadable"
                ) from exc
            if (
                len(content) != chunk_row.byte_length
                or len(content) > _MAX_CHUNK_BYTES
                or hashlib.sha256(content).hexdigest() != chunk_row.content_sha256
            ):
                raise StreamCheckpointIntegrityError("stream checkpoint chunk digest mismatch")
            audio_parts.append(content)
        audio = b"".join(audio_parts)
        if (
            len(audio) != row.audio_bytes
            or len(audio) > _MAX_AUDIO_BYTES
            or restored.get("audio_bytes") != row.audio_bytes
            or restored.get("audio_chunk_count") != row.audio_chunk_count
        ):
            raise StreamCheckpointIntegrityError("stream checkpoint audio accounting mismatch")

        row.session_id = session_id
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return RestoredStreamCheckpoint(state=restored, audio=audio, resumed=True)

    async def append_chunk(
        self,
        db: AsyncSession,
        *,
        scope: dict[str, str],
        session_id: str,
        state: dict[str, Any],
        chunk: bytes,
    ) -> None:
        if not chunk or len(chunk) > _MAX_CHUNK_BYTES:
            raise StreamCheckpointIntegrityError("stream checkpoint chunk size is invalid")
        row = await db.scalar(select(STTStreamCheckpoint).where(
            *_scope_filter(STTStreamCheckpoint, scope),
            STTStreamCheckpoint.session_id == session_id,
        ))
        if row is None:
            raise StreamCheckpointFenceLost("stream checkpoint writer is no longer current")
        sequence = row.audio_chunk_count + 1
        expected_bytes = row.audio_bytes + len(chunk)
        if (
            state.get("audio_chunk_count") != sequence
            or state.get("audio_bytes") != expected_bytes
            or expected_bytes > _MAX_AUDIO_BYTES
        ):
            raise StreamCheckpointIntegrityError("stream checkpoint append accounting mismatch")
        encrypted, digest = _encode_state(state)
        db.add(STTStreamCheckpointChunk(
            **scope,
            sequence=sequence,
            encrypted_content=encrypt_phi_bytes(chunk),
            byte_length=len(chunk),
            content_sha256=hashlib.sha256(chunk).hexdigest(),
        ))
        row.encrypted_state_json = encrypted
        row.state_sha256 = digest
        row.audio_bytes = expected_bytes
        row.audio_chunk_count = sequence
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()

    async def save_state(
        self,
        db: AsyncSession,
        *,
        scope: dict[str, str],
        session_id: str,
        state: dict[str, Any],
    ) -> None:
        row = await db.scalar(select(STTStreamCheckpoint).where(
            *_scope_filter(STTStreamCheckpoint, scope),
            STTStreamCheckpoint.session_id == session_id,
        ))
        if row is None:
            raise StreamCheckpointFenceLost("stream checkpoint writer is no longer current")
        if (
            state.get("audio_bytes") != row.audio_bytes
            or state.get("audio_chunk_count") != row.audio_chunk_count
        ):
            raise StreamCheckpointIntegrityError("stream checkpoint state accounting mismatch")
        encrypted, digest = _encode_state(state)
        row.encrypted_state_json = encrypted
        row.state_sha256 = digest
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()

    async def discard(
        self,
        db: AsyncSession,
        *,
        scope: dict[str, str],
        session_id: str,
    ) -> bool:
        current = await db.scalar(select(STTStreamCheckpoint.session_id).where(
            *_scope_filter(STTStreamCheckpoint, scope)
        ))
        if current != session_id:
            return False
        await db.execute(delete(STTStreamCheckpointChunk).where(
            *_scope_filter(STTStreamCheckpointChunk, scope)
        ))
        deleted = await db.execute(delete(STTStreamCheckpoint).where(
            *_scope_filter(STTStreamCheckpoint, scope),
            STTStreamCheckpoint.session_id == session_id,
        ))
        return bool(deleted.rowcount)


stream_checkpoint_repository = StreamCheckpointRepository()


__all__ = [
    "RestoredStreamCheckpoint",
    "StreamCheckpointConfigurationMismatch",
    "StreamCheckpointError",
    "StreamCheckpointEncryptionRequired",
    "StreamCheckpointFenceLost",
    "StreamCheckpointIntegrityError",
    "StreamCheckpointRepository",
    "stream_checkpoint_repository",
]
