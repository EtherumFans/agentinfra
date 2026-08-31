"""Durable Task Artifact ownership, content, and integrity contracts."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select

from app import database
from app.icoder.agent_runtime.a2a.v1.artifact_store import (
    ArtifactIntegrityError,
    ArtifactValidationError,
    decode_event_artifact,
    load_completed_stream_artifact,
    load_task_artifact,
    load_task_artifacts,
    normalize_artifact,
    persist_artifacts,
    validated_stream_artifact_chunks,
)
from app.icoder.agent_runtime.a2a.v1.task_runtime import append_task_event
from app.icoder.agent_runtime.context.db_models import (
    A2ATaskArtifactRow,
    A2ATaskEventRow,
    ContextRow,
    ContextTaskRefRow,
)
from app.services.phi_encryption import is_encrypted_value


async def _seed_owner() -> tuple[str, str, str]:
    context_id = str(uuid.uuid4())
    first_task = f"task-{uuid.uuid4().hex}"
    second_task = f"task-{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)
    async with database.AsyncSessionLocal() as db:
        db.add(ContextRow(
            id=context_id,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=1),
            agent_id="medcoder-coding-review",
            organization_id="org_default1",
            status="active",
            metadata_json="{}",
            redacted_input_hash="",
            original_input_ref="",
        ))
        db.add_all([
            ContextTaskRefRow(
                context_id=context_id,
                task_id=first_task,
                state="completed",
                started_at=now,
                completed_at=now,
            ),
            ContextTaskRefRow(
                context_id=context_id,
                task_id=second_task,
                state="completed",
                started_at=now,
                completed_at=now,
            ),
        ])
        await db.commit()
    return context_id, first_task, second_task


async def _cleanup(context_id: str) -> None:
    async with database.AsyncSessionLocal() as db:
        await db.execute(
            delete(A2ATaskEventRow).where(
                A2ATaskEventRow.context_id == context_id
            )
        )
        await db.execute(
            delete(A2ATaskArtifactRow).where(
                A2ATaskArtifactRow.context_id == context_id
            )
        )
        await db.execute(
            delete(ContextTaskRefRow).where(
                ContextTaskRefRow.context_id == context_id
            )
        )
        await db.execute(delete(ContextRow).where(ContextRow.id == context_id))
        await db.commit()


@pytest.mark.asyncio
async def test_artifact_is_encrypted_and_owned_by_exact_context_and_task(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    context_id, first_task, second_task = await _seed_owner()
    inline = base64.b64encode(b"synthetic report bytes").decode()
    artifact = {
        "artifactId": "art.synthetic-report",
        "name": "Synthetic report",
        "description": "Synthetic multi-part Artifact contract",
        "parts": [
            {"text": "safe synthetic summary", "mediaType": "text/plain"},
            {"data": {"score": 0.9}, "mediaType": "application/json"},
            {
                "raw": inline,
                "filename": "report.txt",
                "mediaType": "text/plain",
            },
            {
                "url": "https://objects.example.cn/synthetic/report.pdf",
                "filename": "report.pdf",
                "mediaType": "application/pdf",
            },
        ],
        "metadata": {"synthetic": True},
        "extensions": ["urn:icoder:artifact:synthetic:v1"],
    }
    try:
        async with database.AsyncSessionLocal() as db:
            await persist_artifacts(
                db,
                context_id=context_id,
                task_id=first_task,
                artifacts=[artifact],
            )
            await db.commit()

        async with database.AsyncSessionLocal() as db:
            row = await db.get(A2ATaskArtifactRow, {
                "context_id": context_id,
                "task_id": first_task,
                "artifact_id": "art.synthetic-report",
            })
            assert row is not None
            assert is_encrypted_value(row.payload_json)
            assert "safe synthetic summary" not in row.payload_json
            loaded = await load_task_artifacts(
                db, context_id=context_id, task_id=first_task
            )
            assert loaded == [normalize_artifact(artifact)]
            assert await load_task_artifact(
                db,
                context_id=context_id,
                task_id=second_task,
                artifact_id="art.synthetic-report",
            ) is None
    finally:
        await _cleanup(context_id)


@pytest.mark.asyncio
async def test_artifact_digest_corruption_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    context_id, task_id, _ = await _seed_owner()
    try:
        async with database.AsyncSessionLocal() as db:
            await persist_artifacts(
                db,
                context_id=context_id,
                task_id=task_id,
                artifacts=[{
                    "artifactId": "art.integrity",
                    "parts": [{"text": "safe synthetic content"}],
                }],
            )
            await db.commit()
        async with database.AsyncSessionLocal() as db:
            row = await db.get(A2ATaskArtifactRow, {
                "context_id": context_id,
                "task_id": task_id,
                "artifact_id": "art.integrity",
            })
            assert row is not None
            row.payload_sha256 = "0" * 64
            await db.commit()
        async with database.AsyncSessionLocal() as db:
            with pytest.raises(ArtifactIntegrityError):
                await load_task_artifact(
                    db,
                    context_id=context_id,
                    task_id=task_id,
                    artifact_id="art.integrity",
                )
    finally:
        await _cleanup(context_id)


def test_file_artifact_validation_rejects_unsafe_or_ambiguous_content() -> None:
    with pytest.raises(ArtifactValidationError):
        normalize_artifact({
            "artifactId": "art.local",
            "parts": [{"url": "file:///C:/sensitive.txt"}],
        })
    with pytest.raises(ArtifactValidationError):
        normalize_artifact({
            "artifactId": "art.ambiguous",
            "parts": [{"text": "x", "data": {"x": 1}}],
        })
    with pytest.raises(ArtifactValidationError):
        normalize_artifact({
            "artifactId": "art.invalid-base64",
            "parts": [{"raw": "not base64!!"}],
        })
    with pytest.raises(ArtifactValidationError):
        normalize_artifact({
            "artifactId": "art.invalid-extension",
            "parts": [{"text": "x"}],
            "extensions": ["not an absolute URI"],
        })


@pytest.mark.asyncio
async def test_artifact_event_replay_uses_exact_encrypted_chunks_and_detects_tamper(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    context_id, task_id, _ = await _seed_owner()
    chunks = validated_stream_artifact_chunks(
        task_id=task_id,
        parts=[{"kind": "text", "text": "甲" * 9000}],
        source_message_id="message-stream-integrity",
    )
    assert len(chunks) == 2
    try:
        async with database.AsyncSessionLocal() as db:
            for index, artifact in enumerate(chunks):
                append_task_event(
                    db,
                    task_id=task_id,
                    context_id=context_id,
                    organization_id="org_default1",
                    agent_id="medcoder-coding-review",
                    state="working",
                    event_type="artifact",
                    artifact_append=index > 0,
                    artifact_last_chunk=index == len(chunks) - 1,
                    artifact=artifact,
                )
            await db.commit()

        async with database.AsyncSessionLocal() as db:
            events = (
                await db.execute(
                    select(A2ATaskEventRow)
                    .where(A2ATaskEventRow.task_id == task_id)
                    .order_by(A2ATaskEventRow.sequence_id)
                )
            ).scalars().all()
            assert len(events) == 2
            assert all(is_encrypted_value(event.artifact_payload_json) for event in events)
            assert "甲" not in events[0].artifact_payload_json
            assert decode_event_artifact(events[0]) == chunks[0]
            assembled = await load_completed_stream_artifact(
                db,
                context_id=context_id,
                task_id=task_id,
                artifact_id=f"{task_id}-validated-stream",
            )
            assert assembled is not None
            assert json.loads("".join(
                str(part.get("text") or "") for part in assembled["parts"]
            )) == [{"kind": "text", "text": "甲" * 9000}]
            events[1].artifact_payload_sha256 = "0" * 64
            await db.commit()

        async with database.AsyncSessionLocal() as db:
            with pytest.raises(ArtifactIntegrityError):
                await load_completed_stream_artifact(
                    db,
                    context_id=context_id,
                    task_id=task_id,
                    artifact_id=f"{task_id}-validated-stream",
                )
    finally:
        await _cleanup(context_id)
