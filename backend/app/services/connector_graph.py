"""Deterministic, fail-closed execution of persisted Connector graphs."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as database
from app.icoder.agent_runtime.a2a.input_safety import detect_prompt_injection
from app.icoder.agent_runtime.orchestrator.phi_redactor import (
    PHIRedactionError,
    redact_payload,
)
from app.models.agent import Agent
from app.models.agent_connector import AgentConnector
from app.schemas.connector_graph import (
    ConnectorGraphNode,
    ConnectorGraphResponse,
    ConnectorGraphSpec,
)
from app.services.connector_executor import (
    ConnectorExecutionError,
    ConnectorExecutor,
    ConnectorInvocation,
)


MAX_GRAPH_OUTPUT_BYTES = 256 * 1024
logger = logging.getLogger(__name__)
A2A_GRAPH_OPERATIONS = frozenset({
    "SendMessage", "SendStreamingMessage", "GetTask", "ListTasks",
    "CancelTask", "SubscribeToTask",
})


class ConnectorGraphError(RuntimeError):
    """Stable graph failure safe to expose through the Run error contract."""

    def __init__(
        self,
        code: str,
        *,
        node_id: str = "",
        connector_error_code: str = "",
    ) -> None:
        self.code = code
        self.node_id = node_id
        self.connector_error_code = connector_error_code
        super().__init__(code)


@dataclass(frozen=True)
class ConnectorGraphNodeResult:
    node_id: str
    connector_id: str
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    latency_ms: int = 0
    attempts: int = 0

    def provider_value(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "node_id": self.node_id,
            "status": self.status,
        }
        if self.status == "success":
            value["output"] = self.output
        elif self.status == "failed":
            value["error_code"] = self.error_code
        elif self.status == "skipped":
            value["condition_matched"] = False
        return value


@dataclass(frozen=True)
class ConnectorGraphExecutionResult:
    revision: int
    execution_mode: str
    nodes: tuple[ConnectorGraphNodeResult, ...]

    def provider_payload(self) -> dict[str, Any]:
        return {
            "graph_revision": self.revision,
            "execution_mode": self.execution_mode,
            "nodes": [node.provider_value() for node in self.nodes],
        }


def load_connector_graph(agent: Agent) -> ConnectorGraphResponse | None:
    config = agent.config or {}
    raw = config.get("connector_graph") if isinstance(config, dict) else None
    if raw is None:
        return None
    try:
        return ConnectorGraphResponse.model_validate(raw)
    except ValidationError as exc:
        raise ConnectorGraphError("CONNECTOR_GRAPH_CONFIG_INVALID") from exc


async def validate_graph_bindings(
    db: AsyncSession,
    *,
    organization_id: str,
    agent_id: str,
    graph: ConnectorGraphSpec,
) -> None:
    connector_ids = {node.connector_id for node in graph.nodes}
    if not connector_ids:
        return
    rows = (
        await db.execute(
            select(AgentConnector).where(
                AgentConnector.organization_id == organization_id,
                AgentConnector.agent_id == agent_id,
                AgentConnector.id.in_(connector_ids),
                AgentConnector.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    if set(by_id) != connector_ids:
        raise ConnectorGraphError("CONNECTOR_GRAPH_CONNECTOR_NOT_FOUND")
    if graph.enabled and any(not row.enabled for row in rows):
        raise ConnectorGraphError("CONNECTOR_GRAPH_CONNECTOR_DISABLED")
    for node in graph.nodes:
        validate_graph_node_binding(
            node,
            connector_type=by_id[node.connector_id].type,
            config=by_id[node.connector_id].config_json or {},
        )


def validate_graph_node_binding(
    node: ConnectorGraphNode,
    *,
    connector_type: str,
    config: dict[str, Any],
) -> None:
    """Reject graph operations that the selected Connector cannot perform."""

    if connector_type == "registry" or connector_type == "agent":
        capabilities = set(config.get("capabilities") or [])
        if capabilities and node.operation not in capabilities:
            raise ConnectorGraphError("CONNECTOR_GRAPH_OPERATION_NOT_ALLOWED")
        return
    if connector_type == "mcp":
        allowlist = set(config.get("tool_allowlist") or [])
        if allowlist and node.operation not in allowlist:
            raise ConnectorGraphError("CONNECTOR_GRAPH_OPERATION_NOT_ALLOWED")
        return
    if connector_type == "a2a":
        if node.operation not in A2A_GRAPH_OPERATIONS:
            raise ConnectorGraphError("CONNECTOR_GRAPH_OPERATION_NOT_ALLOWED")
        return
    if connector_type == "schema":
        schema_key = {
            "validate_input": "input_schema",
            "validate_output": "output_schema",
        }.get(node.operation)
        if schema_key is None or not isinstance(config.get(schema_key), dict):
            raise ConnectorGraphError("CONNECTOR_GRAPH_OPERATION_NOT_ALLOWED")
        return
    raise ConnectorGraphError("CONNECTOR_GRAPH_CONNECTOR_TYPE_INVALID")


def _topological_nodes(graph: ConnectorGraphResponse) -> list[ConnectorGraphNode]:
    by_id = {node.id: node for node in graph.nodes}
    remaining = {node.id: set(node.depends_on) for node in graph.nodes}
    ordered: list[ConnectorGraphNode] = []
    while remaining:
        ready = [node_id for node_id in by_id if node_id in remaining and not remaining[node_id]]
        if not ready:
            raise ConnectorGraphError("CONNECTOR_GRAPH_CONFIG_INVALID")
        for node_id in ready:
            ordered.append(by_id[node_id])
            remaining.pop(node_id)
            for dependencies in remaining.values():
                dependencies.discard(node_id)
    return ordered


def _topological_layers(
    graph: ConnectorGraphResponse,
) -> list[list[ConnectorGraphNode]]:
    """Return deterministic dependency layers for bounded parallel execution."""

    by_id = {node.id: node for node in graph.nodes}
    remaining = {node.id: set(node.depends_on) for node in graph.nodes}
    layers: list[list[ConnectorGraphNode]] = []
    while remaining:
        ready_ids = [
            node.id for node in graph.nodes
            if node.id in remaining and not remaining[node.id]
        ]
        if not ready_ids:
            raise ConnectorGraphError("CONNECTOR_GRAPH_CONFIG_INVALID")
        layers.append([by_id[node_id] for node_id in ready_ids])
        for node_id in ready_ids:
            remaining.pop(node_id)
        for dependencies in remaining.values():
            dependencies.difference_update(ready_ids)
    return layers


def _condition_matches(node: ConnectorGraphNode, safe_extra: dict[str, Any]) -> bool:
    condition = node.when
    if condition is None:
        return True
    present = condition.input_key in safe_extra
    if condition.operator == "exists":
        return present
    if not present:
        return False
    candidate = safe_extra[condition.input_key]
    if isinstance(candidate, (dict, list)) or candidate is None:
        return False

    def same_scalar(left: object, right: object) -> bool:
        if isinstance(left, bool) or isinstance(right, bool):
            return type(left) is type(right) and left == right
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return left == right
        return type(left) is type(right) and left == right

    if condition.operator == "equals":
        return same_scalar(candidate, condition.value)
    if condition.operator == "not_equals":
        return not same_scalar(candidate, condition.value)
    assert isinstance(condition.value, list)
    return any(same_scalar(candidate, value) for value in condition.value)


def _safe_connector_output(output: dict[str, Any]) -> dict[str, Any]:
    try:
        safe = redact_payload(output).value
    except (PHIRedactionError, ValueError) as exc:
        raise ConnectorGraphError("CONNECTOR_GRAPH_OUTPUT_REDACTION_FAILED") from exc
    if not isinstance(safe, dict):
        raise ConnectorGraphError("CONNECTOR_GRAPH_OUTPUT_INVALID")
    if detect_prompt_injection(safe):
        raise ConnectorGraphError("CONNECTOR_GRAPH_OUTPUT_SAFETY_BLOCKED")
    return safe


def _bounded_payload_size(value: object) -> int:
    try:
        return len(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise ConnectorGraphError("CONNECTOR_GRAPH_OUTPUT_INVALID") from exc


async def execute_connector_graph(
    db: AsyncSession,
    *,
    executor: ConnectorExecutor,
    graph: ConnectorGraphResponse,
    organization_id: str,
    agent_id: str,
    run_id: str,
    trace_id: str,
    safe_text: str,
    safe_extra: dict[str, Any],
    task_id: str | None = None,
    actor_type: str = "",
    actor_id: str = "",
    delegated_subject_id: str = "",
    granted_scopes: frozenset[str] = frozenset(),
    granted_purposes: frozenset[str] = frozenset(),
) -> ConnectorGraphExecutionResult:
    """Execute a validated graph sequentially or by bounded dependency layer."""

    results: list[ConnectorGraphNodeResult] = []
    by_node: dict[str, ConnectorGraphNodeResult] = {}
    aggregate_bytes = 0

    def arguments_for(node: ConnectorGraphNode) -> dict[str, Any]:
        dependencies = {
            dependency: by_node[dependency].provider_value()
            for dependency in node.depends_on
        }
        arguments: dict[str, Any] = {
            key: safe_extra[key]
            for key in node.input_keys
            if key in safe_extra
        }
        if node.include_text:
            arguments["text"] = safe_text
        if dependencies:
            # Input keys cannot start with an underscore, so callers cannot
            # shadow this server-owned dependency channel.
            arguments["_dependencies"] = dependencies
        return arguments

    async def execute_node(
        node_db: AsyncSession,
        node: ConnectorGraphNode,
        arguments: dict[str, Any],
    ) -> ConnectorGraphNodeResult:
        started = time.monotonic()
        error_code = ""
        try:
            execution = await executor.execute(
                node_db,
                ConnectorInvocation(
                    organization_id=organization_id,
                    agent_id=agent_id,
                    connector_id=node.connector_id,
                    operation=node.operation,
                    arguments=arguments,
                    run_id=run_id,
                    task_id=task_id,
                    trace_span_id=f"graph-{node.id}",
                    idempotent=node.idempotent,
                    data_classification=node.data_classification,
                    purpose_of_use=node.purpose_of_use,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    delegated_subject_id=delegated_subject_id,
                    granted_scopes=granted_scopes,
                    granted_purposes=granted_purposes,
                    trusted_server_channels=(
                        frozenset({"_dependencies"})
                        if "_dependencies" in arguments
                        else frozenset()
                    ),
                ),
            )
            safe_output = _safe_connector_output(execution.output)
            result = ConnectorGraphNodeResult(
                node_id=node.id,
                connector_id=node.connector_id,
                status="success",
                output=safe_output,
                latency_ms=execution.latency_ms,
                attempts=execution.attempts,
            )
        except ConnectorExecutionError as exc:
            error_code = exc.code
            result = ConnectorGraphNodeResult(
                node_id=node.id,
                connector_id=node.connector_id,
                status="failed",
                error_code=error_code,
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )
        except ConnectorGraphError as exc:
            error_code = exc.code
            result = ConnectorGraphNodeResult(
                node_id=node.id,
                connector_id=node.connector_id,
                status="failed",
                error_code=error_code,
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
            )

        return result

    def accept_result(node: ConnectorGraphNode, result: ConnectorGraphNodeResult) -> None:
        nonlocal aggregate_bytes
        if result.status == "success":
            aggregate_bytes += _bounded_payload_size(result.output)
            if aggregate_bytes > MAX_GRAPH_OUTPUT_BYTES:
                raise ConnectorGraphError(
                    "CONNECTOR_GRAPH_OUTPUT_TOO_LARGE", node_id=node.id,
                )
        results.append(result)
        by_node[node.id] = result

    if graph.execution_mode == "sequential":
        for node in _topological_nodes(graph):
            if not _condition_matches(node, safe_extra):
                result = ConnectorGraphNodeResult(
                    node_id=node.id,
                    connector_id=node.connector_id,
                    status="skipped",
                )
            else:
                result = await execute_node(db, node, arguments_for(node))
            accept_result(node, result)
            if result.status == "failed" and node.required:
                raise ConnectorGraphError(
                    "CONNECTOR_GRAPH_REQUIRED_NODE_FAILED",
                    node_id=node.id,
                    connector_error_code=result.error_code,
                )
    else:
        semaphore = asyncio.Semaphore(graph.max_concurrency)

        async def execute_isolated(
            node: ConnectorGraphNode,
            arguments: dict[str, Any],
        ) -> ConnectorGraphNodeResult:
            logger.debug("Parallel Connector graph node scheduled (node_id=%s)", node.id)
            async with semaphore:
                async with database.AsyncSessionLocal() as node_db:
                    try:
                        logger.debug(
                            "Parallel Connector graph node executing (node_id=%s)",
                            node.id,
                        )
                        result = await execute_node(node_db, node, arguments)
                        await node_db.commit()
                        return result
                    except Exception as exc:
                        await node_db.rollback()
                        logger.exception(
                            "Parallel Connector graph node failed internally "
                            "(node_id=%s, exception_type=%s)",
                            node.id,
                            type(exc).__name__,
                        )
                        return ConnectorGraphNodeResult(
                            node_id=node.id,
                            connector_id=node.connector_id,
                            status="failed",
                            error_code="CONNECTOR_GRAPH_INTERNAL_ERROR",
                        )

        for layer in _topological_layers(graph):
            runnable: list[tuple[ConnectorGraphNode, dict[str, Any]]] = []
            layer_results_by_id: dict[str, ConnectorGraphNodeResult] = {}
            for node in layer:
                if _condition_matches(node, safe_extra):
                    runnable.append((node, arguments_for(node)))
                else:
                    layer_results_by_id[node.id] = ConnectorGraphNodeResult(
                        node_id=node.id,
                        connector_id=node.connector_id,
                        status="skipped",
                    )
            layer_results = await asyncio.gather(*(
                execute_isolated(node, arguments)
                for node, arguments in runnable
            ))
            for (node, _arguments), result in zip(runnable, layer_results):
                layer_results_by_id[node.id] = result
            for node in layer:
                accept_result(node, layer_results_by_id[node.id])
            failed_required = next(
                (
                    (node, by_node[node.id]) for node in layer
                    if by_node[node.id].status == "failed" and node.required
                ),
                None,
            )
            if failed_required is not None:
                failed_node, failed_result = failed_required
                logger.warning(
                    "Required parallel Connector graph node failed "
                    "(node_id=%s, error_code=%s)",
                    failed_node.id,
                    failed_result.error_code,
                )
                raise ConnectorGraphError(
                    "CONNECTOR_GRAPH_REQUIRED_NODE_FAILED",
                    node_id=failed_node.id,
                    connector_error_code=failed_result.error_code,
                )

    payload = ConnectorGraphExecutionResult(
        revision=graph.revision,
        execution_mode=graph.execution_mode,
        nodes=tuple(results),
    )
    if _bounded_payload_size(payload.provider_payload()) > MAX_GRAPH_OUTPUT_BYTES:
        raise ConnectorGraphError("CONNECTOR_GRAPH_OUTPUT_TOO_LARGE")
    return payload


__all__ = [
    "ConnectorGraphError",
    "ConnectorGraphExecutionResult",
    "ConnectorGraphNodeResult",
    "execute_connector_graph",
    "load_connector_graph",
    "validate_graph_node_binding",
    "validate_graph_bindings",
]
