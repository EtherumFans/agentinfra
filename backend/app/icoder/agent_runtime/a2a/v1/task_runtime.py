"""Durable local worker for A2A v1 ``returnImmediately`` Tasks.

The database is the source of truth.  An in-process asyncio task is only a
wakeup mechanism: submitted rows survive restart, working rows carry a lease,
and startup can reclaim expired work.  This is sufficient for deterministic
development and single-service deployment while keeping Redis/event-bus
multi-worker delivery as an explicit production gate.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import or_, select, update

import app.database as database
from app.services.database_tenancy import bind_tenant_to_transaction
from app.services.phi_encryption import decrypt_phi, encrypt_phi

from ...context.context_repository import ContextRepository
from ...context.db_models import (
    A2ATaskEventRow,
    A2ATaskExecutionRow,
    ContextTaskRefRow,
)
from ..envelope import JsonRpcRequest
from ..routes_inbound import _dispatch
from ..task_state import TERMINAL_STATES, TaskState, settled_state_from_result
from .artifact_store import (
    VALIDATED_STREAM_ARTIFACT_SUFFIX,
    encode_event_artifact,
    load_completed_stream_artifact,
    persist_artifacts,
    result_artifacts,
    validated_stream_artifact_chunks,
)


logger = logging.getLogger(__name__)

LEASE_SECONDS = 300


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def append_task_event(
    db,
    *,
    task_id: str,
    context_id: str,
    organization_id: str,
    agent_id: str,
    state: str,
    event_type: str,
    artifact_id: str | None = None,
    artifact_append: bool | None = None,
    artifact_last_chunk: bool | None = None,
    artifact: dict[str, Any] | None = None,
) -> A2ATaskEventRow:
    artifact_payload_json: str | None = None
    artifact_payload_sha256: str | None = None
    artifact_payload_size_bytes: int | None = None
    if artifact is not None:
        (
            normalized_artifact,
            artifact_payload_json,
            artifact_payload_sha256,
            artifact_payload_size_bytes,
        ) = encode_event_artifact(artifact)
        normalized_id = str(normalized_artifact["artifactId"])
        if artifact_id is not None and artifact_id != normalized_id:
            raise ValueError("Artifact event identity does not match its payload")
        artifact_id = normalized_id
    event = A2ATaskEventRow(
        task_id=task_id,
        context_id=context_id,
        organization_id=organization_id,
        agent_id=agent_id,
        state=state,
        event_type=event_type,
        artifact_id=artifact_id,
        artifact_append=artifact_append,
        artifact_last_chunk=artifact_last_chunk,
        artifact_payload_json=artifact_payload_json,
        artifact_payload_sha256=artifact_payload_sha256,
        artifact_payload_size_bytes=artifact_payload_size_bytes,
        created_at=utc_now(),
    )
    db.add(event)
    return event


async def load_task_result(db, task_id: str) -> dict[str, Any] | None:
    execution = await db.get(A2ATaskExecutionRow, task_id)
    if execution is None or not execution.result_json:
        return None
    raw = decrypt_phi(execution.result_json)
    try:
        value = json.loads(raw or "null")
    except json.JSONDecodeError:
        logger.error("A2A task result is not valid JSON task_id=%s", task_id)
        return None
    return value if isinstance(value, dict) else None


class A2ATaskRuntime:
    """Lease-based asynchronous executor bound to one A2A handler."""

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self._owner = f"a2a-{uuid.uuid4().hex[:24]}"
        self._app: Any = None
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self, app: Any) -> None:
        self._app = app
        now = utc_now()
        async with database.AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(A2ATaskExecutionRow.task_id)
                    .join(
                        ContextTaskRefRow,
                        ContextTaskRefRow.task_id == A2ATaskExecutionRow.task_id,
                    )
                    .where(
                        ContextTaskRefRow.state.in_([
                            TaskState.SUBMITTED.value,
                            TaskState.WORKING.value,
                        ]),
                        or_(
                            A2ATaskExecutionRow.lease_expires_at.is_(None),
                            A2ATaskExecutionRow.lease_expires_at <= now,
                        ),
                    )
                )
            ).scalars().all()
        for task_id in rows:
            self.schedule(app, task_id)

    async def stop(self) -> None:
        pending = [task for task in self._tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._tasks.clear()
        self._app = None

    def schedule(self, app: Any, task_id: str) -> None:
        self._app = app
        existing = self._tasks.get(task_id)
        if existing is not None and not existing.done():
            return
        task = asyncio.create_task(
            self._run(task_id), name=f"a2a-task-{task_id}"
        )
        self._tasks[task_id] = task
        task.add_done_callback(
            lambda done, key=task_id: (
                self._tasks.pop(key, None)
                if self._tasks.get(key) is done
                else None
            )
        )

    async def cancel_running(self, task_id: str) -> bool:
        """Cancel work owned by this runtime and wait for lease release.

        This is deliberately process-local.  Returning ``True`` proves that
        the dispatch coroutine stopped and therefore cannot persist a late
        result.  It does not claim that a synchronous thread or an upstream
        Provider has physically stopped, so callers must keep remote-worker
        and unsupported-provider cancellation as an explicit not-cancelable
        outcome.
        """

        task = self._tasks.get(task_id)
        if task is None or task.done():
            return False
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return task.cancelled()

    async def _run(self, task_id: str) -> None:
        heartbeat: asyncio.Task | None = None
        try:
            claimed = await self._claim(task_id)
            if claimed is None:
                return
            execution, task_row = claimed
            heartbeat = asyncio.create_task(
                self._heartbeat(task_id),
                name=f"a2a-task-heartbeat-{task_id}",
            )

            recovered = await self._recover_persisted_message(execution, task_row)
            if recovered is not None:
                await self._persist_recovered_stream(execution, recovered)
                await self._finish(task_id, recovered)
                return

            raw_payload = decrypt_phi(execution.request_json)
            payload = json.loads(raw_payload or "{}")
            legacy_params = payload.get("legacy_params")
            if not isinstance(legacy_params, dict):
                raise ValueError("persisted A2A Task payload is invalid")
            request_id = payload.get("request_id")
            fake_request = Request({
                "type": "http",
                "method": "POST",
                "path": "/internal/a2a-task",
                "headers": [],
                "query_string": b"",
                "server": ("127.0.0.1", 0),
                "client": ("127.0.0.1", 0),
                "scheme": "http",
                "app": self._app,
            })
            envelope = JsonRpcRequest(
                jsonrpc="2.0",
                id=request_id,
                method="message/send",
                params=legacy_params,
            )
            loop = asyncio.get_running_loop()
            stream_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            def stream_sink(event: dict[str, Any]) -> None:
                if isinstance(event, dict):
                    loop.call_soon_threadsafe(stream_events.put_nowait, event)

            async def dispatch() -> JSONResponse:
                async with database.AsyncSessionLocal() as db:
                    await bind_tenant_to_transaction(
                        db, execution.organization_id
                    )
                    return await _dispatch(
                        self._handler,
                        execution.agent_id,
                        fake_request,
                        organization_id=execution.organization_id,
                        db=db,
                        allowed_methods=("message/send",),
                        parsed_request=envelope,
                        parsed_params=legacy_params,
                        stream_sink=stream_sink,
                        server_task_id=execution.task_id,
                    )

            dispatch_task = asyncio.create_task(
                dispatch(), name=f"a2a-task-dispatch-{task_id}"
            )
            try:
                while not dispatch_task.done() or not stream_events.empty():
                    try:
                        event = await asyncio.wait_for(
                            stream_events.get(), timeout=0.1
                        )
                    except TimeoutError:
                        continue
                    if event.get("step") == "a2a_validated_artifact_chunk":
                        await self._persist_artifact_chunk(execution, event)
                response = await dispatch_task
            except BaseException:
                if not dispatch_task.done():
                    dispatch_task.cancel()
                await asyncio.gather(dispatch_task, return_exceptions=True)
                raise
            await self._finish(task_id, response)
        except asyncio.CancelledError:
            await self._release_lease(task_id)
            raise
        except Exception as exc:
            logger.error(
                "A2A asynchronous Task failed task_id=%s error_type=%s",
                task_id,
                type(exc).__name__,
            )
            await self._fail_internal(task_id)
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

    async def _claim(
        self, task_id: str,
    ) -> tuple[A2ATaskExecutionRow, ContextTaskRefRow] | None:
        now = utc_now()
        lease_until = now + timedelta(seconds=LEASE_SECONDS)
        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            if execution is None:
                return None
            await bind_tenant_to_transaction(db, execution.organization_id)
            task_row = await db.get(
                ContextTaskRefRow,
                {"context_id": execution.context_id, "task_id": task_id},
            )
            if task_row is None or task_row.state not in {
                TaskState.SUBMITTED.value,
                TaskState.WORKING.value,
            }:
                return None
            lease_expires_at = _as_utc(execution.lease_expires_at)
            if (
                execution.lease_owner
                and execution.lease_owner != self._owner
                and lease_expires_at is not None
                and lease_expires_at > now
            ):
                return None

            previous_state = task_row.state
            claimed = await db.execute(
                update(A2ATaskExecutionRow)
                .where(
                    A2ATaskExecutionRow.task_id == task_id,
                    or_(
                        A2ATaskExecutionRow.lease_expires_at.is_(None),
                        A2ATaskExecutionRow.lease_expires_at <= now,
                        A2ATaskExecutionRow.lease_owner == self._owner,
                    ),
                )
                .values(
                    lease_owner=self._owner,
                    lease_expires_at=lease_until,
                    attempt_count=A2ATaskExecutionRow.attempt_count + 1,
                    updated_at=now,
                )
            )
            if not claimed.rowcount:
                await db.rollback()
                return None
            if previous_state == TaskState.SUBMITTED.value:
                started = await db.execute(
                    update(ContextTaskRefRow)
                    .where(
                        ContextTaskRefRow.context_id == execution.context_id,
                        ContextTaskRefRow.task_id == task_id,
                        ContextTaskRefRow.state == TaskState.SUBMITTED.value,
                    )
                    .values(state=TaskState.WORKING.value)
                )
                if not started.rowcount:
                    # A concurrent CancelTask won the state transition. Roll
                    # back the lease acquisition as part of the same DB
                    # transaction so canceled work can never be executed.
                    await db.rollback()
                    return None
            append_task_event(
                db,
                task_id=task_id,
                context_id=execution.context_id,
                organization_id=execution.organization_id,
                agent_id=execution.agent_id,
                state=TaskState.WORKING.value,
                event_type=(
                    "working" if previous_state == TaskState.SUBMITTED.value
                    else "recovered"
                ),
            )
            await db.commit()
            await db.refresh(execution)
            await db.refresh(task_row)
            return execution, task_row

    async def _heartbeat(self, task_id: str) -> None:
        """Renew an owned lease while a long Provider invocation is running."""

        interval = max(1.0, LEASE_SECONDS / 3)
        while True:
            await asyncio.sleep(interval)
            now = utc_now()
            try:
                async with database.AsyncSessionLocal() as db:
                    organization_id = (
                        await db.execute(
                            select(A2ATaskExecutionRow.organization_id).where(
                                A2ATaskExecutionRow.task_id == task_id
                            )
                        )
                    ).scalar_one_or_none()
                    if not organization_id:
                        return
                    await bind_tenant_to_transaction(db, organization_id)
                    renewed = await db.execute(
                        update(A2ATaskExecutionRow)
                        .where(
                            A2ATaskExecutionRow.task_id == task_id,
                            A2ATaskExecutionRow.lease_owner == self._owner,
                        )
                        .values(
                            lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                            updated_at=now,
                        )
                    )
                    await db.commit()
                    if not renewed.rowcount:
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                # A transient DB outage should not silently kill renewal. The
                # next interval retries; the original lease remains valid in
                # the meantime and _finish still owns the terminal CAS.
                logger.exception(
                    "A2A Task lease heartbeat failed task_id=%s", task_id
                )

    async def _release_lease(self, task_id: str) -> None:
        """Make interrupted work immediately recoverable by the next process."""

        now = utc_now()
        try:
            async with database.AsyncSessionLocal() as db:
                organization_id = (
                    await db.execute(
                        select(A2ATaskExecutionRow.organization_id).where(
                            A2ATaskExecutionRow.task_id == task_id
                        )
                    )
                ).scalar_one_or_none()
                if not organization_id:
                    return
                await bind_tenant_to_transaction(db, organization_id)
                await db.execute(
                    update(A2ATaskExecutionRow)
                    .where(
                        A2ATaskExecutionRow.task_id == task_id,
                        A2ATaskExecutionRow.lease_owner == self._owner,
                    )
                    .values(
                        lease_owner=None,
                        lease_expires_at=None,
                        updated_at=now,
                    )
                )
                await db.commit()
        except Exception:
            logger.exception(
                "A2A Task lease release failed task_id=%s", task_id
            )

    async def _recover_persisted_message(
        self,
        execution: A2ATaskExecutionRow,
        task_row: ContextTaskRefRow,
    ) -> JSONResponse | None:
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db, execution.organization_id)
            repo = ContextRepository(db)
            messages = await repo.get_messages(task_row.context_id)
        for message in reversed(messages):
            if (
                message.role == "agent"
                and str(message.metadata.get("a2a_v1_task_id") or "")
                == execution.task_id
            ):
                result = {
                    "kind": "message",
                    "role": "agent",
                    "messageId": message.message_id,
                    "contextId": execution.context_id,
                    "parts": message.parts,
                    "metadata": message.metadata,
                }
                return JSONResponse(content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "result": result,
                })
        return None

    async def _persist_recovered_stream(
        self,
        execution: A2ATaskExecutionRow,
        response: JSONResponse,
    ) -> None:
        """Reset an interrupted stream from the already durable Agent Message."""

        try:
            body = json.loads(bytes(response.body).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        result = body.get("result") if isinstance(body, dict) else None
        parts = result.get("parts") if isinstance(result, dict) else None
        if not isinstance(parts, list) or not parts:
            return
        chunks = validated_stream_artifact_chunks(
            task_id=execution.task_id,
            parts=parts,
            source_message_id=str(result.get("messageId") or ""),
        )
        for index, artifact in enumerate(chunks):
            await self._persist_artifact_chunk(execution, {
                "step": "a2a_validated_artifact_chunk",
                "payload": {
                    "artifact": artifact,
                    "append": index > 0,
                    "lastChunk": index == len(chunks) - 1,
                },
            })

    async def _persist_artifact_chunk(
        self,
        execution: A2ATaskExecutionRow,
        event: dict[str, Any],
    ) -> None:
        """Commit one exact validated Artifact chunk while the lease is owned."""

        payload = event.get("payload")
        if not isinstance(payload, dict) or not isinstance(
            payload.get("artifact"), dict
        ):
            raise ValueError("validated Artifact chunk payload is invalid")
        append = payload.get("append")
        last_chunk = payload.get("lastChunk")
        if not isinstance(append, bool) or not isinstance(last_chunk, bool):
            raise ValueError("validated Artifact chunk flags are invalid")
        artifact = payload["artifact"]
        now = utc_now()
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db, execution.organization_id)
            current_execution = await db.get(
                A2ATaskExecutionRow, execution.task_id
            )
            task_row = await db.get(
                ContextTaskRefRow,
                {
                    "context_id": execution.context_id,
                    "task_id": execution.task_id,
                },
            )
            if (
                current_execution is None
                or task_row is None
                or current_execution.lease_owner != self._owner
                or task_row.state != TaskState.WORKING.value
            ):
                raise RuntimeError(
                    "validated Artifact chunk lost its owned working Task"
                )
            append_task_event(
                db,
                task_id=execution.task_id,
                context_id=execution.context_id,
                organization_id=execution.organization_id,
                agent_id=execution.agent_id,
                state=TaskState.WORKING.value,
                event_type="artifact",
                artifact_append=append,
                artifact_last_chunk=last_chunk,
                artifact=artifact,
            )
            current_execution.updated_at = now
            await db.commit()

    async def _finish(self, task_id: str, response: JSONResponse) -> None:
        try:
            body = json.loads(bytes(response.body).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        result = body.get("result") if isinstance(body, dict) else None
        transport_failed = (
            response.status_code >= 400
            or not isinstance(body, dict)
            or isinstance(body.get("error"), dict)
            or not isinstance(result, dict)
        )
        error_code = ""
        if transport_failed and isinstance(body.get("error"), dict):
            data = body["error"].get("data")
            if isinstance(data, dict):
                error_code = str(data.get("a2a_error_code") or "")
        result_is_settled = False
        target = TaskState.FAILED
        if not transport_failed and isinstance(result, dict):
            try:
                target = settled_state_from_result(result)
                result_is_settled = True
            except ValueError:
                error_code = "INVALID_AGENT_RESULT"
        prepared_artifacts: list[dict[str, Any]] = []
        if target == TaskState.COMPLETED and isinstance(result, dict):
            # Validate the whole Artifact before the terminal transaction.
            # Invalid Agent output fails closed and cannot create a completed
            # Task whose durable result is missing or ambiguous.
            try:
                prepared_artifacts = result_artifacts(task_id, result)
            except ValueError:
                target = TaskState.FAILED
                result_is_settled = False
                error_code = "INVALID_AGENT_RESULT"
        now = utc_now()
        encrypted_result = (
            encrypt_phi(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            if result_is_settled and isinstance(result, dict)
            else None
        )

        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            if execution is None:
                return
            await bind_tenant_to_transaction(db, execution.organization_id)
            task_row = await db.get(
                ContextTaskRefRow,
                {"context_id": execution.context_id, "task_id": task_id},
            )
            if task_row is None:
                return
            if execution.lease_owner != self._owner:
                # A newer worker reclaimed an expired lease. The stale worker
                # must not overwrite that worker's eventual terminal result.
                return
            if task_row.state == TaskState.CANCELED.value:
                await db.execute(
                    update(A2ATaskExecutionRow)
                    .where(
                        A2ATaskExecutionRow.task_id == task_id,
                        A2ATaskExecutionRow.lease_owner == self._owner,
                    )
                    .values(
                        lease_owner=None,
                        lease_expires_at=None,
                        updated_at=now,
                    )
                )
                await db.commit()
                return
            if TaskState(task_row.state) in TERMINAL_STATES:
                return
            state_values: dict[str, Any] = {"state": target.value}
            state_values["completed_at"] = now if target in TERMINAL_STATES else None
            settled = await db.execute(
                update(ContextTaskRefRow)
                .where(
                    ContextTaskRefRow.context_id == execution.context_id,
                    ContextTaskRefRow.task_id == task_id,
                    ContextTaskRefRow.state.in_([
                        TaskState.SUBMITTED.value,
                        TaskState.WORKING.value,
                    ]),
                )
                .values(**state_values)
            )
            if not settled.rowcount:
                await db.rollback()
                return
            stored = await db.execute(
                update(A2ATaskExecutionRow)
                .where(
                    A2ATaskExecutionRow.task_id == task_id,
                    A2ATaskExecutionRow.lease_owner == self._owner,
                )
                .values(
                    result_json=encrypted_result,
                    error_code=(error_code or "INTERNAL_ERROR")
                    if not result_is_settled
                    else None,
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
            )
            if not stored.rowcount:
                await db.rollback()
                return
            if target == TaskState.COMPLETED:
                stream_artifact = await load_completed_stream_artifact(
                    db,
                    context_id=execution.context_id,
                    task_id=task_id,
                    artifact_id=(
                        f"{task_id}{VALIDATED_STREAM_ARTIFACT_SUFFIX}"
                    ),
                )
                artifacts_to_persist = list(prepared_artifacts)
                if stream_artifact is not None:
                    if any(
                        item["artifactId"] == stream_artifact["artifactId"]
                        for item in artifacts_to_persist
                    ):
                        raise ValueError(
                            "validated stream Artifact conflicts with Agent result"
                        )
                    artifacts_to_persist.append(stream_artifact)
                await persist_artifacts(
                    db,
                    context_id=execution.context_id,
                    task_id=task_id,
                    artifacts=artifacts_to_persist,
                    created_at=now,
                )
                for artifact in prepared_artifacts:
                    append_task_event(
                        db,
                        task_id=task_id,
                        context_id=execution.context_id,
                        organization_id=execution.organization_id,
                        agent_id=execution.agent_id,
                        state=TaskState.WORKING.value,
                        event_type="artifact",
                        artifact_id=str(artifact["artifactId"]),
                        artifact_append=False,
                        artifact_last_chunk=True,
                        artifact=artifact,
                    )
            append_task_event(
                db,
                task_id=task_id,
                context_id=execution.context_id,
                organization_id=execution.organization_id,
                agent_id=execution.agent_id,
                state=target.value,
                event_type=target.value,
            )
            await db.commit()

    async def _fail_internal(self, task_id: str) -> None:
        now = utc_now()
        async with database.AsyncSessionLocal() as db:
            execution = await db.get(A2ATaskExecutionRow, task_id)
            if execution is None:
                return
            await bind_tenant_to_transaction(db, execution.organization_id)
            task_row = await db.get(
                ContextTaskRefRow,
                {"context_id": execution.context_id, "task_id": task_id},
            )
            if task_row is None or TaskState(task_row.state) in TERMINAL_STATES:
                return
            if execution.lease_owner != self._owner:
                return
            terminal = await db.execute(
                update(ContextTaskRefRow)
                .where(
                    ContextTaskRefRow.context_id == execution.context_id,
                    ContextTaskRefRow.task_id == task_id,
                    ContextTaskRefRow.state.in_([
                        TaskState.SUBMITTED.value,
                        TaskState.WORKING.value,
                    ]),
                )
                .values(state=TaskState.FAILED.value, completed_at=now)
            )
            if not terminal.rowcount:
                await db.rollback()
                return
            stored = await db.execute(
                update(A2ATaskExecutionRow)
                .where(
                    A2ATaskExecutionRow.task_id == task_id,
                    A2ATaskExecutionRow.lease_owner == self._owner,
                )
                .values(
                    error_code="INTERNAL_ERROR",
                    lease_owner=None,
                    lease_expires_at=None,
                    updated_at=now,
                )
            )
            if not stored.rowcount:
                await db.rollback()
                return
            append_task_event(
                db,
                task_id=task_id,
                context_id=execution.context_id,
                organization_id=execution.organization_id,
                agent_id=execution.agent_id,
                state=TaskState.FAILED.value,
                event_type="failed",
            )
            await db.commit()


__all__ = [
    "A2ATaskRuntime",
    "append_task_event",
    "load_task_result",
    "utc_now",
]
