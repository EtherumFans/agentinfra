"""A2A v1.0 JSON-RPC and HTTP+JSON bindings.

Both bindings adapt into the existing protocol-neutral inbound handler and the
same tenant-scoped task rows.  The v0.3 routes are mounted separately and are
not reinterpreted by this router.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as database
from app.database import get_db
from app.icoder.agent_runtime.context.context_isolation import ContextIsolationError
from app.icoder.agent_runtime.context.context_lifecycle import ContextLifecycle
from app.icoder.agent_runtime.context.context_repository import ContextRepository
from app.icoder.agent_runtime.context.context_status import ContextStatus
from app.icoder.agent_runtime.orchestrator.phi_redactor import (
    PHIRedactionError,
    redact_payload,
)
from app.middleware.auth import get_current_organization, get_current_user_or_oauth_client
from app.models.organization import Organization
from app.services.agent_runtime_pack import (
    load_tenant_agent,
    pack_from_tenant_agent,
)
from app.services.database_tenancy import bind_tenant_to_transaction
from app.services.phi_encryption import encrypt_phi
from app.services.result_attestation import (
    ResultAttestationError,
    verify_upstream_result_attestations,
)

from ...context.db_models import (
    A2ATaskEventRow,
    A2ATaskExecutionRow,
    ContextRow,
    ContextTaskRefRow,
)
from ..agent_card import AgentCard, agent_card_from_pack, project_v1_agent_card
from ..envelope import JsonRpcRequest
from ..input_safety import detect_prompt_injection
from ..routes_discovery import AgentProvider
from ..routes_inbound import _dispatch
from ..task_state import (
    INTERRUPTED_STATES,
    SETTLED_STATES,
    TERMINAL_STATES,
    InvalidTaskTransition,
    TaskState,
    next_state,
    settled_state_from_result,
)
from .protocol import (
    A2A_V1_HEADER,
    A2A_V1_VERSION,
    A2AV1ProtocolError,
    CanonicalMessage,
    MAX_V1_BODY_BYTES,
    TASK_STATE_FROM_V1,
    decode_task_cursor,
    encode_task_cursor,
    parse_iso_timestamp,
    parse_v1_jsonrpc,
    parse_v1_message,
    project_v0_3_message,
    project_v0_3_task,
    task_row_to_v1,
    validate_v1_version,
)
from .task_runtime import (
    A2ATaskRuntime,
    append_task_event,
    load_task_result,
    utc_now,
)
from .artifact_store import (
    decode_event_artifact,
    load_task_artifact,
    load_task_artifacts,
    persist_artifacts,
    result_artifacts,
)


def build_v1_router(handler: Any, agent_provider: AgentProvider) -> APIRouter:
    router = APIRouter(prefix="/api/v2/agentic/agents/{agent_id}", tags=["a2a-v1"])
    task_runtime = A2ATaskRuntime(handler)
    router.a2a_task_runtime = task_runtime

    @router.post("/a2a", operation_id="a2a_v1_jsonrpc")
    async def jsonrpc_binding(
        agent_id: str,
        request: Request,
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        request_id: str | int | None = None
        try:
            validate_v1_version(dict(request.headers))
            request_id, method, params = parse_v1_jsonrpc(await request.body())
            _validate_method_params(method, params)
            if method in {"SendMessage", "SendStreamingMessage"}:
                canonical, configuration = parse_v1_message(params)
                canonical = await _prepare_message(
                    db, current_org.id, agent_id, canonical
                )
                if method == "SendStreamingMessage" and not canonical.task_id:
                    task, submitted_sequence = await _enqueue_async_task(
                        task_runtime,
                        agent_provider,
                        agent_id=agent_id,
                        request=request,
                        organization_id=current_org.id,
                        db=db,
                        request_id=request_id,
                        canonical=canonical,
                        configuration=configuration,
                        schedule=False,
                    )
                    stream = await _subscribe_task(
                        request,
                        organization_id=current_org.id,
                        agent_id=agent_id,
                        task_id=task["id"],
                        after_sequence=0,
                        jsonrpc=True,
                        request_id=request_id,
                        initial_replay_sequence=submitted_sequence,
                    )
                    task_runtime.schedule(request.app, task["id"])
                    return stream
                if configuration.get("returnImmediately") is True:
                    task, _submitted_sequence = await _enqueue_async_task(
                        task_runtime,
                        agent_provider,
                        agent_id=agent_id,
                        request=request,
                        organization_id=current_org.id,
                        db=db,
                        request_id=request_id,
                        canonical=canonical,
                        configuration=configuration,
                    )
                    body = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "result": {"task": task},
                    }
                    return _jsonrpc(body)
                response = await _execute_send(
                    handler,
                    agent_id,
                    request,
                    current_org.id,
                    db,
                    request_id,
                    canonical.to_v0_3_params(configuration),
                    task_id=canonical.task_id,
                )
                projected = _project_legacy_response(
                    response, task_id=canonical.task_id
                )
                if isinstance(projected, A2AV1ProtocolError):
                    return _jsonrpc_error(projected, request_id)
                body = {"jsonrpc": "2.0", "id": request_id, "result": projected}
                if method == "SendStreamingMessage":
                    return _sse([body], jsonrpc=True)
                return _jsonrpc(body)
            if method == "GetTask":
                task_id = _required_id(params)
                row = await _load_task(db, current_org.id, agent_id, task_id)
                if row is None:
                    raise _task_not_found(task_id)
                return _jsonrpc({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": await _task_to_v1(db, row),
                })
            if method == "SubscribeToTask":
                task_id = _required_id(params)
                return await _subscribe_task(
                    request,
                    organization_id=current_org.id,
                    agent_id=agent_id,
                    task_id=task_id,
                    after_sequence=_optional_sequence(params.get("afterSequence")),
                    jsonrpc=True,
                    request_id=request_id,
                )
            if method == "ListTasks":
                result = await _list_tasks(
                    db,
                    organization_id=current_org.id,
                    agent_id=agent_id,
                    context_id=_optional_string(params, "contextId"),
                    status=_optional_string(params, "status"),
                    page_size=_page_size(params.get("pageSize")),
                    page_token=_optional_string(params, "pageToken"),
                    status_timestamp_after=_optional_string(params, "statusTimestampAfter"),
                    include_artifacts=_optional_bool(params, "includeArtifacts"),
                )
                return _jsonrpc({"jsonrpc": "2.0", "id": request_id, "result": result})
            if method == "CancelTask":
                task_id = _required_id(params)
                row = await _cancel_task(
                    db,
                    current_org.id,
                    agent_id,
                    task_id,
                    task_runtime=task_runtime,
                )
                return _jsonrpc({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": await _task_to_v1(db, row),
                })
            raise A2AV1ProtocolError("METHOD_NOT_FOUND", f"unsupported method {method!r}", "method")
        except A2AV1ProtocolError as exc:
            return _jsonrpc_error(exc, request_id)

    @router.post("/message:send", operation_id="a2a_v1_http_send_message")
    async def http_send_message(
        agent_id: str,
        request: Request,
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            validate_v1_version(dict(request.headers))
            params = await _read_http_body(request)
            canonical, configuration = parse_v1_message(params)
            canonical = await _prepare_message(
                db, current_org.id, agent_id, canonical
            )
            if configuration.get("returnImmediately") is True:
                task, _submitted_sequence = await _enqueue_async_task(
                    task_runtime,
                    agent_provider,
                    agent_id=agent_id,
                    request=request,
                    organization_id=current_org.id,
                    db=db,
                    request_id=None,
                    canonical=canonical,
                    configuration=configuration,
                )
                return _http_json({"task": task})
            response = await _execute_send(
                handler,
                agent_id,
                request,
                current_org.id,
                db,
                None,
                canonical.to_v0_3_params(configuration),
                task_id=canonical.task_id,
            )
            projected = _project_legacy_response(
                response, task_id=canonical.task_id
            )
            if isinstance(projected, A2AV1ProtocolError):
                raise projected
            return _http_json(projected)
        except A2AV1ProtocolError as exc:
            return _http_error(exc)

    @router.post("/message:stream", operation_id="a2a_v1_http_stream_message")
    async def http_stream_message(
        agent_id: str,
        request: Request,
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            validate_v1_version(dict(request.headers))
            params = await _read_http_body(request)
            canonical, configuration = parse_v1_message(params)
            canonical = await _prepare_message(
                db, current_org.id, agent_id, canonical
            )
            if not canonical.task_id:
                task, submitted_sequence = await _enqueue_async_task(
                    task_runtime,
                    agent_provider,
                    agent_id=agent_id,
                    request=request,
                    organization_id=current_org.id,
                    db=db,
                    request_id=None,
                    canonical=canonical,
                    configuration=configuration,
                    schedule=False,
                )
                stream = await _subscribe_task(
                    request,
                    organization_id=current_org.id,
                    agent_id=agent_id,
                    task_id=task["id"],
                    after_sequence=0,
                    jsonrpc=False,
                    request_id=None,
                    initial_replay_sequence=submitted_sequence,
                )
                task_runtime.schedule(request.app, task["id"])
                return stream
            response = await _execute_send(
                handler,
                agent_id,
                request,
                current_org.id,
                db,
                None,
                canonical.to_v0_3_params(configuration),
                task_id=canonical.task_id,
            )
            projected = _project_legacy_response(
                response, task_id=canonical.task_id
            )
            if isinstance(projected, A2AV1ProtocolError):
                raise projected
            return _sse([projected], jsonrpc=False)
        except A2AV1ProtocolError as exc:
            return _http_error(exc)

    @router.get("/tasks", operation_id="a2a_v1_http_list_tasks")
    async def http_list_tasks(
        agent_id: str,
        request: Request,
        context_id: str = Query("", alias="contextId"),
        status: str = Query(""),
        page_size: int = Query(50, ge=1, le=100, alias="pageSize"),
        page_token: str = Query("", alias="pageToken"),
        status_timestamp_after: str = Query("", alias="statusTimestampAfter"),
        include_artifacts: bool = Query(False, alias="includeArtifacts"),
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            validate_v1_version(dict(request.headers))
            result = await _list_tasks(
                db,
                organization_id=current_org.id,
                agent_id=agent_id,
                context_id=context_id,
                status=status,
                page_size=page_size,
                page_token=page_token,
                status_timestamp_after=status_timestamp_after,
                include_artifacts=include_artifacts,
            )
            return _http_json(result)
        except A2AV1ProtocolError as exc:
            return _http_error(exc)

    @router.get(
        "/tasks/{task_id}:subscribe",
        operation_id="a2a_v1_http_subscribe_task",
    )
    async def http_subscribe_task(
        agent_id: str,
        task_id: str,
        request: Request,
        after_sequence: int = Query(0, ge=0, alias="afterSequence"),
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
    ):
        try:
            validate_v1_version(dict(request.headers))
            header_sequence = _last_event_sequence(request)
            return await _subscribe_task(
                request,
                organization_id=current_org.id,
                agent_id=agent_id,
                task_id=task_id,
                after_sequence=max(after_sequence, header_sequence),
                jsonrpc=False,
                request_id=None,
            )
        except A2AV1ProtocolError as exc:
            return _http_error(exc)

    @router.get("/tasks/{task_id}", operation_id="a2a_v1_http_get_task")
    async def http_get_task(
        agent_id: str,
        task_id: str,
        request: Request,
        history_length: int | None = Query(None, ge=0, le=100, alias="historyLength"),
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        del history_length
        try:
            validate_v1_version(dict(request.headers))
            row = await _load_task(db, current_org.id, agent_id, task_id)
            if row is None:
                raise _task_not_found(task_id)
            return _http_json(await _task_to_v1(db, row))
        except A2AV1ProtocolError as exc:
            return _http_error(exc)

    @router.post("/tasks/{task_id}:cancel", operation_id="a2a_v1_http_cancel_task")
    async def http_cancel_task(
        agent_id: str,
        task_id: str,
        request: Request,
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            validate_v1_version(dict(request.headers))
            row = await _cancel_task(
                db,
                current_org.id,
                agent_id,
                task_id,
                task_runtime=task_runtime,
            )
            return _http_json(await _task_to_v1(db, row))
        except A2AV1ProtocolError as exc:
            return _http_error(exc)

    @router.get("/agent-card", operation_id="a2a_v1_agent_card")
    async def get_agent_card(
        agent_id: str,
        request: Request,
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            validate_v1_version(dict(request.headers))
            card = await _resolve_tenant_card(
                agent_provider, agent_id, current_org.id, db,
            )
            if card is None:
                return _http_error(A2AV1ProtocolError("METHOD_NOT_FOUND", "agent is not available"))
            return _agent_card_response(
                project_v1_agent_card(
                    card, base_url=str(request.base_url), agent_id=agent_id,
                ),
                request,
                private=True,
            )
        except A2AV1ProtocolError as exc:
            return _http_error(exc)

    @router.get(
        "/.well-known/agent-card.json",
        operation_id="a2a_v1_agent_card_well_known",
        summary="Authenticated tenant Agent Card at the standard relative path",
    )
    async def get_well_known_agent_card(
        agent_id: str,
        request: Request,
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        card = await _resolve_tenant_card(
            agent_provider, agent_id, current_org.id, db,
        )
        if card is None:
            return _http_error(
                A2AV1ProtocolError("METHOD_NOT_FOUND", "agent is not available")
            )
        return _agent_card_response(
            project_v1_agent_card(
                card, base_url=str(request.base_url), agent_id=agent_id,
            ),
            request,
            private=True,
        )

    return router


async def _read_http_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_V1_BODY_BYTES:
        raise A2AV1ProtocolError("INVALID_REQUEST", "request body exceeds 1 MiB", "request")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A2AV1ProtocolError("JSON_PARSE_ERROR", str(exc), "request") from exc
    if not isinstance(body, dict):
        raise A2AV1ProtocolError("INVALID_REQUEST", "request body must be an object", "request")
    return body


async def _enqueue_async_task(
    runtime: A2ATaskRuntime,
    agent_provider: AgentProvider,
    *,
    agent_id: str,
    request: Request,
    organization_id: str,
    db: AsyncSession,
    request_id: str | int | None,
    canonical: CanonicalMessage,
    configuration: dict[str, Any],
    schedule: bool = True,
) -> tuple[dict[str, Any], int]:
    """Persist a route-redacted Task before scheduling any Agent execution."""

    if canonical.task_id:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "returnImmediately creates a new Task and cannot target an existing taskId",
            "message.taskId",
        )

    card = agent_provider(agent_id)
    db_agent = await load_tenant_agent(agent_id, organization_id, db)
    if card is None and not (db_agent is not None and db_agent.a2a_enabled):
        raise A2AV1ProtocolError("METHOD_NOT_FOUND", "agent is not available")

    legacy_configuration = dict(configuration)
    legacy_configuration["returnImmediately"] = False
    legacy_params = canonical.to_v0_3_params(legacy_configuration)
    message = dict(legacy_params["message"])
    raw_upstream_results: list[dict[str, Any]] = []
    for part in message["parts"]:
        if not isinstance(part, dict) or part.get("kind") != "data":
            continue
        data = part.get("data")
        value = data.get("value") if isinstance(data, dict) else None
        if not isinstance(value, dict):
            continue
        candidates = value.get("upstream_results")
        if isinstance(candidates, list):
            raw_upstream_results.extend(candidates)
    try:
        verify_upstream_result_attestations(
            raw_upstream_results,
            organization_id=organization_id,
        )
    except ResultAttestationError as exc:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "an upstream Agent result could not be authenticated",
            "message.parts",
        ) from exc

    try:
        safe_payload = redact_payload({
            "parts": message["parts"],
            "metadata": message.get("metadata") or {},
        }).value
    except PHIRedactionError as exc:
        raise A2AV1ProtocolError(
            "INTERNAL", "request could not be safely de-identified"
        ) from exc
    injection_rules = detect_prompt_injection(safe_payload)
    if injection_rules:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "request was blocked by input safety policy",
            "message.parts",
            metadata={"ruleIds": ",".join(injection_rules)},
        )
    message["parts"] = safe_payload["parts"]
    message["metadata"] = safe_payload["metadata"]

    repo = ContextRepository(db)
    lifecycle = ContextLifecycle(repo)
    created_context = False
    if canonical.context_id:
        try:
            context_row = await repo.get_for_org(
                canonical.context_id, organization_id
            )
        except ContextIsolationError as exc:
            raise A2AV1ProtocolError(
                "INVALID_PARAMS",
                "contextId must be a canonical UUID v4",
                "message.contextId",
            ) from exc
        if context_row is None or context_row.agent_id != agent_id:
            raise A2AV1ProtocolError(
                "INVALID_PARAMS",
                "contextId does not exist or is not accessible",
                "message.contextId",
            )
        context = await lifecycle.expire_if_overdue(canonical.context_id)
        if context is None or context.status != ContextStatus.ACTIVE:
            raise A2AV1ProtocolError(
                "INVALID_PARAMS", "context is no longer active", "message.contextId"
            )
        context_id = canonical.context_id
    else:
        context = await lifecycle.create(
            agent_id=agent_id,
            organization_id=organization_id,
        )
        context_id = context.id
        created_context = True

    if await repo.get_messages(context_id, message_id=canonical.message_id):
        if created_context:
            await repo.delete_context(context_id)
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "message.messageId already exists in this context",
            "message.messageId",
        )
    existing_execution = (
        await db.execute(
            select(A2ATaskExecutionRow).where(
                A2ATaskExecutionRow.organization_id == organization_id,
                A2ATaskExecutionRow.agent_id == agent_id,
                A2ATaskExecutionRow.message_id == canonical.message_id,
            )
        )
    ).scalar_one_or_none()
    if existing_execution is not None:
        if created_context:
            await repo.delete_context(context_id)
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "message.messageId already identifies an asynchronous Task",
            "message.messageId",
        )

    task_id = f"task-{uuid.uuid4().hex}"
    now = utc_now()
    message["contextId"] = context_id
    message_metadata = dict(message.get("metadata") or {})
    message_metadata["_a2a_v1_task_id"] = task_id
    message["metadata"] = message_metadata
    legacy_params["message"] = message
    try:
        encrypted_request = encrypt_phi(json.dumps(
            {"request_id": request_id, "legacy_params": legacy_params},
            ensure_ascii=False,
            separators=(",", ":"),
        ))
    except Exception as exc:
        if created_context:
            try:
                await repo.delete_context(context_id)
            except Exception:
                await db.rollback()
        raise A2AV1ProtocolError(
            "INTERNAL", "asynchronous Task payload could not be encrypted"
        ) from exc
    if not encrypted_request:
        if created_context:
            await repo.delete_context(context_id)
        raise A2AV1ProtocolError(
            "INTERNAL", "asynchronous Task payload encryption returned no data"
        )

    task_row = ContextTaskRefRow(
        context_id=context_id,
        task_id=task_id,
        state=TaskState.SUBMITTED.value,
        started_at=now,
        completed_at=None,
    )
    execution = A2ATaskExecutionRow(
        task_id=task_id,
        context_id=context_id,
        organization_id=organization_id,
        agent_id=agent_id,
        message_id=canonical.message_id,
        request_json=encrypted_request,
        result_json=None,
        error_code=None,
        attempt_count=0,
        lease_owner=None,
        lease_expires_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(task_row)
    db.add(execution)
    submitted_event = append_task_event(
        db,
        task_id=task_id,
        context_id=context_id,
        organization_id=organization_id,
        agent_id=agent_id,
        state=TaskState.SUBMITTED.value,
        event_type="submitted",
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if created_context:
            try:
                await repo.delete_context(context_id)
            except Exception:
                await db.rollback()
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "message.messageId conflicts with an existing asynchronous Task",
            "message.messageId",
        ) from exc
    await db.refresh(task_row)
    await db.refresh(submitted_event)
    if schedule:
        runtime.schedule(request.app, task_id)
    return task_row_to_v1(task_row), int(submitted_event.sequence_id)


async def _task_to_v1(
    db: AsyncSession,
    row: ContextTaskRefRow,
    *,
    include_artifacts: bool = True,
    state_override: str = "",
    status_timestamp: datetime | None = None,
) -> dict[str, Any]:
    try:
        result = await load_task_result(db, row.task_id)
    except Exception as exc:
        raise A2AV1ProtocolError(
            "INTERNAL", "Task result is temporarily unavailable"
        ) from exc
    execution = await db.get(A2ATaskExecutionRow, row.task_id)
    try:
        durable_artifacts = await load_task_artifacts(
            db, context_id=row.context_id, task_id=row.task_id
        )
    except Exception as exc:
        raise A2AV1ProtocolError(
            "INTERNAL", "Task Artifact is temporarily unavailable"
        ) from exc
    result_message = result
    if isinstance(result, dict) and result.get("kind") == "task":
        status = result.get("status")
        result_message = status.get("message") if isinstance(status, dict) else None
    return task_row_to_v1(
        row,
        result_message=result_message if isinstance(result_message, dict) else None,
        include_artifacts=include_artifacts,
        state_override=state_override,
        status_timestamp=status_timestamp,
        error_code=str(execution.error_code or "") if execution else "",
        # No rows means a pre-050 Task and retains the documented compatibility
        # projection. New writes always create at least one durable Artifact.
        artifacts=durable_artifacts or None,
    )


async def _execute_send(
    handler: Any,
    agent_id: str,
    request: Request,
    organization_id: str,
    db: AsyncSession,
    request_id: str | int | None,
    legacy_params: dict[str, Any],
    *,
    task_id: str = "",
) -> JSONResponse:
    if task_id:
        # Server-owned bridge metadata: the v0.3 wire Message has no v1
        # taskId field, but ConnectorExecutionAudit must retain the durable
        # Task correlation. Client metadata with the same key is overwritten.
        legacy_params = dict(legacy_params)
        legacy_message = dict(legacy_params.get("message") or {})
        legacy_metadata = dict(legacy_message.get("metadata") or {})
        legacy_metadata["_a2a_v1_task_id"] = task_id
        legacy_message["metadata"] = legacy_metadata
        legacy_params["message"] = legacy_message
    legacy_envelope = JsonRpcRequest(
        jsonrpc="2.0",
        id=request_id,
        method="message/send",
        params=legacy_params,
    )
    response = await _dispatch(
        handler,
        agent_id,
        request,
        organization_id=organization_id,
        db=db,
        allowed_methods=("message/send",),
        parsed_request=legacy_envelope,
        parsed_params=legacy_params,
        server_task_id=task_id,
    )
    if task_id:
        await _finalize_task_after_send(
            db,
            organization_id=organization_id,
            agent_id=agent_id,
            task_id=task_id,
            response=response,
        )
    return response


def _project_legacy_response(
    response: JSONResponse, *, task_id: str = ""
) -> dict[str, Any] | A2AV1ProtocolError:
    try:
        body = json.loads(bytes(response.body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return A2AV1ProtocolError("INTERNAL", "legacy adapter returned invalid JSON")
    if not isinstance(body, dict):
        return A2AV1ProtocolError("INTERNAL", "legacy adapter returned a non-object")
    if isinstance(body.get("error"), dict):
        return _translate_legacy_error(body["error"])
    result = body.get("result")
    if not isinstance(result, dict):
        return A2AV1ProtocolError("INTERNAL", "legacy adapter omitted result")
    if result.get("kind") == "message":
        message = project_v0_3_message(result)
        if task_id:
            message["taskId"] = task_id
        return {"message": message}
    if result.get("kind") == "task":
        return {"task": project_v0_3_task(result)}
    return A2AV1ProtocolError("INTERNAL", "legacy adapter returned an unsupported payload")


def _translate_legacy_error(error: dict[str, Any]) -> A2AV1ProtocolError:
    data = error.get("data") if isinstance(error.get("data"), dict) else {}
    code = str(data.get("a2a_error_code") or "")
    detail = str(data.get("details") or error.get("message") or "")
    mapping = {
        "TASK_NOT_FOUND": "TASK_NOT_FOUND",
        "TASK_NOT_CANCELABLE": "TASK_NOT_CANCELABLE",
        "UNSUPPORTED_OPERATION": "UNSUPPORTED_OPERATION",
        "INVALID_PARAMS": "INVALID_PARAMS",
        "INVALID_REQUEST": "INVALID_REQUEST",
        "CONTEXT_INVALID": "INVALID_PARAMS",
        "CONTEXT_NOT_FOUND": "INVALID_PARAMS",
        "AGENT_NOT_FOUND": "METHOD_NOT_FOUND",
        "INPUT_SAFETY_BLOCKED": "INVALID_PARAMS",
    }
    return A2AV1ProtocolError(mapping.get(code, "INTERNAL"), detail)


async def _load_task(
    db: AsyncSession,
    organization_id: str,
    agent_id: str,
    task_id: str,
) -> ContextTaskRefRow | None:
    stmt = (
        select(ContextTaskRefRow)
        .join(ContextRow, ContextRow.id == ContextTaskRefRow.context_id)
        .where(
            ContextTaskRefRow.task_id == task_id,
            ContextRow.organization_id == organization_id,
            ContextRow.agent_id == agent_id,
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _prepare_message(
    db: AsyncSession,
    organization_id: str,
    agent_id: str,
    message: CanonicalMessage,
) -> CanonicalMessage:
    """Resolve v1 task linkage without weakening tenant/agent isolation."""

    for reference_id in message.reference_task_ids:
        if await _load_task(db, organization_id, agent_id, reference_id) is None:
            raise _task_not_found(reference_id)
    if not message.task_id:
        return message
    row = await _load_task(db, organization_id, agent_id, message.task_id)
    if row is None:
        raise _task_not_found(message.task_id)
    current = TaskState(row.state)
    if current in TERMINAL_STATES:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "taskId must identify a non-terminal task",
            "message.taskId",
        )
    if message.context_id and message.context_id != row.context_id:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "message.contextId does not match message.taskId",
            "message.contextId",
        )
    if current in INTERRUPTED_STATES:
        next_state(current, TaskState.WORKING)
        resumed = await db.execute(
            update(ContextTaskRefRow)
            .where(
                ContextTaskRefRow.context_id == row.context_id,
                ContextTaskRefRow.task_id == row.task_id,
                ContextTaskRefRow.state == current.value,
            )
            .values(state=TaskState.WORKING.value, completed_at=None)
        )
        if not resumed.rowcount:
            await db.rollback()
            raise A2AV1ProtocolError(
                "INVALID_PARAMS",
                "taskId is already being resumed",
                "message.taskId",
            )
        append_task_event(
            db,
            task_id=row.task_id,
            context_id=row.context_id,
            organization_id=organization_id,
            agent_id=agent_id,
            state=TaskState.WORKING.value,
            event_type="working",
        )
        await db.commit()
    return replace(message, context_id=row.context_id)


async def _finalize_task_after_send(
    db: AsyncSession,
    *,
    organization_id: str,
    agent_id: str,
    task_id: str,
    response: JSONResponse,
) -> None:
    """Advance a v1-linked Task to exactly one terminal state.

    The transport previously validated ``taskId`` but left the row in
    ``working`` regardless of the execution outcome. Connector and Provider
    failures must be observable through GetTask/ListTasks and must never be
    represented as completed work.
    """

    try:
        body = json.loads(bytes(response.body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise A2AV1ProtocolError(
            "INTERNAL", "legacy adapter returned invalid JSON while finalizing task"
        ) from exc
    result = body.get("result") if isinstance(body, dict) else None
    result_is_settled = False
    target = TaskState.FAILED
    if (
        response.status_code < 400
        and isinstance(body, dict)
        and not isinstance(body.get("error"), dict)
        and isinstance(result, dict)
    ):
        try:
            target = settled_state_from_result(result)
            result_is_settled = True
        except ValueError:
            target = TaskState.FAILED
    prepared_artifacts: list[dict[str, Any]] = []
    if target == TaskState.COMPLETED:
        try:
            prepared_artifacts = result_artifacts(task_id, result)
        except ValueError:
            target = TaskState.FAILED
            result_is_settled = False
    row = await _load_task(db, organization_id, agent_id, task_id)
    if row is None:
        raise _task_not_found(task_id)

    current = TaskState(row.state)
    if current == TaskState.SUBMITTED:
        next_state(current, TaskState.WORKING)
        started = await db.execute(
            update(ContextTaskRefRow)
            .where(
                ContextTaskRefRow.context_id == row.context_id,
                ContextTaskRefRow.task_id == task_id,
                ContextTaskRefRow.state == TaskState.SUBMITTED.value,
            )
            .values(state=TaskState.WORKING.value)
        )
        if not started.rowcount:
            await db.rollback()
            raise A2AV1ProtocolError(
                "INTERNAL", f"task {task_id!r} changed state concurrently"
            )
        current = TaskState.WORKING

    if current in TERMINAL_STATES:
        if current == target:
            return
        await db.rollback()
        raise A2AV1ProtocolError(
            "INTERNAL", f"task {task_id!r} reached a conflicting terminal state"
        )

    next_state(current, target)
    state_values: dict[str, Any] = {"state": target.value}
    state_values["completed_at"] = (
        func.current_timestamp() if target in TERMINAL_STATES else None
    )
    completed = await db.execute(
        update(ContextTaskRefRow)
        .where(
            ContextTaskRefRow.context_id == row.context_id,
            ContextTaskRefRow.task_id == task_id,
            ContextTaskRefRow.state == current.value,
        )
        .values(**state_values)
    )
    if not completed.rowcount:
        await db.rollback()
        raise A2AV1ProtocolError(
            "INTERNAL", f"task {task_id!r} changed state concurrently"
        )
    if target == TaskState.COMPLETED:
        await persist_artifacts(
            db,
            context_id=row.context_id,
            task_id=task_id,
            artifacts=prepared_artifacts,
        )
        for artifact in prepared_artifacts:
            append_task_event(
                db,
                task_id=task_id,
                context_id=row.context_id,
                organization_id=organization_id,
                agent_id=agent_id,
                state=TaskState.WORKING.value,
                event_type="artifact",
                artifact_id=str(artifact["artifactId"]),
                artifact_append=False,
                artifact_last_chunk=True,
                artifact=artifact,
            )
    execution = await db.get(A2ATaskExecutionRow, task_id)
    if execution is not None:
        encrypted_result = None
        if result_is_settled and isinstance(result, dict):
            try:
                encrypted_result = encrypt_phi(json.dumps(
                    result, ensure_ascii=False, separators=(",", ":")
                ))
            except Exception as exc:
                await db.rollback()
                raise A2AV1ProtocolError(
                    "INTERNAL", "Task result could not be encrypted"
                ) from exc
        execution.result_json = encrypted_result
        execution.error_code = (
            None if result_is_settled else "INVALID_AGENT_RESULT"
        )
        execution.lease_owner = None
        execution.lease_expires_at = None
        execution.updated_at = utc_now()
    append_task_event(
        db,
        task_id=task_id,
        context_id=row.context_id,
        organization_id=organization_id,
        agent_id=agent_id,
        state=target.value,
        event_type=target.value,
    )
    await db.commit()


async def _cancel_task(
    db: AsyncSession,
    organization_id: str,
    agent_id: str,
    task_id: str,
    *,
    task_runtime: A2ATaskRuntime,
) -> ContextTaskRefRow:
    row = await _load_task(db, organization_id, agent_id, task_id)
    if row is None:
        raise _task_not_found(task_id)
    execution = await db.get(A2ATaskExecutionRow, task_id)
    if execution is not None and row.state == TaskState.WORKING.value:
        # Only the runtime that owns the in-process dispatch can prove the
        # coroutine has stopped.  Cross-process work and Provider calls that
        # are not represented by a local asyncio Task remain not cancelable.
        canceled_here = await task_runtime.cancel_running(task_id)
        if not canceled_here:
            raise A2AV1ProtocolError(
                "TASK_NOT_CANCELABLE",
                f"task {task_id!r} is already executing outside this runtime",
                metadata={"taskId": task_id},
            )
        # cancel_running releases the lease in a separate session.  End this
        # read transaction and reload authoritative state before the terminal
        # compare-and-set below.
        await db.rollback()
        row = await _load_task(db, organization_id, agent_id, task_id)
        if row is None:
            raise _task_not_found(task_id)
        execution = await db.get(A2ATaskExecutionRow, task_id)
    try:
        target = next_state(TaskState(row.state), TaskState.CANCELED)
    except (InvalidTaskTransition, ValueError) as exc:
        raise A2AV1ProtocolError(
            "TASK_NOT_CANCELABLE",
            f"task {task_id!r} is not cancelable",
            metadata={"taskId": task_id},
        ) from exc
    now = utc_now()
    result = await db.execute(
        update(ContextTaskRefRow)
        .where(
            ContextTaskRefRow.context_id == row.context_id,
            ContextTaskRefRow.task_id == task_id,
            ContextTaskRefRow.state == row.state,
        )
        .values(state=target.value, completed_at=now)
    )
    if not result.rowcount:
        await db.rollback()
        raise A2AV1ProtocolError(
            "TASK_NOT_CANCELABLE",
            f"task {task_id!r} changed state concurrently",
            metadata={"taskId": task_id},
        )
    if execution is not None:
        execution.lease_owner = None
        execution.lease_expires_at = None
        execution.updated_at = now
        append_task_event(
            db,
            task_id=task_id,
            context_id=row.context_id,
            organization_id=organization_id,
            agent_id=agent_id,
            state=TaskState.CANCELED.value,
            event_type="canceled",
        )
    await db.commit()
    refreshed = await _load_task(db, organization_id, agent_id, task_id)
    assert refreshed is not None
    return refreshed


async def _list_tasks(
    db: AsyncSession,
    *,
    organization_id: str,
    agent_id: str,
    context_id: str,
    status: str,
    page_size: int,
    page_token: str,
    status_timestamp_after: str,
    include_artifacts: bool,
) -> dict[str, Any]:
    if status and status not in TASK_STATE_FROM_V1:
        raise A2AV1ProtocolError("INVALID_PARAMS", "unknown TaskState", "status")
    after = parse_iso_timestamp(status_timestamp_after, "statusTimestampAfter") if status_timestamp_after else None
    filters = [
        ContextRow.organization_id == organization_id,
        ContextRow.agent_id == agent_id,
    ]
    if context_id:
        filters.append(ContextRow.id == context_id)
    if status:
        filters.append(ContextTaskRefRow.state == TASK_STATE_FROM_V1[status])
    effective_timestamp = func.coalesce(ContextTaskRefRow.completed_at, ContextTaskRefRow.started_at)
    if after is not None:
        filters.append(effective_timestamp >= after)

    cursor: dict[str, Any] | None = None
    if page_token:
        cursor = decode_task_cursor(page_token)
        identity = {
            "o": organization_id,
            "a": agent_id,
            "c": context_id,
            "s": status,
            "after": status_timestamp_after,
            "artifacts": include_artifacts,
        }
        if any(cursor.get(key) != value for key, value in identity.items()):
            raise A2AV1ProtocolError("INVALID_PARAMS", "pageToken does not match this query", "pageToken")

    base = (
        select(ContextTaskRefRow)
        .join(ContextRow, ContextRow.id == ContextTaskRefRow.context_id)
        .where(*filters)
    )
    total_stmt = (
        select(func.count())
        .select_from(ContextTaskRefRow)
        .join(ContextRow, ContextRow.id == ContextTaskRefRow.context_id)
        .where(*filters)
    )
    total_size = int((await db.execute(total_stmt)).scalar_one())
    if cursor:
        cursor_ts = parse_iso_timestamp(str(cursor.get("ts") or ""), "pageToken")
        cursor_id = str(cursor.get("id") or "")
        base = base.where(or_(
            ContextTaskRefRow.started_at < cursor_ts,
            and_(ContextTaskRefRow.started_at == cursor_ts, ContextTaskRefRow.task_id < cursor_id),
        ))
    rows = (await db.execute(
        base.order_by(ContextTaskRefRow.started_at.desc(), ContextTaskRefRow.task_id.desc()).limit(page_size + 1)
    )).scalars().all()
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    next_page_token = ""
    if has_more and page_rows:
        last = page_rows[-1]
        started_at = last.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        next_page_token = encode_task_cursor({
            "v": 1,
            "o": organization_id,
            "a": agent_id,
            "c": context_id,
            "s": status,
            "after": status_timestamp_after,
            "artifacts": include_artifacts,
            "ts": started_at.isoformat(),
            "id": last.task_id,
        })
    projected_tasks = [
        await _task_to_v1(
            db,
            row,
            include_artifacts=include_artifacts,
        )
        for row in page_rows
    ]
    return {
        "tasks": projected_tasks,
        "nextPageToken": next_page_token,
        "pageSize": page_size,
        "totalSize": total_size,
    }


async def _subscribe_task(
    request: Request,
    *,
    organization_id: str,
    agent_id: str,
    task_id: str,
    after_sequence: int,
    jsonrpc: bool,
    request_id: str | int | None,
    initial_replay_sequence: int | None = None,
) -> StreamingResponse:
    async with database.AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, organization_id)
        row = await _load_task(db, organization_id, agent_id, task_id)
        if row is None:
            raise _task_not_found(task_id)
        initial_task = await _task_to_v1(db, row, include_artifacts=True)
        initial_sequence = int((
            await db.execute(
                select(func.max(A2ATaskEventRow.sequence_id)).where(
                    A2ATaskEventRow.organization_id == organization_id,
                    A2ATaskEventRow.agent_id == agent_id,
                    A2ATaskEventRow.task_id == task_id,
                )
            )
        ).scalar_one_or_none() or 0)

    async def generate():
        cursor = after_sequence
        idle_polls = 0
        settled_states = {state.value for state in SETTLED_STATES}
        if after_sequence == 0:
            initial_response = {"task": initial_task}
            initial_payload: dict[str, Any]
            if jsonrpc:
                initial_payload = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": initial_response,
                }
            else:
                initial_payload = initial_response
            snapshot_sequence = (
                initial_replay_sequence
                if initial_replay_sequence is not None
                else initial_sequence
            )
            yield (
                f"id: {snapshot_sequence}\n"
                "event: task\n"
                "data: "
                + json.dumps(
                    initial_payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n\n"
            )
            cursor = snapshot_sequence
            if row.state in settled_states and initial_replay_sequence is None:
                return
        while True:
            if await request.is_disconnected():
                return
            async with database.AsyncSessionLocal() as db:
                await bind_tenant_to_transaction(db, organization_id)
                events = (
                    await db.execute(
                        select(A2ATaskEventRow)
                        .where(
                            A2ATaskEventRow.organization_id == organization_id,
                            A2ATaskEventRow.agent_id == agent_id,
                            A2ATaskEventRow.task_id == task_id,
                            A2ATaskEventRow.sequence_id > cursor,
                        )
                        .order_by(A2ATaskEventRow.sequence_id)
                        .limit(100)
                    )
                ).scalars().all()
                current = await _load_task(db, organization_id, agent_id, task_id)
                if current is None:
                    return
                for event in events:
                    stream_response: dict[str, Any]
                    sse_event: str
                    if event.event_type == "artifact":
                        if not event.artifact_id:
                            # A persisted Artifact event without identity is
                            # not safe to project or resume.
                            return
                        artifact = decode_event_artifact(event)
                        if artifact is None:
                            # Compatibility for events written by revision
                            # 051 before exact event payload persistence.
                            artifact = await load_task_artifact(
                                db,
                                context_id=current.context_id,
                                task_id=current.task_id,
                                artifact_id=event.artifact_id,
                            )
                        if artifact is None:
                            return
                        stream_response = {"artifactUpdate": {
                            "taskId": current.task_id,
                            "contextId": current.context_id,
                            "artifact": artifact,
                            "append": bool(event.artifact_append),
                            "lastChunk": bool(event.artifact_last_chunk),
                            "metadata": {},
                        }}
                        sse_event = "artifact-update"
                    else:
                        task = await _task_to_v1(
                            db,
                            current,
                            include_artifacts=False,
                            state_override=event.state,
                            status_timestamp=event.created_at,
                        )
                        stream_response = {"statusUpdate": {
                            "taskId": current.task_id,
                            "contextId": current.context_id,
                            "status": task["status"],
                            "metadata": {},
                        }}
                        sse_event = "status-update"
                    payload: dict[str, Any]
                    if jsonrpc:
                        payload = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": stream_response,
                        }
                    else:
                        payload = stream_response
                    yield (
                        f"id: {event.sequence_id}\n"
                        f"event: {sse_event}\n"
                        "data: "
                        + json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        + "\n\n"
                    )
                    cursor = event.sequence_id
                    idle_polls = 0
                    if (
                        event.event_type != "artifact"
                        and event.state in settled_states
                    ):
                        return
                if not events and current.state in settled_states:
                    return
            idle_polls += 1
            if idle_polls % 150 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(
        generate(),
        status_code=200,
        media_type="text/event-stream",
        headers={
            A2A_V1_HEADER: A2A_V1_VERSION,
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-A2A-Binding": "JSONRPC" if jsonrpc else "HTTP+JSON",
        },
    )


def _last_event_sequence(request: Request) -> int:
    raw = str(request.headers.get("last-event-id") or "").strip()
    if not raw:
        return 0
    return _optional_sequence(raw)


def _optional_sequence(value: Any) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        raise A2AV1ProtocolError(
            "INVALID_PARAMS", "afterSequence must be a non-negative integer", "afterSequence"
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS", "afterSequence must be a non-negative integer", "afterSequence"
        ) from exc
    if parsed < 0 or str(parsed) != str(value).strip():
        raise A2AV1ProtocolError(
            "INVALID_PARAMS", "afterSequence must be a non-negative integer", "afterSequence"
        )
    return parsed


def _required_id(params: dict[str, Any]) -> str:
    value = params.get("id")
    if not isinstance(value, str) or not value or len(value) > 128:
        raise A2AV1ProtocolError("INVALID_PARAMS", "id is required", "id")
    return value


def _optional_string(params: dict[str, Any], key: str) -> str:
    value = params.get(key) or ""
    if not isinstance(value, str):
        raise A2AV1ProtocolError("INVALID_PARAMS", f"{key} must be a string", key)
    return value


def _page_size(value: Any) -> int:
    if value is None:
        return 50
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise A2AV1ProtocolError("INVALID_PARAMS", "pageSize must be between 1 and 100", "pageSize")
    return value


def _optional_bool(params: dict[str, Any], key: str) -> bool:
    value = params.get(key, False)
    if not isinstance(value, bool):
        raise A2AV1ProtocolError("INVALID_PARAMS", f"{key} must be boolean", key)
    return value


def _validate_method_params(method: str, params: dict[str, Any]) -> None:
    if method in {"SendMessage", "SendStreamingMessage"}:
        return
    allowed_by_method = {
        "GetTask": {"tenant", "id", "historyLength"},
        "ListTasks": {
            "tenant", "contextId", "status", "pageSize", "pageToken",
            "historyLength", "statusTimestampAfter", "includeArtifacts",
        },
        "CancelTask": {"tenant", "id", "metadata"},
        "SubscribeToTask": {"tenant", "id", "afterSequence"},
    }
    unknown = set(params) - allowed_by_method.get(method, set())
    if unknown:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            f"unknown {method} fields: {', '.join(sorted(unknown))}",
            "params",
        )
    tenant = params.get("tenant") or ""
    if not isinstance(tenant, str):
        raise A2AV1ProtocolError("INVALID_PARAMS", "tenant must be a string", "tenant")
    if tenant:
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "this interface derives tenant scope from authenticated organization",
            "tenant",
        )
    history_length = params.get("historyLength")
    if history_length is not None and (
        isinstance(history_length, bool)
        or not isinstance(history_length, int)
        or not 0 <= history_length <= 100
    ):
        raise A2AV1ProtocolError(
            "INVALID_PARAMS",
            "historyLength must be between 0 and 100",
            "historyLength",
        )
    if method == "CancelTask":
        metadata = params.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise A2AV1ProtocolError(
                "INVALID_PARAMS", "metadata must be an object", "metadata"
            )
    if method == "SubscribeToTask":
        _optional_sequence(params.get("afterSequence"))


def _task_not_found(task_id: str) -> A2AV1ProtocolError:
    return A2AV1ProtocolError(
        "TASK_NOT_FOUND",
        f"task {task_id!r} does not exist or is not accessible",
        metadata={"taskId": task_id},
    )


def _jsonrpc(content: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content=content,
        status_code=200,
        media_type="application/json",
        headers={A2A_V1_HEADER: A2A_V1_VERSION},
    )


def _jsonrpc_error(error: A2AV1ProtocolError, request_id: str | int | None) -> JSONResponse:
    return _jsonrpc(error.jsonrpc_body(request_id))


def _http_json(content: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content=content,
        status_code=200,
        media_type="application/a2a+json",
        headers={A2A_V1_HEADER: A2A_V1_VERSION},
    )


def _http_error(error: A2AV1ProtocolError) -> JSONResponse:
    return JSONResponse(
        content=error.http_body(),
        status_code=error.http_status,
        media_type="application/a2a+json",
        headers={A2A_V1_HEADER: A2A_V1_VERSION},
    )


def _sse(payloads: list[dict[str, Any]], *, jsonrpc: bool) -> StreamingResponse:
    async def generate():
        for payload in payloads:
            yield "data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n"

    return StreamingResponse(
        generate(),
        status_code=200,
        media_type="text/event-stream",
        headers={
            A2A_V1_HEADER: A2A_V1_VERSION,
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-A2A-Binding": "JSONRPC" if jsonrpc else "HTTP+JSON",
        },
    )


def _resolve_card(provider: AgentProvider, agent_id: str) -> AgentCard | None:
    raw = provider(agent_id)
    if raw is None:
        return None
    return raw if isinstance(raw, AgentCard) else AgentCard.model_validate(raw)


async def _resolve_tenant_card(
    provider: AgentProvider,
    agent_id: str,
    organization_id: str,
    db: AsyncSession,
) -> AgentCard | None:
    card = _resolve_card(provider, agent_id)
    if card is not None:
        return card
    agent = await load_tenant_agent(agent_id, organization_id, db)
    if agent is None or not agent.a2a_enabled or agent.status == "archived":
        return None
    # Clone Packs may contain tenant-owned Expert overlays. Resolve them with
    # the same organization-scoped builder used by Run and A2A dispatch so
    # discovery cannot fail (or describe a different runtime) after a project
    # customizes its Expert bindings.
    return agent_card_from_pack(
        await pack_from_tenant_agent(agent, organization_id, db)
    )


def _agent_card_response(
    content: dict[str, Any],
    request: Request,
    *,
    private: bool,
) -> Response:
    canonical = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    etag = f'"{hashlib.sha256(canonical).hexdigest()}"'
    headers = {
        A2A_V1_HEADER: A2A_V1_VERSION,
        "ETag": etag,
        "Cache-Control": "private, max-age=60" if private else "public, max-age=300",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(
        content=content,
        status_code=200,
        media_type="application/a2a+json",
        headers=headers,
    )


__all__ = ["build_v1_router"]
