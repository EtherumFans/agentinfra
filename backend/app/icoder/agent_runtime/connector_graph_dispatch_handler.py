"""Transport-wide Connector graph gate for direct A2A execution.

The unified Agent Run API has an async database session and can apply graphs at
its route boundary. Direct A2A handlers are synchronous adapters, including
dedicated CDI and coding handlers that do not pass through ProviderRegistry.
This wrapper executes the same tenant-owned graph before *any* A2A handler and
marks the request so provider-backed handlers do not execute it twice.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import app.database as database
from app.services.database_tenancy import bind_tenant_to_transaction
from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundRequest,
    InboundResponse,
    extract_text_from_parts,
    make_run_id,
)
from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload
from app.icoder.agent_runtime.orchestrator.run_trace import (
    RunTraceStatus,
    RunTraceStep,
    emit_trace_event,
)
from app.services.agent_runtime_pack import load_tenant_agent
from app.services.connector_executor import ConnectorExecutor
from app.services.connector_graph import (
    ConnectorGraphError,
    execute_connector_graph,
    load_connector_graph,
    validate_graph_bindings,
)


logger = logging.getLogger(__name__)


class ConnectorGraphDispatchHandler:
    """Apply one server-governed graph before the selected A2A adapter."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def handle(self, agent_id: str, request: InboundRequest) -> InboundResponse:
        prepared, error = asyncio.run(self._prepare(agent_id, request))
        if error is not None:
            return error
        return self._inner.handle(agent_id, prepared)

    async def _prepare(
        self,
        agent_id: str,
        request: InboundRequest,
    ) -> tuple[InboundRequest, InboundResponse | None]:
        context_id = request.message.context_id
        tenant_id = str(
            request.metadata.get("organization_id")
            or request.metadata.get("tenant_id")
            or "default"
        )
        run_id = str(request.metadata.get("run_id") or make_run_id())
        trace_id = str(request.metadata.get("trace_id") or run_id)
        request.metadata["run_id"] = run_id
        request.metadata["trace_id"] = trace_id

        safe_parts = redact_payload(request.message.parts).value
        reserved = self._reserved_input_keys(safe_parts)
        # ``extract_text_from_parts`` intentionally renders DataParts for LLM
        # context. Connector ``include_text`` means only the canonical TextPart;
        # selected structured values travel exclusively through ``input_keys``.
        # Keeping those channels separate prevents an unselected DataPart field
        # from reaching a Connector via serialized fallback text.
        safe_text = self._text_input(safe_parts) or extract_text_from_parts(safe_parts)
        if reserved:
            return request, self._error(
                agent_id=agent_id,
                context_id=context_id,
                run_id=run_id,
                safe_text=safe_text,
                code="RESERVED_INPUT_KEY",
                message="DataPart keys beginning with '_' are server-owned.",
                http_status=400,
            )
        request.message.parts = safe_parts

        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db, tenant_id)
            db_agent = await load_tenant_agent(agent_id, tenant_id, db)
            if db_agent is None:
                return request, None
            try:
                graph = load_connector_graph(db_agent)
                if graph is None or not graph.enabled:
                    return request, None
                await validate_graph_bindings(
                    db,
                    organization_id=tenant_id,
                    agent_id=agent_id,
                    graph=graph,
                )
                data_input = self._data_input(safe_parts)
                runtime_request = request.runtime_request
                configured_executor = (
                    getattr(runtime_request.app.state, "connector_executor", None)
                    if runtime_request is not None
                    else None
                )
                emit_trace_event(
                    run_id,
                    RunTraceStep.USER_MESSAGE_RECEIVED,
                    safe_metadata={
                        "agent_id": agent_id,
                        "input_parts": len(safe_parts),
                        "_organization_id": tenant_id,
                        "_trace_id": trace_id,
                    },
                )
                result = await execute_connector_graph(
                    db,
                    executor=configured_executor or ConnectorExecutor(),
                    graph=graph,
                    organization_id=tenant_id,
                    agent_id=agent_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    safe_text=safe_text,
                    safe_extra=data_input,
                    task_id=str(request.metadata.get("_a2a_v1_task_id") or "") or None,
                    actor_type=(
                        "user" if request.metadata.get("user_id")
                        else "api_client" if request.metadata.get("api_client_id")
                        else ""
                    ),
                    actor_id=str(
                        request.metadata.get("user_id")
                        or request.metadata.get("api_client_id")
                        or ""
                    ),
                )
                for node in result.nodes:
                    emit_trace_event(
                        run_id,
                        RunTraceStep.TOOLS_CALL,
                        status=(
                            RunTraceStatus.OK
                            if node.status == "success"
                            else RunTraceStatus.FAILED
                        ),
                        duration_ms=node.latency_ms,
                        safe_metadata={
                            "agent_id": agent_id,
                            "connector_id": node.connector_id,
                            "connector_node_id": node.node_id,
                            "connector_graph_revision": result.revision,
                            "attempts": node.attempts,
                            "error_code": node.error_code,
                            "_organization_id": tenant_id,
                            "_trace_id": trace_id,
                        },
                    )
                payload = result.provider_payload()
                request.message.parts.append({
                    "kind": "data",
                    "data": {
                        "schema": "icoder/ServerConnectorResults/v1",
                        "value": {"_connector_results": payload},
                    },
                })
                request.metadata["connector_graph_preexecuted"] = True
                request.metadata["connector_graph_revision"] = result.revision
                await db.commit()
                return request, None
            except ConnectorGraphError as exc:
                await self._record_failure(
                    db,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    context_id=context_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    safe_text=safe_text,
                    actor_id=str(request.metadata.get("user_id") or ""),
                    error_code=exc.connector_error_code or exc.code,
                    node_id=exc.node_id,
                )
                return request, self._error(
                    agent_id=agent_id,
                    context_id=context_id,
                    run_id=run_id,
                    safe_text=safe_text,
                    code="CONNECTOR_GRAPH_FAILED",
                    message=(
                        "Agent execution was stopped because a required Connector "
                        "graph node did not complete safely."
                    ),
                    http_status=503,
                    revision=int(request.metadata.get("connector_graph_revision") or 0),
                )
            except Exception as exc:
                logger.error(
                    "A2A connector graph gate crashed agent_id=%s error_type=%s",
                    agent_id,
                    type(exc).__name__,
                )
                await db.rollback()
                try:
                    await self._record_failure(
                        db,
                        agent_id=agent_id,
                        tenant_id=tenant_id,
                        context_id=context_id,
                        run_id=run_id,
                        trace_id=trace_id,
                        safe_text=safe_text,
                        actor_id=str(request.metadata.get("user_id") or ""),
                        error_code="CONNECTOR_GRAPH_INTERNAL_ERROR",
                        node_id="",
                    )
                except Exception as audit_exc:
                    logger.error(
                        "A2A connector graph failure audit failed agent_id=%s error_type=%s",
                        agent_id,
                        type(audit_exc).__name__,
                    )
                    await db.rollback()
                return request, self._error(
                    agent_id=agent_id,
                    context_id=context_id,
                    run_id=run_id,
                    safe_text=safe_text,
                    code="CONNECTOR_GRAPH_FAILED",
                    message="Agent execution was stopped because its Connector graph failed safely.",
                    http_status=503,
                )

    @staticmethod
    async def _record_failure(
        db: Any,
        *,
        agent_id: str,
        tenant_id: str,
        context_id: str,
        run_id: str,
        trace_id: str,
        safe_text: str,
        actor_id: str,
        error_code: str,
        node_id: str,
    ) -> None:
        from app.services.run_lifecycle import RunStatus, record_run_start, set_status

        emit_trace_event(
            run_id,
            RunTraceStep.TOOLS_CALL,
            status=RunTraceStatus.FAILED,
            safe_metadata={
                "agent_id": agent_id,
                "connector_node_id": node_id,
                "error_code": error_code,
                "_organization_id": tenant_id,
                "_trace_id": trace_id,
            },
        )
        emit_trace_event(
            run_id,
            RunTraceStep.COMPLETION,
            status=RunTraceStatus.FAILED,
            safe_metadata={
                "agent_id": agent_id,
                "error_code": "CONNECTOR_GRAPH_FAILED",
                "_organization_id": tenant_id,
                "_trace_id": trace_id,
            },
        )
        await record_run_start(
            db,
            run_id=run_id,
            agent_id=agent_id,
            user_id=actor_id,
            organization_id=tenant_id,
            input_text=safe_text,
            runtime_mode="a2a_connector_graph",
            trace_id=trace_id,
            context_id=context_id or None,
        )
        await set_status(
            db,
            run_id=run_id,
            status=RunStatus.FAILED,
            extra_fields={
                "error": True,
                "error_reason": "connector_graph_failed",
                "output_summary": "Agent execution stopped at the Connector graph gate.",
            },
        )
        await db.commit()

    @staticmethod
    def _reserved_input_keys(parts: list[dict[str, Any]]) -> list[str]:
        keys: set[str] = set()
        for part in parts:
            if not isinstance(part, dict) or (part.get("kind") or part.get("type")) != "data":
                continue
            data = part.get("data")
            if not isinstance(data, dict):
                continue
            value = data.get("value") if isinstance(data.get("value"), dict) else data
            if isinstance(value, dict):
                keys.update(str(key) for key in value if str(key).startswith("_"))
        return sorted(keys)

    @staticmethod
    def _data_input(parts: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for part in parts:
            if not isinstance(part, dict) or (part.get("kind") or part.get("type")) != "data":
                continue
            data = part.get("data")
            if not isinstance(data, dict):
                continue
            value = data.get("value")
            if isinstance(value, dict):
                merged.update(value)
            else:
                merged.update(data)
        return merged

    @staticmethod
    def _text_input(parts: list[dict[str, Any]]) -> str:
        return "\n".join(
            str(part.get("text"))
            for part in parts
            if isinstance(part, dict)
            and (part.get("kind") or part.get("type")) == "text"
            and part.get("text")
        ).strip()

    @staticmethod
    def _error(
        *,
        agent_id: str,
        context_id: str,
        run_id: str,
        safe_text: str,
        code: str,
        message: str,
        http_status: int,
        revision: int = 0,
    ) -> InboundResponse:
        return InboundResponse(
            kind="error",
            context_id=context_id,
            metadata={
                "run_id": run_id,
                "agent_id": agent_id,
                "connector_graph_revision": revision,
                "phi_redacted": True,
                "production_writeback_blocked": True,
            },
            error={"code": code, "message": message},
            http_status=http_status,
            redacted_input=safe_text,
        )


__all__ = ["ConnectorGraphDispatchHandler"]
