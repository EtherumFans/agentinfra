"""Inbound A2A route (SPEC §7.2).

Thin wrapper around :class:`InboundHandler`:

::

    HTTP POST body
      → JSON-RPC parse
      → method validate
      → params.message parse + tenant-scoped context continuation validation
      → InboundRequest + InboundHandler.handle()
      → JSON-RPC success/error envelope
      → HTTP 200 + A2A-Protocol-Version: 0.3

The handler is unaware of JSON-RPC. This module owns the wire format.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import (
    get_current_organization,
    get_current_user_or_oauth_client,
)
from app.models.organization import Organization
from app.services.result_attestation import (
    ResultAttestationError,
    verify_upstream_result_attestations,
)

from ..context.context import ContextMessage
from ..context.context_isolation import ContextIsolationError
from ..context.context_lifecycle import ContextLifecycle
from ..context.context_repository import ContextRepository
from ..context.context_retrieval import select_context_memory
from ..context.context_status import ContextStatus
from ..orchestrator.inbound_handler import (
    InboundHandler,
    InboundMessage,
    InboundRequest,
    make_message_id,
)
from ..orchestrator.phi_redactor import PHIRedactionError, redact_payload
from .input_safety import detect_prompt_injection
from .envelope import (
    SUPPORTED_METHODS,
    JsonRpcRequest,
    make_error_response,
    make_parse_error_response,
    make_success_response,
    parse_request,
    validate_method,
)
from .errors import (
    A2AError,
    A2AErrorCode,
    JSON_RPC_INVALID_REQUEST,
    JSON_RPC_PARSE_ERROR,
    agent_not_found,
    context_invalid,
    context_not_found,
    internal_error,
    input_safety_blocked,
    invalid_params,
    invalid_request,
    phi_redaction_failed,
)
from .messages import parse_params
from .version import (
    A2A_PROTOCOL_HEADER,
    A2A_PROTOCOL_VERSION,
    A2AVersionError,
    validate_version_header,
)


# JSON-RPC spec says outer HTTP status is 200 for protocol errors.
# However, two cases (parse error + missing protocol version) cannot even
# be parsed into a JSON-RPC envelope, so the route returns 400 directly.
_OUTER_HTTP_STATUS: int = 200


def build_inbound_router(handler: InboundHandler) -> APIRouter:
    """Build the inbound message:send router.

    Caller mounts it at e.g. ``/api/icoder/agents/{agent_id}`` — the
    :func:`mount_a2a` helper does this.
    """
    router = APIRouter(tags=["a2a-inbound"])

    @router.post("/v1/message:send", operation_id="a2a_message_send_v0_3")
    async def message_send(
        agent_id: str,
        request: Request,
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        """``POST /v1/message:send`` — A2A v0.3 message/send entry point."""
        return await _dispatch(
            handler,
            agent_id,
            request,
            organization_id=current_org.id,
            db=db,
            allowed_methods=("message/send",),
        )

    @router.post(
        "/v1/message:stream",
        operation_id="a2a_message_stream_v0_3",
        response_class=StreamingResponse,
        response_model=None,
    )
    async def message_stream(
        agent_id: str,
        request: Request,
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ):
        """Run an A2A turn over a fail-closed server-sent event stream.

        The stream opens before the potentially long Agent execution and emits
        status heartbeats while the canonical ``message:send`` processing
        pipeline performs PHI redaction, context isolation, execution and
        atomic persistence.  Final output is then projected into the same
        Corti-observed event family used by the Console runtime.  No synthetic
        clinical token is emitted: ``text-delta`` events contain only text
        already present in the completed, validated A2A response.
        """
        parsed, params, error_response = await _parse_inbound_request(
            request,
            allowed_methods=("message/stream",),
        )
        if error_response is not None:
            return error_response
        assert parsed is not None and params is not None

        return StreamingResponse(
            _stream_dispatch(
                handler,
                agent_id,
                request,
                organization_id=current_org.id,
                db=db,
                parsed=parsed,
                params=params,
            ),
            status_code=200,
            media_type="text/event-stream",
            headers={
                A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION,
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get("/v1/contexts/{context_id}", operation_id="a2a_get_context_v0_3")
    async def get_context(
        agent_id: str,
        context_id: str,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        _identity: tuple = Depends(get_current_user_or_oauth_client),
        current_org: Organization = Depends(get_current_organization),
        db: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        """Return tenant/agent-scoped messages and tasks for one context."""
        repo = ContextRepository(db)
        try:
            row = await repo.get_for_org(context_id, current_org.id)
        except ContextIsolationError:
            row = None
        if row is None or row.agent_id != agent_id:
            return _error_response(context_not_found(context_id), None, 404)

        messages = await repo.get_messages(context_id)
        tasks = await repo.get_tasks(context_id)
        items: list[dict[str, Any]] = [
            {
                "kind": "message",
                "role": message.role,
                "parts": message.parts,
                "messageId": message.message_id,
                "contextId": context_id,
                "metadata": message.metadata,
                "timestamp": message.timestamp.isoformat(),
            }
            for message in messages
        ]
        items.extend(
            {
                "kind": "task",
                "id": task.task_id,
                "contextId": context_id,
                "status": {
                    "state": task.state,
                    "timestamp": task.started_at.isoformat(),
                },
                "history": [],
                "artifacts": [],
                "metadata": {},
            }
            for task in tasks
        )
        items.sort(
            key=lambda item: item.get("timestamp")
            or item.get("status", {}).get("timestamp", "")
        )
        return JSONResponse(
            status_code=200,
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            content={"id": context_id, "items": items[offset:offset + limit]},
        )

    return router


async def _dispatch(
    handler: InboundHandler,
    agent_id: str,
    request: Request,
    *,
    organization_id: str,
    db: AsyncSession,
    allowed_methods: tuple[str, ...] = SUPPORTED_METHODS,
    parsed_request: JsonRpcRequest | None = None,
    parsed_params: dict[str, Any] | None = None,
    stream_sink: Any = None,
    server_task_id: str = "",
) -> JSONResponse:
    """Internal: parse envelope, call handler, serialize response."""
    parsed = parsed_request
    params = parsed_params
    if parsed is None or params is None:
        parsed, params, error_response = await _parse_inbound_request(
            request,
            allowed_methods=allowed_methods,
        )
        if error_response is not None:
            return error_response
    assert parsed is not None and params is not None

    message = params["message"]
    msg_obj = parsed.params["message"] if parsed.params else {}

    # Authenticate upstream Agent outputs against their exact pre-redaction
    # JSON.  Verifying after PHI redaction would compare the proof with a
    # transformed result and reject legitimate chains (or tempt callers to
    # weaken the digest).  The verified marker below is server-owned and
    # overwrites any same-named client metadata.
    raw_upstream_results: list[dict[str, Any]] = []
    for part in message["parts"]:
        if not isinstance(part, dict) or part.get("kind") != "data":
            continue
        data = part.get("data")
        value = data.get("value") if isinstance(data, dict) else None
        if not isinstance(value, dict):
            continue
        candidate = value.get("upstream_results")
        if isinstance(candidate, list):
            raw_upstream_results.extend(candidate)
    try:
        verify_upstream_result_attestations(
            raw_upstream_results,
            organization_id=organization_id,
        )
    except ResultAttestationError:
        return _error_response(
            invalid_params("an upstream Agent result could not be authenticated"),
            parsed.id,
            400,
        )

    # Enforce the PHI boundary before context lookup, handler selection, tool
    # execution, or persistence. This covers nested DataPart and metadata
    # strings that text-only downstream redaction cannot see.
    # ``_a2a_v1_task_id`` is an internal bridge field, not client content.
    # Remove any client-supplied value before recursive PHI redaction, then
    # re-attach only the Task ID supplied by the trusted v1 transport.  Apart
    # from preventing correlation spoofing, this keeps phone-like digit runs
    # inside UUIDs from being transformed by clinical free-text rules.
    client_metadata = dict(message["metadata"] or {})
    client_metadata.pop("_a2a_v1_task_id", None)
    try:
        route_redaction = redact_payload({
            "parts": message["parts"],
            "metadata": client_metadata,
        })
    except PHIRedactionError:
        return _error_response(
            phi_redaction_failed(
                "request could not be safely de-identified and was not executed"
            ),
            parsed.id,
            500,
        )
    safe_message_payload = route_redaction.value
    message = {
        **message,
        "parts": safe_message_payload["parts"],
        "metadata": safe_message_payload["metadata"],
    }

    # Explicit instruction-hierarchy attacks are rejected before Context
    # creation, handler selection, model/tool execution, or persistence.  Only
    # stable rule IDs enter the response; matched content is never echoed.
    injection_rules = detect_prompt_injection(safe_message_payload)
    if injection_rules:
        error = input_safety_blocked(
            "request was not executed; matched safety rules: "
            + ",".join(injection_rules)
        )
        return _error_response(error, parsed.id, error.http_status)

    # ── [5] Resolve new vs continued context. The client may only reuse a
    # server-issued ID that belongs to this organization and agent and is
    # still ACTIVE. Wrong-tenant and missing IDs are intentionally identical.
    repo = ContextRepository(db)
    lifecycle = ContextLifecycle(repo)
    requested_context_id = message.get("contextId") or ""
    created_new_context = False
    if requested_context_id:
        try:
            row = await repo.get_for_org(requested_context_id, organization_id)
        except ContextIsolationError:
            return _error_response(
                context_invalid("contextId must be a canonical UUID v4"),
                parsed.id,
                400,
            )
        if row is None or row.agent_id != agent_id:
            return _error_response(
                context_not_found(requested_context_id), parsed.id, 404
            )
        context = await lifecycle.expire_if_overdue(requested_context_id)
        if context is None or context.status != ContextStatus.ACTIVE:
            return _error_response(
                context_invalid("context is no longer active"), parsed.id, 409
            )
        context_id = requested_context_id
    else:
        context = await lifecycle.create(
            agent_id=agent_id,
            organization_id=organization_id,
        )
        context_id = context.id
        created_new_context = True

    inbound_message_id = message["messageId"] or make_message_id()
    if await repo.get_messages(context_id, message_id=inbound_message_id):
        return _error_response(
            invalid_params("message.messageId already exists in this context"),
            parsed.id,
            400,
        )

    current_text = "\n".join(
        str(part.get("text", ""))
        for part in message["parts"]
        if isinstance(part, dict) and part.get("kind") == "text"
    )
    prior_messages = await repo.get_messages(context_id)
    memory_selection = select_context_memory(current_text, prior_messages)

    # ── [6] Build InboundRequest with a route-validated continuation ID.
    inbound_msg = InboundMessage(
        role=message["role"],
        parts=message["parts"],
        interaction_id=message["messageId"] or msg_obj.get("messageId", ""),
        context_id=context_id,
    )
    inbound_req = InboundRequest(
        message=inbound_msg,
        metadata={
            **(message["metadata"] or {}),
            **(
                {"_a2a_v1_task_id": server_task_id}
                if server_task_id
                else {}
            ),
            "context_id": context_id,
            "organization_id": organization_id,
            "upstream_result_attestations_verified": True,
            "upstream_result_attestation_count": len(raw_upstream_results),
            "route_redaction_entity_types": route_redaction.entity_types,
            "route_redaction_entity_counts": route_redaction.entity_counts,
            "route_redaction_applied": route_redaction.redaction_applied,
            "context_memory_mode": memory_selection.retrieval_mode,
            "context_memory_candidate_count": memory_selection.candidate_count,
            "context_memory_selected_count": memory_selection.selected_count,
        },
        context_messages=[
            {
                "role": prior.role,
                "parts": prior.parts,
                "messageId": prior.message_id,
            }
            for prior in memory_selection.messages
        ],
        runtime_request=request,
        stream_sink=stream_sink,
    )

    # ── [7] Call handler (sync, but route is async) ──────────────────
    # Run in a thread so the sync handler (and any asyncio.run inside
    # its LLM/Expert adapters) doesn't deadlock against the running
    # event loop. Also keeps the loop unblocked during long LLM calls.
    import asyncio as _asyncio
    response = await _asyncio.to_thread(handler.handle, agent_id, inbound_req)
    if response.kind == "task":
        # The durable transport owns Task identity and Context correlation.
        # A handler may choose the state/status message but cannot redirect a
        # continuation to an arbitrary Task or Context.
        response.context_id = context_id
        if server_task_id:
            response.task_id = server_task_id

    # Downstream handlers may re-redact the already-safe text and therefore
    # report no detections. Preserve the boundary detections in the public
    # audit metadata without exposing matched values.
    handler_types = response.metadata.get("redaction_entity_types", []) or []
    response.metadata["redaction_entity_types"] = sorted(
        set(handler_types) | set(route_redaction.entity_types)
    )
    response.metadata["redaction_entity_counts"] = dict(
        route_redaction.entity_counts
    )
    response.metadata["redaction_applied"] = route_redaction.redaction_applied
    response.metadata["phi_redacted"] = True

    # ── [8] Persist only redacted user content plus derived agent output.
    # Both messages are appended in one DB transaction so a partial turn can
    # never appear in context history.
    if response.redacted_input:
        now = datetime.now(timezone.utc)
        a2a_v1_task_id = str(
            inbound_req.metadata.get("_a2a_v1_task_id") or ""
        )
        context_messages = [
            ContextMessage(
                message_id=inbound_message_id,
                role=message["role"],
                parts=[{"kind": "text", "text": response.redacted_input}],
                timestamp=now,
                redacted=True,
                metadata={
                    "source_part_count": len(message["parts"]),
                    **(
                        {"a2a_v1_task_id": a2a_v1_task_id}
                        if a2a_v1_task_id
                        else {}
                    ),
                },
            )
        ]
        if response.kind in {"message", "task"} and response.message_id and response.parts:
            context_messages.append(
                ContextMessage(
                    message_id=response.message_id,
                    role="agent",
                    parts=response.parts,
                    timestamp=now + timedelta(microseconds=1),
                    redacted=True,
                    metadata={
                        "run_id": response.metadata.get("run_id", ""),
                        **(
                            {"a2a_v1_task_id": a2a_v1_task_id}
                            if a2a_v1_task_id
                            else {}
                        ),
                    },
                )
            )
        try:
            await repo.add_messages(context_id, context_messages)
        except Exception as exc:
            await db.rollback()
            return _error_response(
                internal_error(
                    f"context persistence failed: {type(exc).__name__}"
                ),
                parsed.id,
                500,
            )
    elif created_new_context:
        # Invalid requests and pre-redaction failures must not leave empty
        # server-generated contexts behind.
        await repo.delete_context(context_id)

    # Emit only the response that has crossed every output-contract, audit,
    # PHI and context-persistence boundary. Provider-native deltas remain
    # provisional telemetry and can never become public A2A Artifact chunks.
    # The durable v1 Task runtime consumes this internal event family; v0.3
    # requests have no server-owned Task ID and therefore do not receive it.
    a2a_v1_task_id = str(
        inbound_req.metadata.get("_a2a_v1_task_id") or ""
    )
    if stream_sink is not None and response.kind == "message" and a2a_v1_task_id:
        from .v1.artifact_store import validated_stream_artifact_chunks

        chunks = validated_stream_artifact_chunks(
            task_id=a2a_v1_task_id,
            parts=response.parts,
            source_message_id=response.message_id,
        )
        for index, artifact in enumerate(chunks):
            stream_sink({
                "step": "a2a_validated_artifact_chunk",
                "payload": {
                    "artifact": artifact,
                    "append": index > 0,
                    "lastChunk": index == len(chunks) - 1,
                },
            })

    # ── [9] Serialize response
    return _serialize_response(parsed.id, response)


async def _parse_inbound_request(
    request: Request,
    *,
    allowed_methods: tuple[str, ...],
) -> tuple[JsonRpcRequest | None, dict[str, Any] | None, JSONResponse | None]:
    """Validate the transport envelope without executing or persisting it."""
    try:
        validate_version_header(dict(request.headers))
    except A2AVersionError as exc:
        return None, None, JSONResponse(
            status_code=400,
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            content=make_parse_error_response(str(exc)),
        )

    raw = await request.body()
    parsed = parse_request(raw)
    if isinstance(parsed, A2AError):
        return None, None, _error_response(parsed, None, _OUTER_HTTP_STATUS)
    if not isinstance(parsed, JsonRpcRequest):
        error = A2AError(
            code=A2AErrorCode.INTERNAL_ERROR,
            details="envelope parser returned unexpected type",
        )
        return None, None, _error_response(error, None, _OUTER_HTTP_STATUS)

    method_error = validate_method(parsed.method, allowed_methods)
    if method_error is not None:
        return None, None, _error_response(
            method_error,
            parsed.id,
            method_error.http_status,
        )
    try:
        params = parse_params(parsed.params)
    except A2AError as exc:
        return None, None, _error_response(exc, parsed.id, exc.http_status)
    return parsed, params, None


def _sse_event(event: str, payload: Any) -> str:
    data = payload if isinstance(payload, str) else json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: {event}\ndata: {data}\n\n"


def _json_response_body(response: JSONResponse) -> dict[str, Any]:
    try:
        decoded = json.loads(bytes(response.body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return make_parse_error_response("stream response serialization failed")
    return decoded if isinstance(decoded, dict) else make_parse_error_response(
        "stream response was not a JSON object"
    )


def _stream_text(body: dict[str, Any]) -> str:
    """Extract only server-produced response text for ``text-delta`` events."""
    result = body.get("result")
    if not isinstance(result, dict):
        return ""
    chunks: list[str] = []
    for part in result.get("parts") or []:
        if not isinstance(part, dict):
            continue
        if part.get("kind") == "text" and isinstance(part.get("text"), str):
            chunks.append(part["text"])
            continue
        data = part.get("data")
        if not isinstance(data, dict):
            continue
        for key in ("summary", "markdown"):
            value = data.get(key)
            if isinstance(value, str) and value and value not in chunks:
                chunks.append(value)
    return "\n\n".join(chunks)


def _project_provider_stream_event(
    event: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Project internal provider events to a PHI-safe SSE telemetry shape.

    Provisional model text and tool arguments are intentionally not copied to
    the transport before the final output contract/safety boundary succeeds.
    Clients still receive real-time evidence that native tokens/tool fragments
    are arriving, while the final ``text-delta`` remains validated content.
    """
    step = str(event.get("step") or "")
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    if step == "provider_text_delta":
        delta = payload.get("delta")
        if not isinstance(delta, str) or not delta:
            return None
        return "data-provider-progress", {
            "kind": "text_delta",
            "characters": len(delta),
            "native": bool(payload.get("native", False)),
            "provisional": True,
        }
    if step == "provider_tool_call_delta":
        return "data-tool-call-delta", {
            "index": int(payload.get("index", 0) or 0),
            "idPresent": bool(payload.get("id_present", False)),
            "argumentCharacters": int(
                payload.get("argument_characters", 0) or 0
            ),
            "native": bool(payload.get("native", False)),
            "provisional": True,
        }
    if step == "provider_usage":
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return "data-provider-usage", {
            "inputTokens": int(usage.get("input_tokens", 0) or 0),
            "outputTokens": int(usage.get("output_tokens", 0) or 0),
        }
    if step == "provider_reset":
        return "data-provider-reset", {
            "native": bool(payload.get("native", False)),
            "reason": "provider_failover",
        }
    if step == "tool_call_completed":
        record = event.get("payload")
        return "data-tool-call", {
            "toolName": str(getattr(record, "tool_name", ""))[:128],
            "durationMs": int(getattr(record, "duration_ms", 0) or 0),
            "failed": bool(getattr(record, "error", None)),
        }
    return None


async def _stream_dispatch(
    handler: InboundHandler,
    agent_id: str,
    request: Request,
    *,
    organization_id: str,
    db: AsyncSession,
    parsed: JsonRpcRequest,
    params: dict[str, Any],
):
    """Open immediately, keep the proxy alive, then emit validated output."""
    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    provider_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def stream_sink(event: dict[str, Any]) -> None:
        if isinstance(event, dict):
            loop.call_soon_threadsafe(provider_events.put_nowait, event)

    task = asyncio.create_task(
        _dispatch(
            handler,
            agent_id,
            request,
            organization_id=organization_id,
            db=db,
            allowed_methods=("message/stream",),
            parsed_request=parsed,
            parsed_params=params,
            stream_sink=stream_sink,
        )
    )
    yield _sse_event("data-status-update", {
        "state": "working",
        "message": "Running agent",
        "requestId": parsed.id,
    })

    try:
        last_heartbeat = time.perf_counter()
        while not task.done():
            heartbeat_in = max(
                0.05,
                5.0 - (time.perf_counter() - last_heartbeat),
            )
            try:
                provider_event = await asyncio.wait_for(
                    provider_events.get(),
                    timeout=heartbeat_in,
                )
            except TimeoutError:
                last_heartbeat = time.perf_counter()
                yield _sse_event("data-status-update", {
                    "state": "working",
                    "message": "Agent execution in progress",
                    "requestId": parsed.id,
                    "elapsedMs": int((time.perf_counter() - started) * 1000),
                })
            else:
                projected = _project_provider_stream_event(provider_event)
                if projected is not None:
                    event_name, payload = projected
                    yield _sse_event(event_name, payload)
        response = await task
        while not provider_events.empty():
            projected = _project_provider_stream_event(
                provider_events.get_nowait()
            )
            if projected is not None:
                event_name, payload = projected
                yield _sse_event(event_name, payload)
    except asyncio.CancelledError:
        # The provider may already be writing audit/context state.  Do not
        # abandon that transaction merely because the client disconnected.
        if not task.done():
            try:
                await asyncio.shield(task)
            except Exception:
                pass
        raise
    except Exception:
        response = _error_response(
            internal_error("stream dispatch failed"),
            parsed.id,
            500,
        )

    body = _json_response_body(response)
    is_error = "error" in body
    yield _sse_event("data-json", body)

    text = _stream_text(body)
    if text:
        yield _sse_event("text-start", {"requestId": parsed.id})
        for offset in range(0, len(text), 200):
            yield _sse_event("text-delta", {"delta": text[offset:offset + 200]})
        yield _sse_event("text-end", {"requestId": parsed.id})

    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    metadata = result.get("metadata") if isinstance(result, dict) else {}
    yield _sse_event("message-metadata", {
        "requestId": parsed.id,
        "httpStatus": response.status_code,
        "metadata": metadata if isinstance(metadata, dict) else {},
    })
    yield _sse_event("finish", {
        "finishReason": "error" if is_error else "stop",
        "state": "failed" if is_error else "completed",
        "elapsedMs": int((time.perf_counter() - started) * 1000),
    })
    yield _sse_event("done", "[DONE]")


def _serialize_response(req_id: str | int | None, response: Any) -> JSONResponse:
    """Build JSON-RPC envelope from an :class:`InboundResponse`."""
    if response.kind == "message":
        result = {
            "kind": "message",
            "role": response.role,
            "messageId": response.message_id,
            "contextId": response.context_id,
            "parts": response.parts,
            "metadata": response.metadata,
        }
        body = make_success_response(req_id, result)
        return JSONResponse(
            status_code=_OUTER_HTTP_STATUS,
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            content=body,
        )

    if response.kind == "task":
        result = response.to_dict()
        from .task_state import settled_state_from_result

        try:
            settled_state_from_result(result)
        except ValueError:
            return _error_response(
                internal_error("Agent returned an invalid settled Task"),
                req_id,
                500,
            )
        body = make_success_response(req_id, result)
        return JSONResponse(
            status_code=_OUTER_HTTP_STATUS,
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            content=body,
        )

    # Error path
    err_obj = response.error or {}
    # Map the OrchestratorError envelope to A2AError for envelope shape.
    a2a_code = err_obj.get("code", "INTERNAL_ERROR")
    # Translate legacy internal code names → A2A business codes if needed.
    code = _translate_code(a2a_code)
    details = err_obj.get("message", "")
    # Preserve only server-owned correlation/attribution fields. Previously an
    # A2A failure discarded project Agent identity even though the successful
    # envelope retained it, leaving failed clinical runs unauditable to the
    # caller. Never forward arbitrary handler metadata here.
    response_metadata = response.metadata or {}
    safe_error_metadata = {
        key: response_metadata[key]
        for key in (
            "agent_id",
            "source_runtime_agent_id",
            "run_id",
            "trace_id",
            "connector_graph_revision",
        )
        if response_metadata.get(key) not in (None, "")
    }
    err = A2AError(code=code, details=details, extra=safe_error_metadata)
    return _error_response(err, req_id, response.http_status)


def _error_response(
    err: A2AError, req_id: str | int | None, http_status: int
) -> JSONResponse:
    """Build a JSON-RPC error response with the A2A-Protocol-Version header."""
    body = make_error_response(req_id, err)
    return JSONResponse(
        status_code=http_status,
        headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
        content=body,
    )


# ---------------------------------------------------------------------------
# Code translation: legacy OrchestratorError codes → A2A business codes
# ---------------------------------------------------------------------------

# Maps the OrchestratorError envelope codes used by the handler to the
# matching A2A business codes. The handler uses a small set of lowercased
# codes; A2A uses UPPERCASE_SNAKE. Keep this table tight.
_LEGACY_TO_A2A_CODE = {
    "invalid_request": A2AErrorCode.INVALID_REQUEST,
    "planning_failed": A2AErrorCode.PLANNING_FAILED,
    "expert_failed": A2AErrorCode.EXPERT_FAILED,
    "aggregation_failed": A2AErrorCode.AGGREGATION_FAILED,
    "connector_graph_failed": A2AErrorCode.CONNECTOR_GRAPH_FAILED,
    "phi_redaction_failed": A2AErrorCode.PHI_REDACTION_FAILED,
    "agent_not_found": A2AErrorCode.AGENT_NOT_FOUND,
    "agent_not_published": A2AErrorCode.AGENT_NOT_PUBLISHED,
}


def _translate_code(legacy: str) -> str:
    """Translate legacy OrchestratorError code to A2A business code."""
    return _LEGACY_TO_A2A_CODE.get(legacy.lower(), A2AErrorCode.INTERNAL_ERROR)


__all__ = [
    "build_inbound_router",
]
