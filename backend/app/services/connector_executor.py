"""Fail-closed execution layer for persisted Agentic v2 connectors.

The executor is deliberately adapter-driven.  Resource enablement alone never
authorizes network access: a deployment must inject a transport, credential
resolver, registry adapter, or internal Agent invoker.  Local tests inject
in-memory adapters, while an unconfigured production path fails before I/O.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_connector import (
    AgentConnector,
    ConnectorCredential,
    ConnectorExecutionAudit,
)
from app.services.agent_connectors import (
    ConnectorValidationError,
    normalize_config,
    require_agent_in_tenant,
)
from app.services.circuit_breaker import CircuitBreaker
from app.services.database_tenancy import bind_tenant_to_transaction


MAX_INVOCATION_BYTES = 64 * 1024
OPERATION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
AUDIT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
ERROR_CODE_RE = re.compile(r"^CONNECTOR_[A-Z0-9_]{1,54}$")
A2A_OPERATIONS = frozenset({
    "SendMessage", "SendStreamingMessage", "GetTask", "ListTasks",
    "CancelTask", "SubscribeToTask",
})


class ConnectorExecutionError(RuntimeError):
    """Stable, non-sensitive connector failure returned to orchestration."""

    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        http_status_class: str | None = None,
    ) -> None:
        self.code = code if ERROR_CODE_RE.fullmatch(code or "") else "CONNECTOR_FAILURE"
        self.retryable = retryable
        self.http_status_class = (
            http_status_class if http_status_class in {"4xx", "5xx"} else None
        )
        super().__init__(self.code)


class ConnectorTransportError(ConnectorExecutionError):
    pass


@dataclass(frozen=True)
class ConnectorInvocation:
    organization_id: str
    agent_id: str
    connector_id: str
    operation: str
    arguments: dict[str, Any]
    run_id: str | None = None
    task_id: str | None = None
    trace_span_id: str | None = None
    idempotent: bool = False
    data_classification: str = "non_phi"
    purpose_of_use: str = ""
    actor_type: str = ""
    actor_id: str = ""
    delegated_subject_id: str = ""
    granted_scopes: frozenset[str] = field(default_factory=frozenset)
    granted_purposes: frozenset[str] = field(default_factory=frozenset)
    trusted_server_channels: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ConnectorTransportRequest:
    connector_type: str
    url: str
    operation: str
    arguments: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)
    connect_timeout_seconds: float = 5.0
    total_timeout_seconds: float = 30.0
    max_response_bytes: int = 262_144
    protocol_binding: str = ""
    redirect_policy: str = "deny"
    max_redirects: int = 0
    session_scope: str = ""
    agent_card_url: str = ""
    agent_card_digest: str = ""


@dataclass(frozen=True)
class ConnectorExecutionResult:
    connector_id: str
    connector_type: str
    operation: str
    output: dict[str, Any]
    attempts: int
    latency_ms: int


RemoteTransport = Callable[[ConnectorTransportRequest], Awaitable[dict[str, Any]]]
CredentialResolver = Callable[[ConnectorCredential], dict[str, str] | Awaitable[dict[str, str]]]
RegistryInvoker = Callable[[str, str, dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
AgentInvoker = Callable[[str, str, dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]
ContextualRegistryInvoker = Callable[
    [AsyncSession, AgentConnector, ConnectorInvocation, str],
    dict[str, Any] | Awaitable[dict[str, Any]],
]
ContextualAgentInvoker = Callable[
    [AsyncSession, AgentConnector, ConnectorInvocation, str],
    dict[str, Any] | Awaitable[dict[str, Any]],
]
PolicyAuthorizer = Callable[[AgentConnector, ConnectorInvocation], bool | Awaitable[bool]]


async def _maybe_await(value):
    return await value if inspect.isawaitable(value) else value


class ConnectorExecutor:
    def __init__(
        self,
        *,
        remote_transport: RemoteTransport | None = None,
        credential_resolver: CredentialResolver | None = None,
        registry_invoker: RegistryInvoker | None = None,
        agent_invoker: AgentInvoker | None = None,
        contextual_registry_invoker: ContextualRegistryInvoker | None = None,
        contextual_agent_invoker: ContextualAgentInvoker | None = None,
        policy_authorizer: PolicyAuthorizer | None = None,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self._remote_transport = remote_transport
        self._credential_resolver = credential_resolver
        self._registry_invoker = registry_invoker
        self._agent_invoker = agent_invoker
        self._contextual_registry_invoker = contextual_registry_invoker
        self._contextual_agent_invoker = contextual_agent_invoker
        self._policy_authorizer = policy_authorizer
        self._failure_threshold = max(1, min(failure_threshold, 20))
        self._recovery_timeout = max(1.0, min(recovery_timeout_seconds, 300.0))
        self._circuits: dict[str, CircuitBreaker] = {}
        self._semaphores: dict[str, tuple[int, asyncio.Semaphore]] = {}

    def _circuit(self, connector_id: str) -> CircuitBreaker:
        circuit = self._circuits.get(connector_id)
        if circuit is None:
            circuit = CircuitBreaker(
                name=f"connector:{connector_id}",
                failure_threshold=self._failure_threshold,
                recovery_timeout=self._recovery_timeout,
            )
            self._circuits[connector_id] = circuit
        return circuit

    def _semaphore(self, connector_id: str, limit: int) -> asyncio.Semaphore:
        bounded = max(1, min(int(limit), 32))
        current = self._semaphores.get(connector_id)
        if current is None or current[0] != bounded:
            current = (bounded, asyncio.Semaphore(bounded))
            self._semaphores[connector_id] = current
        return current[1]

    async def execute(
        self,
        db: AsyncSession,
        invocation: ConnectorInvocation,
    ) -> ConnectorExecutionResult:
        await bind_tenant_to_transaction(db, invocation.organization_id)
        started = time.monotonic()
        connector = (
            await db.execute(
                select(AgentConnector).where(
                    AgentConnector.organization_id == invocation.organization_id,
                    AgentConnector.agent_id == invocation.agent_id,
                    AgentConnector.id == invocation.connector_id,
                    AgentConnector.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if connector is None:
            raise ConnectorExecutionError("CONNECTOR_NOT_FOUND")
        if not connector.enabled:
            error = ConnectorExecutionError("CONNECTOR_DISABLED")
            await self._audit(db, connector, invocation, started, 0, error, "deny")
            raise error

        try:
            normalized = normalize_config(
                connector.type,
                connector.config_json or {},
                enabled=True,
            )
        except ConnectorValidationError as exc:
            error = ConnectorExecutionError(exc.code)
            await self._audit(db, connector, invocation, started, 0, error, "deny")
            raise error from exc

        try:
            self._validate_audit_identifiers(invocation)
            self._validate_invocation_size(invocation.arguments)
            if invocation.actor_type == "api_client":
                if not invocation.delegated_subject_id:
                    raise ConnectorExecutionError(
                        "CONNECTOR_DELEGATED_SUBJECT_REQUIRED"
                    )
                if invocation.purpose_of_use not in invocation.granted_purposes:
                    raise ConnectorExecutionError("CONNECTOR_PURPOSE_FORBIDDEN")
        except ConnectorExecutionError as error:
            await self._audit(db, connector, invocation, started, 0, error, "deny")
            raise
        if connector.type in {"registry", "mcp", "a2a"}:
            try:
                await self._authorize_remote(connector, invocation)
            except ConnectorExecutionError as error:
                await self._audit(db, connector, invocation, started, 0, error, "deny")
                raise
        circuit = self._circuit(connector.id)
        if circuit.is_open:
            error = ConnectorExecutionError("CONNECTOR_CIRCUIT_OPEN", retryable=True)
            await self._audit(db, connector, invocation, started, 0, error, "deny")
            raise error

        config = normalized.config
        concurrency_limit = int(config.get("concurrency_limit") or 4)
        semaphore = self._semaphore(connector.id, concurrency_limit)
        total_timeout = float(config.get("total_timeout_seconds") or 30.0)
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=total_timeout)
        except asyncio.TimeoutError as exc:
            error = ConnectorExecutionError("CONNECTOR_CONCURRENCY_TIMEOUT", retryable=True)
            circuit.record_failure()
            await self._audit(db, connector, invocation, started, 0, error, "allow")
            raise error from exc
        try:
            return await self._execute_bounded(
                db,
                connector=connector,
                invocation=invocation,
                normalized=normalized,
                circuit=circuit,
                started=started,
            )
        finally:
            semaphore.release()

    async def _execute_bounded(
        self,
        db: AsyncSession,
        *,
        connector: AgentConnector,
        invocation: ConnectorInvocation,
        normalized,
        circuit: CircuitBreaker,
        started: float,
    ) -> ConnectorExecutionResult:
        config = normalized.config
        total_timeout = float(config.get("total_timeout_seconds") or 30.0)
        configured_attempts = int(config.get("max_attempts") or 1)
        max_attempts = configured_attempts if invocation.idempotent else 1
        attempts = 0
        last_error: ConnectorExecutionError | None = None
        while attempts < max_attempts:
            attempts += 1
            elapsed = time.monotonic() - started
            remaining = total_timeout - elapsed
            if remaining <= 0:
                last_error = ConnectorExecutionError(
                    "CONNECTOR_TIMEOUT", retryable=True,
                )
                break
            try:
                output = await asyncio.wait_for(
                    self._dispatch(
                        db,
                        connector=connector,
                        invocation=invocation,
                        normalized=normalized,
                    ),
                    timeout=remaining,
                )
                self._validate_output(output, int(config.get("max_response_bytes") or 262_144))
                circuit.record_success()
                latency_ms = max(0, int((time.monotonic() - started) * 1000))
                await self._audit(db, connector, invocation, started, attempts - 1, None, "allow")
                return ConnectorExecutionResult(
                    connector_id=connector.id,
                    connector_type=connector.type,
                    operation=invocation.operation,
                    output=output,
                    attempts=attempts,
                    latency_ms=latency_ms,
                )
            except asyncio.TimeoutError:
                last_error = ConnectorExecutionError(
                    "CONNECTOR_TIMEOUT", retryable=True,
                )
            except ConnectorExecutionError as exc:
                last_error = exc
            except Exception:
                last_error = ConnectorExecutionError(
                    "CONNECTOR_ADAPTER_FAILURE", retryable=False,
                )
            if not last_error.retryable or attempts >= max_attempts:
                break

        assert last_error is not None
        if last_error.retryable:
            circuit.record_failure()
        await self._audit(
            db,
            connector,
            invocation,
            started,
            max(0, attempts - 1),
            last_error,
            self._policy_for_error(last_error),
        )
        raise last_error

    async def _dispatch(
        self,
        db: AsyncSession,
        *,
        connector: AgentConnector,
        invocation: ConnectorInvocation,
        normalized,
    ) -> dict[str, Any]:
        config = normalized.config
        if connector.type == "schema":
            return self._execute_schema(config, invocation)
        if connector.type == "registry":
            capabilities = set(config.get("capabilities") or [])
            if capabilities and invocation.operation not in capabilities:
                raise ConnectorExecutionError("CONNECTOR_CAPABILITY_NOT_ALLOWED")
            if self._contextual_registry_invoker is not None:
                result = await _maybe_await(
                    self._contextual_registry_invoker(
                        db, connector, invocation, config["registry_key"],
                    )
                )
                return self._require_object(result)
            if self._registry_invoker is None:
                raise ConnectorExecutionError("CONNECTOR_REGISTRY_ADAPTER_NOT_CONFIGURED")
            result = await _maybe_await(
                self._registry_invoker(
                    config["registry_key"], invocation.operation, dict(invocation.arguments),
                )
            )
            return self._require_object(result)
        if connector.type == "agent":
            capabilities = set(config.get("capabilities") or [])
            if capabilities and invocation.operation not in capabilities:
                raise ConnectorExecutionError("CONNECTOR_CAPABILITY_NOT_ALLOWED")
            if (
                self._contextual_agent_invoker is None
                and self._agent_invoker is None
            ):
                raise ConnectorExecutionError("CONNECTOR_AGENT_ADAPTER_NOT_CONFIGURED")
            try:
                await require_agent_in_tenant(
                    db,
                    connector.organization_id,
                    normalized.target_agent_id or "",
                )
            except ConnectorValidationError as exc:
                raise ConnectorExecutionError("CONNECTOR_TARGET_AGENT_NOT_FOUND") from exc
            if self._contextual_agent_invoker is not None:
                result = await _maybe_await(
                    self._contextual_agent_invoker(
                        db,
                        connector,
                        invocation,
                        normalized.target_agent_id or "",
                    )
                )
            else:
                assert self._agent_invoker is not None
                result = await _maybe_await(
                    self._agent_invoker(
                        normalized.target_agent_id or "",
                        invocation.operation,
                        dict(invocation.arguments),
                    )
                )
            return self._require_object(result)

        if self._remote_transport is None:
            raise ConnectorExecutionError("CONNECTOR_TRANSPORT_NOT_CONFIGURED")
        if connector.type == "mcp":
            allowlist = set(config.get("tool_allowlist") or [])
            if allowlist and invocation.operation not in allowlist:
                raise ConnectorExecutionError("CONNECTOR_TOOL_NOT_ALLOWED")
        elif invocation.operation not in A2A_OPERATIONS:
            raise ConnectorExecutionError("CONNECTOR_A2A_OPERATION_NOT_ALLOWED")

        headers = await self._resolve_headers(db, connector, config)
        # ``normalize_config`` above intentionally repeats URL resolution and
        # SSRF/egress checks at execution time; persisted validation is not
        # trusted as a permanent DNS decision.
        request = ConnectorTransportRequest(
            connector_type=connector.type,
            url=normalized.normalized_url or "",
            operation=invocation.operation,
            arguments=dict(invocation.arguments),
            headers=headers,
            connect_timeout_seconds=float(config.get("connect_timeout_seconds") or 5.0),
            total_timeout_seconds=float(config.get("total_timeout_seconds") or 30.0),
            max_response_bytes=int(config.get("max_response_bytes") or 262_144),
            protocol_binding=(
                str(config.get("transport") or "streamable-http")
                if connector.type == "mcp"
                else str((config.get("bindings") or ["JSONRPC"])[0])
            ),
            redirect_policy=str(config.get("redirect_policy") or "deny"),
            max_redirects=int(config.get("max_redirects") or 0),
            session_scope=(
                f"{connector.organization_id}:{connector.id}:{connector.version}"
            ),
            agent_card_url=(
                str(config.get("agent_card_url") or "")
                if connector.type == "a2a"
                else ""
            ),
            agent_card_digest=(
                str(config.get("agent_card_digest") or "")
                if connector.type == "a2a"
                else ""
            ),
        )
        result = await self._remote_transport(request)
        return self._require_object(result)

    async def _resolve_headers(
        self,
        db: AsyncSession,
        connector: AgentConnector,
        config: dict[str, Any],
    ) -> dict[str, str]:
        policy = str(config.get("auth_policy") or "none")
        if policy == "none":
            return {}
        credential = (
            await db.execute(
                select(ConnectorCredential).where(
                    ConnectorCredential.organization_id == connector.organization_id,
                    ConnectorCredential.connector_id == connector.id,
                    ConnectorCredential.status == "active",
                )
            )
        ).scalar_one_or_none()
        if credential is None:
            raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_REQUIRED")
        if self._credential_resolver is None:
            raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_ADAPTER_NOT_CONFIGURED")
        try:
            headers = await _maybe_await(self._credential_resolver(credential))
        except ConnectorExecutionError:
            raise
        except Exception:
            raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_RESOLUTION_FAILED")
        if not isinstance(headers, dict) or not headers:
            raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_RESOLUTION_FAILED")
        normalized_headers: dict[str, str] = {}
        for key, value in headers.items():
            if str(key).casefold() not in {"authorization", "x-api-key"}:
                raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_HEADER_FORBIDDEN")
            if not isinstance(value, str) or not value or len(value) > 4096:
                raise ConnectorExecutionError("CONNECTOR_CREDENTIAL_RESOLUTION_FAILED")
            normalized_headers[str(key)] = value
        return normalized_headers

    async def _authorize_remote(
        self,
        connector: AgentConnector,
        invocation: ConnectorInvocation,
    ) -> None:
        if self._policy_authorizer is None:
            raise ConnectorExecutionError("CONNECTOR_DATA_POLICY_NOT_CONFIGURED")
        if invocation.data_classification not in {
            "non_phi", "deidentified", "phi", "restricted",
        }:
            raise ConnectorExecutionError("CONNECTOR_DATA_CLASSIFICATION_INVALID")
        try:
            allowed = await _maybe_await(self._policy_authorizer(connector, invocation))
        except ConnectorExecutionError:
            raise
        except Exception:
            raise ConnectorExecutionError("CONNECTOR_DATA_POLICY_UNAVAILABLE")
        if allowed is not True:
            raise ConnectorExecutionError("CONNECTOR_DATA_POLICY_DENIED")

    @staticmethod
    def _execute_schema(config: dict[str, Any], invocation: ConnectorInvocation) -> dict[str, Any]:
        schema_key = {
            "validate_input": "input_schema",
            "validate_output": "output_schema",
        }.get(invocation.operation)
        if schema_key is None:
            raise ConnectorExecutionError("CONNECTOR_SCHEMA_OPERATION_NOT_ALLOWED")
        schema = config.get(schema_key)
        if not isinstance(schema, dict):
            raise ConnectorExecutionError("CONNECTOR_SCHEMA_NOT_CONFIGURED")
        try:
            import jsonschema

            validator_type = jsonschema.validators.validator_for(schema)
            validator_type.check_schema(schema)
            validator_type(schema).validate(invocation.arguments)
        except ImportError:
            raise ConnectorExecutionError("CONNECTOR_SCHEMA_VALIDATOR_NOT_CONFIGURED")
        except jsonschema.ValidationError:
            raise ConnectorExecutionError("CONNECTOR_SCHEMA_VALIDATION_FAILED")
        except jsonschema.SchemaError:
            raise ConnectorExecutionError("CONNECTOR_SCHEMA_INVALID")
        return {"valid": True, "schema": schema_key}

    @staticmethod
    def _validate_invocation_size(arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ConnectorExecutionError("CONNECTOR_ARGUMENTS_INVALID")
        try:
            size = len(json.dumps(arguments, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError):
            raise ConnectorExecutionError("CONNECTOR_ARGUMENTS_INVALID")
        if size > MAX_INVOCATION_BYTES:
            raise ConnectorExecutionError("CONNECTOR_ARGUMENTS_TOO_LARGE")

    @staticmethod
    def _validate_audit_identifiers(invocation: ConnectorInvocation) -> None:
        if not OPERATION_RE.fullmatch(invocation.operation or ""):
            raise ConnectorExecutionError("CONNECTOR_OPERATION_INVALID")
        for value, max_length in (
            (invocation.run_id, 128),
            (invocation.task_id, 128),
            (invocation.trace_span_id, 64),
        ):
            if value is not None and (
                len(value) > max_length or not AUDIT_ID_RE.fullmatch(value)
            ):
                raise ConnectorExecutionError("CONNECTOR_AUDIT_IDENTIFIER_INVALID")

    @staticmethod
    def _validate_output(output: dict[str, Any], max_bytes: int) -> None:
        if not isinstance(output, dict):
            raise ConnectorExecutionError("CONNECTOR_RESPONSE_INVALID")
        try:
            size = len(json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        except (TypeError, ValueError):
            raise ConnectorExecutionError("CONNECTOR_RESPONSE_INVALID")
        if size > max_bytes:
            raise ConnectorExecutionError("CONNECTOR_RESPONSE_TOO_LARGE")

    @staticmethod
    def _require_object(value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ConnectorExecutionError("CONNECTOR_RESPONSE_INVALID")
        return value

    @staticmethod
    def _policy_for_error(error: ConnectorExecutionError) -> str:
        denied_suffixes = (
            "_NOT_ALLOWED", "_FORBIDDEN", "_REQUIRED", "_NOT_FOUND",
            "_DISABLED", "_TOO_LARGE", "_INVALID", "_NOT_CONFIGURED",
        )
        return "deny" if error.code.endswith(denied_suffixes) else "allow"

    @staticmethod
    async def _audit(
        db: AsyncSession,
        connector: AgentConnector,
        invocation: ConnectorInvocation,
        started: float,
        retry_count: int,
        error: ConnectorExecutionError | None,
        policy_decision: str,
    ) -> None:
        db.add(
            ConnectorExecutionAudit(
                organization_id=connector.organization_id,
                connector_id=connector.id,
                task_id=(
                    invocation.task_id
                    if invocation.task_id
                    and len(invocation.task_id) <= 128
                    and AUDIT_ID_RE.fullmatch(invocation.task_id)
                    else None
                ),
                run_id=(
                    invocation.run_id
                    if invocation.run_id
                    and len(invocation.run_id) <= 128
                    and AUDIT_ID_RE.fullmatch(invocation.run_id)
                    else None
                ),
                action=(
                    invocation.operation
                    if OPERATION_RE.fullmatch(invocation.operation or "")
                    else "invalid"
                ),
                actor_type=(
                    invocation.actor_type
                    if re.fullmatch(r"[a-z][a-z0-9_]{0,23}", invocation.actor_type or "")
                    else "unknown"
                ),
                actor_id=(
                    invocation.actor_id
                    if invocation.actor_id
                    and len(invocation.actor_id) <= 128
                    and AUDIT_ID_RE.fullmatch(invocation.actor_id)
                    else None
                ),
                delegated_subject_id=(
                    invocation.delegated_subject_id
                    if invocation.delegated_subject_id
                    and len(invocation.delegated_subject_id) <= 128
                    and AUDIT_ID_RE.fullmatch(invocation.delegated_subject_id)
                    else None
                ),
                granted_scopes=sorted({
                    scope for scope in invocation.granted_scopes
                    if isinstance(scope, str)
                    and len(scope) <= 128
                    and re.fullmatch(r"[a-z][a-z0-9_.:-]{0,127}", scope)
                }),
                granted_purposes=sorted({
                    purpose for purpose in invocation.granted_purposes
                    if isinstance(purpose, str)
                    and len(purpose) <= 32
                    and re.fullmatch(r"[a-z][a-z0-9_]{0,31}", purpose)
                }),
                policy_decision=policy_decision,
                status="success" if error is None else "failed",
                latency_ms=max(0, int((time.monotonic() - started) * 1000)),
                retry_count=max(0, retry_count),
                http_status_class=(error.http_status_class if error else None),
                error_code=(error.code[:64] if error else None),
                trace_span_id=(
                    invocation.trace_span_id
                    if invocation.trace_span_id
                    and len(invocation.trace_span_id) <= 64
                    and AUDIT_ID_RE.fullmatch(invocation.trace_span_id)
                    else None
                ),
            )
        )
        await db.flush()


__all__ = [
    "ConnectorExecutionError", "ConnectorTransportError",
    "ConnectorInvocation", "ConnectorTransportRequest",
    "ConnectorExecutionResult", "ConnectorExecutor",
    "ContextualRegistryInvoker", "ContextualAgentInvoker",
]
