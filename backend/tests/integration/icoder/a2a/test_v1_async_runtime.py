"""Durable-worker contracts for A2A v1 asynchronous Tasks."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select

from app import database
from app.icoder.agent_runtime.a2a.v1.task_runtime import A2ATaskRuntime
from app.icoder.agent_runtime.a2a.v1.artifact_store import (
    ARTIFACT_STREAM_CHUNK_CHARS,
    decode_event_artifact,
    load_task_artifacts,
)
from app.icoder.agent_runtime.a2a.v1.protocol import parse_v1_message
from app.icoder.agent_runtime.a2a.v1.routes import (
    _cancel_task,
    _finalize_task_after_send,
    _prepare_message,
)
from app.icoder.agent_runtime.a2a.v1.task_runtime import load_task_result
from app.icoder.agent_runtime.context.db_models import (
    A2ATaskArtifactRow,
    A2ATaskEventRow,
    A2ATaskExecutionRow,
    ContextMessageRow,
    ContextRow,
    ContextTaskRefRow,
)
from app.icoder.agent_runtime.context.context_repository import ContextRepository
from app.icoder.agent_runtime.orchestrator.inbound_handler import InboundResponse
from app.services.phi_encryption import encrypt_phi


class _BlockingHandler:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def handle(self, _agent_id, request):
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("synthetic blocking handler was not released")
        return _response(request.message.context_id, request.message.interaction_id)


class _ImmediateHandler:
    def handle(self, _agent_id, request):
        return _response(request.message.context_id, request.message.interaction_id)


class _LongImmediateHandler:
    def __init__(self) -> None:
        self.text = "验" * (ARTIFACT_STREAM_CHUNK_CHARS * 2 + 17)

    def handle(self, _agent_id, request):
        return _response(
            request.message.context_id,
            request.message.interaction_id,
            text=self.text,
        )


class _RequiredConnectorFailureHandler:
    def handle(self, _agent_id, _request):
        return InboundResponse(
            kind="error",
            error={
                "code": "connector_graph_failed",
                "message": "required connector failed",
            },
            http_status=502,
        )


class _InputRequiredHandler:
    def handle(self, _agent_id, request):
        return InboundResponse(
            kind="task",
            task_id=str(request.metadata.get("_a2a_v1_task_id") or ""),
            task_state="input-required",
            message_id=f"prompt-{uuid.uuid4()}",
            context_id=request.message.context_id,
            role="agent",
            parts=[{"kind": "text", "text": "请确认主要诊断"}],
            metadata={"reason": "clinical-clarification"},
            redacted_input="safe:initial-note",
        )


def _response(
    context_id: str,
    interaction_id: str,
    *,
    text: str = "completed after recovery",
) -> InboundResponse:
    return InboundResponse(
        kind="message",
        message_id=f"agent-{uuid.uuid4()}",
        context_id=context_id,
        role="agent",
        parts=[{"kind": "text", "text": text}],
        metadata={"test": True},
        redacted_input=f"safe:{interaction_id}",
    )


async def _seed_submitted_execution() -> tuple[str, str]:
    context_id = str(uuid.uuid4())
    task_id = f"task-{uuid.uuid4().hex}"
    message_id = f"message-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    legacy_params = {
        "message": {
            "role": "user",
            "messageId": message_id,
            "contextId": context_id,
            "parts": [{"kind": "text", "text": "safe recovery input"}],
            "metadata": {"_a2a_v1_task_id": task_id},
        },
        "configuration": {"returnImmediately": False},
    }
    encrypted = encrypt_phi(json.dumps({
        "request_id": "recover-request",
        "legacy_params": legacy_params,
    }))
    assert encrypted
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
        db.add(ContextTaskRefRow(
            context_id=context_id,
            task_id=task_id,
            state="submitted",
            started_at=now,
            completed_at=None,
        ))
        db.add(A2ATaskExecutionRow(
            task_id=task_id,
            context_id=context_id,
            organization_id="org_default1",
            agent_id="medcoder-coding-review",
            message_id=message_id,
            request_json=encrypted,
            result_json=None,
            error_code=None,
            attempt_count=0,
            lease_owner=None,
            lease_expires_at=None,
            created_at=now,
            updated_at=now,
        ))
        db.add(A2ATaskEventRow(
            task_id=task_id,
            context_id=context_id,
            organization_id="org_default1",
            agent_id="medcoder-coding-review",
            state="submitted",
            event_type="submitted",
            created_at=now,
        ))
        await db.commit()
    return context_id, task_id


async def _cleanup(context_id: str) -> None:
    async with database.AsyncSessionLocal() as db:
        await db.execute(delete(A2ATaskArtifactRow).where(A2ATaskArtifactRow.context_id == context_id))
        await db.execute(delete(A2ATaskEventRow).where(A2ATaskEventRow.context_id == context_id))
        await db.execute(delete(A2ATaskExecutionRow).where(A2ATaskExecutionRow.context_id == context_id))
        await db.execute(delete(ContextMessageRow).where(ContextMessageRow.context_id == context_id))
        await db.execute(delete(ContextTaskRefRow).where(ContextTaskRefRow.context_id == context_id))
        await db.execute(delete(ContextRow).where(ContextRow.id == context_id))
        await db.commit()


@pytest.mark.asyncio
async def test_input_required_task_is_durable_resumable_and_completes() -> None:
    context_id, task_id = await _seed_submitted_execution()
    runtime = A2ATaskRuntime(_InputRequiredHandler())
    app = FastAPI()
    try:
        runtime.schedule(app, task_id)
        pending = list(runtime._tasks.values())
        if pending:
            await asyncio.gather(*pending)

        async with database.AsyncSessionLocal() as db:
            task = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            execution = await db.get(A2ATaskExecutionRow, task_id)
            stored = await load_task_result(db, task_id)
            assert task is not None and task.state == "input-required"
            assert task.completed_at is None
            assert execution is not None and execution.lease_owner is None
            assert stored is not None
            assert stored["status"]["state"] == "input-required"
            assert stored["status"]["message"]["parts"][0]["text"] == "请确认主要诊断"

        canonical, _configuration = parse_v1_message({
            "message": {
                "messageId": f"resume-{uuid.uuid4()}",
                "taskId": task_id,
                "role": "ROLE_USER",
                "parts": [{"text": "已确认主要诊断", "mediaType": "text/plain"}],
            }
        })
        async with database.AsyncSessionLocal() as db:
            prepared = await _prepare_message(
                db,
                "org_default1",
                "medcoder-coding-review",
                canonical,
            )
            assert prepared.context_id == context_id
            working = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            assert working is not None and working.state == "working"

            response = JSONResponse({
                "jsonrpc": "2.0",
                "id": "resume-request",
                "result": {
                    "kind": "message",
                    "messageId": f"done-{uuid.uuid4()}",
                    "contextId": context_id,
                    "role": "agent",
                    "parts": [{"kind": "text", "text": "编码建议已完成"}],
                    "metadata": {},
                },
            })
            await _finalize_task_after_send(
                db,
                organization_id="org_default1",
                agent_id="medcoder-coding-review",
                task_id=task_id,
                response=response,
            )

        async with database.AsyncSessionLocal() as db:
            completed = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            stored = await load_task_result(db, task_id)
            events = (
                await db.execute(
                    select(A2ATaskEventRow)
                    .where(A2ATaskEventRow.task_id == task_id)
                    .order_by(A2ATaskEventRow.sequence_id)
                )
            ).scalars().all()
            assert completed is not None and completed.state == "completed"
            assert completed.completed_at is not None
            assert stored is not None and stored["kind"] == "message"
            state_events = [
                event.state for event in events if event.event_type != "artifact"
            ]
            assert state_events[-3:] == [
                "input-required", "working", "completed",
            ]
    finally:
        await runtime.stop()
        await _cleanup(context_id)


@pytest.mark.asyncio
async def test_graceful_stop_releases_lease_and_next_runtime_recovers() -> None:
    context_id, task_id = await _seed_submitted_execution()
    blocking = _BlockingHandler()
    first_runtime = A2ATaskRuntime(blocking)
    app = FastAPI()

    try:
        first_runtime.schedule(app, task_id)
        assert await asyncio.to_thread(blocking.started.wait, 2)

        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            task = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            assert execution is not None and execution.lease_owner == first_runtime._owner
            assert task is not None and task.state == "working"

        await first_runtime.stop()
        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            assert execution is not None
            assert execution.lease_owner is None
            assert execution.lease_expires_at is None

        # A new process/runtime can immediately reclaim the still-working row;
        # it does not need to wait for the original five-minute lease.
        second_runtime = A2ATaskRuntime(_ImmediateHandler())
        await second_runtime.start(app)
        pending = list(second_runtime._tasks.values())
        if pending:
            await asyncio.gather(*pending)

        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            task = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            events = (
                await db.execute(
                    select(A2ATaskEventRow)
                    .where(A2ATaskEventRow.task_id == task_id)
                    .order_by(A2ATaskEventRow.sequence_id)
                )
            ).scalars().all()
            assert execution is not None and execution.attempt_count == 2
            assert task is not None and task.state == "completed"
            artifacts = (
                await db.execute(
                    select(A2ATaskArtifactRow).where(
                        A2ATaskArtifactRow.context_id == context_id,
                        A2ATaskArtifactRow.task_id == task_id,
                    )
                )
            ).scalars().all()
            assert {artifact.artifact_id for artifact in artifacts} == {
                f"{task_id}-result",
                f"{task_id}-validated-stream",
            }
            assert [event.event_type for event in events] == [
                "submitted",
                "working",
                "recovered",
                "artifact",
                "artifact",
                "completed",
            ]
    finally:
        blocking.release.set()
        await first_runtime.stop()
        await _cleanup(context_id)


@pytest.mark.asyncio
async def test_validated_response_is_persisted_as_exact_multi_chunk_stream() -> None:
    context_id, task_id = await _seed_submitted_execution()
    handler = _LongImmediateHandler()
    runtime = A2ATaskRuntime(handler)
    try:
        await runtime._run(task_id)
        async with database.AsyncSessionLocal() as db:
            task = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            assert task is not None and task.state == "completed"
            events = (
                await db.execute(
                    select(A2ATaskEventRow)
                    .where(
                        A2ATaskEventRow.task_id == task_id,
                        A2ATaskEventRow.artifact_id
                        == f"{task_id}-validated-stream",
                    )
                    .order_by(A2ATaskEventRow.sequence_id)
                )
            ).scalars().all()
            assert len(events) == 3
            assert [event.artifact_append for event in events] == [
                False,
                True,
                True,
            ]
            assert [event.artifact_last_chunk for event in events] == [
                False,
                False,
                True,
            ]
            exact_chunks = [decode_event_artifact(event) for event in events]
            assert all(chunk is not None for chunk in exact_chunks)
            assert len({event.artifact_payload_sha256 for event in events}) == 3

            artifacts = await load_task_artifacts(
                db, context_id=context_id, task_id=task_id
            )
            stream = next(
                artifact
                for artifact in artifacts
                if artifact["artifactId"] == f"{task_id}-validated-stream"
            )
            serialized_parts = "".join(
                str(part.get("text") or "") for part in stream["parts"]
            )
            assert json.loads(serialized_parts) == [
                {"kind": "text", "text": handler.text}
            ]
    finally:
        await runtime.stop()
        await _cleanup(context_id)


@pytest.mark.asyncio
async def test_required_connector_failure_is_auditable_failed_terminal_task() -> None:
    context_id, task_id = await _seed_submitted_execution()
    runtime = A2ATaskRuntime(_RequiredConnectorFailureHandler())
    try:
        await runtime._run(task_id)
        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            task = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            events = (
                await db.execute(
                    select(A2ATaskEventRow)
                    .where(A2ATaskEventRow.task_id == task_id)
                    .order_by(A2ATaskEventRow.sequence_id)
                )
            ).scalars().all()
            assert execution is not None
            assert execution.error_code == "CONNECTOR_GRAPH_FAILED"
            assert execution.result_json is None
            assert execution.lease_owner is None
            assert task is not None and task.state == "failed"
            assert [event.event_type for event in events] == [
                "submitted",
                "working",
                "failed",
            ]
    finally:
        await runtime.stop()
        await _cleanup(context_id)


@pytest.mark.asyncio
async def test_local_working_task_can_be_canceled_without_late_result() -> None:
    context_id, task_id = await _seed_submitted_execution()
    blocking = _BlockingHandler()
    runtime = A2ATaskRuntime(blocking)
    app = FastAPI()

    try:
        runtime.schedule(app, task_id)
        assert await asyncio.to_thread(blocking.started.wait, 2)

        async with database.AsyncSessionLocal() as db:
            row = await _cancel_task(
                db,
                "org_default1",
                "medcoder-coding-review",
                task_id,
                task_runtime=runtime,
            )
            assert row.state == "canceled"

        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            task = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            events = (
                await db.execute(
                    select(A2ATaskEventRow)
                    .where(A2ATaskEventRow.task_id == task_id)
                    .order_by(A2ATaskEventRow.sequence_id)
                )
            ).scalars().all()
            assert execution is not None
            assert execution.lease_owner is None
            assert execution.lease_expires_at is None
            assert execution.result_json is None
            assert task is not None and task.state == "canceled"
            assert [event.event_type for event in events] == [
                "submitted",
                "working",
                "canceled",
            ]

        # The synthetic synchronous handler may still leave its worker thread
        # after release, but the canceled coroutine has no path to persist the
        # returned result or overwrite the durable terminal state.
        blocking.release.set()
        await asyncio.sleep(0.05)
        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            task = await db.get(
                ContextTaskRefRow,
                {"context_id": context_id, "task_id": task_id},
            )
            assert execution is not None and execution.result_json is None
            assert task is not None and task.state == "canceled"
    finally:
        blocking.release.set()
        await runtime.stop()
        await _cleanup(context_id)


@pytest.mark.asyncio
async def test_context_hard_delete_scrubs_async_payload_and_event_rows() -> None:
    context_id, task_id = await _seed_submitted_execution()
    async with database.AsyncSessionLocal() as db:
        counts = await ContextRepository(db).hard_delete_context(context_id)
        assert counts["a2a_task_executions"] == 1
        assert counts["a2a_task_events"] == 1
        assert await db.get(A2ATaskExecutionRow, task_id) is None
        remaining_events = (
            await db.execute(
                select(A2ATaskEventRow).where(A2ATaskEventRow.task_id == task_id)
            )
        ).scalars().all()
        assert remaining_events == []
        assert await db.get(ContextRow, context_id) is None
