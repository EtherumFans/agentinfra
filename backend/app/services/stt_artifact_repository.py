"""Database repository for encrypted STT recordings and transcripts."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import delete, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stt_artifact import STTInteraction, STTRecording, STTTranscript
from app.services.phi_encryption import (
    decrypt_phi,
    decrypt_phi_bytes,
    encrypt_phi,
    encrypt_phi_bytes,
)
from app.services.database_tenancy import bind_tenant_to_transaction


_TRANSCRIPT_PAYLOAD_PREFIX = "icoder/stt-transcript-payload/v1\n"


def _validated_transcript_segments(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or len(value) > 1000:
        raise RuntimeError("stt_transcript_payload_invalid")
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise RuntimeError("stt_transcript_payload_invalid")
        channel = item.get("channel")
        participant = item.get("participant")
        speaker_id = item.get("speakerId")
        text = item.get("text")
        start = item.get("start")
        end = item.get("end")
        if (
            not all(
                isinstance(number, int) and not isinstance(number, bool)
                for number in (channel, participant, speaker_id, start, end)
            )
            or not isinstance(text, str)
            or len(text) > 2_000_000
            or start < 0
            or end < start
        ):
            raise RuntimeError("stt_transcript_payload_invalid")
        result.append(
            {
                "channel": channel,
                "participant": participant,
                "speakerId": speaker_id,
                "text": text,
                "start": start,
                "end": end,
            }
        )
    return tuple(result)


def _encode_transcript_segments(segments: tuple[dict[str, object], ...]) -> str:
    validated = _validated_transcript_segments(list(segments))
    return _TRANSCRIPT_PAYLOAD_PREFIX + json.dumps(
        {"segments": validated},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _decode_transcript_segments(raw: str) -> tuple[dict[str, object], ...] | None:
    if not raw.startswith(_TRANSCRIPT_PAYLOAD_PREFIX):
        return None
    try:
        payload = json.loads(raw[len(_TRANSCRIPT_PAYLOAD_PREFIX):])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("stt_transcript_payload_invalid") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("stt_transcript_payload_invalid")
    return _validated_transcript_segments(payload.get("segments"))


class STTArtifactRepository:
    @staticmethod
    async def _bind(db: AsyncSession, organization_id: str) -> None:
        await bind_tenant_to_transaction(db, organization_id)

    async def is_materialized(
        self, db: AsyncSession, organization_id: str, owner_id: str, interaction_id: str
    ) -> bool:
        await self._bind(db, organization_id)
        return bool(await db.scalar(select(exists().where(
            STTInteraction.organization_id == organization_id,
            STTInteraction.owner_id == owner_id,
            STTInteraction.interaction_id == interaction_id,
        ))))

    async def ensure_interaction(
        self, db: AsyncSession, organization_id: str, owner_id: str, interaction_id: str
    ) -> None:
        await self._bind(db, organization_id)
        if await self.is_materialized(db, organization_id, owner_id, interaction_id):
            return
        # Two first writes for the same interaction can race between the
        # existence check and INSERT. Keep the unique constraint authoritative
        # and isolate the losing INSERT in a savepoint so it cannot roll back
        # the surrounding recording/transcript transaction.
        try:
            async with db.begin_nested():
                db.add(STTInteraction(
                    organization_id=organization_id,
                    owner_id=owner_id,
                    interaction_id=interaction_id,
                ))
                await db.flush()
        except IntegrityError:
            if not await self.is_materialized(
                db, organization_id, owner_id, interaction_id
            ):
                raise

    async def put_recording(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        owner_id: str,
        interaction_id: str,
        recording_id: str,
        media_type: str,
        content: bytes,
    ) -> STTRecording:
        await self._bind(db, organization_id)
        await self.ensure_interaction(db, organization_id, owner_id, interaction_id)
        row = STTRecording(
            organization_id=organization_id,
            owner_id=owner_id,
            interaction_id=interaction_id,
            recording_id=recording_id,
            media_type=media_type,
            encrypted_content=encrypt_phi_bytes(content),
            byte_length=len(content),
            content_sha256=hashlib.sha256(content).hexdigest(),
        )
        db.add(row)
        await db.flush()
        return row

    async def list_recordings(self, db: AsyncSession, *, organization_id: str, owner_id: str, interaction_id: str) -> list[STTRecording]:
        await self._bind(db, organization_id)
        result = await db.execute(select(STTRecording).where(
            STTRecording.organization_id == organization_id,
            STTRecording.owner_id == owner_id,
            STTRecording.interaction_id == interaction_id,
        ).order_by(STTRecording.id))
        return list(result.scalars())

    async def get_recording(self, db: AsyncSession, *, organization_id: str, owner_id: str, interaction_id: str, recording_id: str) -> STTRecording | None:
        await self._bind(db, organization_id)
        return await db.scalar(select(STTRecording).where(
            STTRecording.organization_id == organization_id,
            STTRecording.owner_id == owner_id,
            STTRecording.interaction_id == interaction_id,
            STTRecording.recording_id == recording_id,
        ))

    @staticmethod
    def recording_content(row: STTRecording) -> bytes:
        content = decrypt_phi_bytes(row.encrypted_content)
        if hashlib.sha256(content).hexdigest() != row.content_sha256:
            raise RuntimeError("stt_recording_integrity_check_failed")
        return content

    async def delete_recording(self, db: AsyncSession, **scope) -> bool:
        await self._bind(db, scope["organization_id"])
        result = await db.execute(delete(STTRecording).where(
            STTRecording.organization_id == scope["organization_id"],
            STTRecording.owner_id == scope["owner_id"],
            STTRecording.interaction_id == scope["interaction_id"],
            STTRecording.recording_id == scope["recording_id"],
        ))
        return bool(result.rowcount)

    async def put_transcript(
        self,
        db: AsyncSession,
        *,
        participant_roles: tuple[tuple[int, str], ...],
        text: str | None = None,
        transcript_segments: tuple[dict[str, object], ...] | None = None,
        request_data: dict | None = None,
        **fields,
    ) -> STTTranscript:
        await self._bind(db, fields["organization_id"])
        await self.ensure_interaction(
            db, fields["organization_id"], fields["owner_id"], fields["interaction_id"]
        )
        if text is not None and transcript_segments is not None:
            raise ValueError("text_and_transcript_segments_are_mutually_exclusive")
        transcript_payload = (
            _encode_transcript_segments(transcript_segments)
            if transcript_segments is not None
            else text
        )
        row = STTTranscript(
            **fields,
            encrypted_text=(
                encrypt_phi(transcript_payload)
                if transcript_payload is not None
                else None
            ),
            encrypted_request_json=(
                encrypt_phi(json.dumps(request_data, ensure_ascii=False))
                if request_data is not None else None
            ),
            participant_roles_json=json.dumps(participant_roles, ensure_ascii=False),
        )
        db.add(row)
        await db.flush()
        return row

    async def list_transcripts(self, db: AsyncSession, *, organization_id: str, owner_id: str, interaction_id: str) -> list[STTTranscript]:
        await self._bind(db, organization_id)
        result = await db.execute(select(STTTranscript).where(
            STTTranscript.organization_id == organization_id,
            STTTranscript.owner_id == owner_id,
            STTTranscript.interaction_id == interaction_id,
        ).order_by(STTTranscript.id))
        return list(result.scalars())

    async def get_transcript(self, db: AsyncSession, *, organization_id: str, owner_id: str, interaction_id: str, transcript_id: str) -> STTTranscript | None:
        await self._bind(db, organization_id)
        return await db.scalar(select(STTTranscript).where(
            STTTranscript.organization_id == organization_id,
            STTTranscript.owner_id == owner_id,
            STTTranscript.interaction_id == interaction_id,
            STTTranscript.transcript_id == transcript_id,
        ))

    @staticmethod
    def transcript_text(row: STTTranscript) -> str:
        raw = decrypt_phi(row.encrypted_text) or ""
        segments = _decode_transcript_segments(raw)
        if segments is None:
            return raw
        return "\n".join(str(item["text"]) for item in segments)

    @staticmethod
    def transcript_segments(row: STTTranscript) -> tuple[dict[str, object], ...]:
        raw = decrypt_phi(row.encrypted_text) or ""
        return _decode_transcript_segments(raw) or ()

    @staticmethod
    def request_data(row: STTTranscript) -> dict:
        raw = decrypt_phi(row.encrypted_request_json)
        return json.loads(raw) if raw else {}

    @staticmethod
    def participant_roles(row: STTTranscript) -> tuple[tuple[int, str], ...]:
        return tuple((int(item[0]), str(item[1])) for item in json.loads(row.participant_roles_json))

    async def set_transcript_completed(
        self, db: AsyncSession, row: STTTranscript, text: str
    ) -> None:
        await self._bind(db, row.organization_id)
        row.encrypted_text = encrypt_phi(text)
        row.status = "completed"
        row.error_code = None
        row.error_detail = None
        await db.flush()

    async def set_transcript_completed_segments(
        self,
        db: AsyncSession,
        row: STTTranscript,
        segments: tuple[dict[str, object], ...],
    ) -> None:
        await self._bind(db, row.organization_id)
        row.encrypted_text = encrypt_phi(_encode_transcript_segments(segments))
        row.status = "completed"
        row.error_code = None
        row.error_detail = None
        await db.flush()

    async def set_transcript_failed(
        self, db: AsyncSession, row: STTTranscript, code: str, detail: str
    ) -> None:
        await self._bind(db, row.organization_id)
        row.status = "failed"
        row.error_code = code
        row.error_detail = encrypt_phi(detail)
        await db.flush()

    async def set_transcript_runtime_telemetry(
        self,
        db: AsyncSession,
        row: STTTranscript,
        telemetry: dict | None,
    ) -> None:
        """Persist only the bounded ASR accounting allowlist, encrypted."""
        if not isinstance(telemetry, dict) or not telemetry:
            return
        await self._bind(db, row.organization_id)
        safe: dict[str, object] = {}
        for key in ("schema", "provider", "model", "status"):
            value = telemetry.get(key)
            if (
                isinstance(value, str)
                and 0 < len(value) <= 256
                and all(
                    char.isascii()
                    and (char.isalnum() or char in "._:/@+-")
                    for char in value
                )
            ):
                safe[key] = value
        if safe.get("schema") != "icoder/stt-inference-telemetry/v1":
            safe.pop("schema", None)
        if safe.get("provider") not in {"funasr", "whisper"}:
            safe.pop("provider", None)
        if safe.get("status") not in {"complete", "empty", "failed"}:
            safe.pop("status", None)
        latency = telemetry.get("latency_ms")
        if (
            isinstance(latency, int)
            and not isinstance(latency, bool)
            and 0 <= latency <= 86_400_000
        ):
            safe["latency_ms"] = latency
        for key in ("fallback_used", "streaming"):
            if isinstance(telemetry.get(key), bool):
                safe[key] = telemetry[key]
        if not safe:
            return
        request_data = self.request_data(row)
        request_data["_runtimeTelemetry"] = safe
        row.encrypted_request_json = encrypt_phi(
            json.dumps(request_data, ensure_ascii=False)
        )
        await db.flush()

    async def list_processing(
        self, db: AsyncSession, organization_id: str
    ) -> list[STTTranscript]:
        await self._bind(db, organization_id)
        result = await db.execute(
            select(STTTranscript).where(
                STTTranscript.organization_id == organization_id,
                STTTranscript.status == "processing",
            )
        )
        return list(result.scalars())

    async def delete_transcript(self, db: AsyncSession, **scope) -> bool:
        await self._bind(db, scope["organization_id"])
        result = await db.execute(delete(STTTranscript).where(
            STTTranscript.organization_id == scope["organization_id"],
            STTTranscript.owner_id == scope["owner_id"],
            STTTranscript.interaction_id == scope["interaction_id"],
            STTTranscript.transcript_id == scope["transcript_id"],
        ))
        return bool(result.rowcount)


stt_artifact_repository = STTArtifactRepository()
