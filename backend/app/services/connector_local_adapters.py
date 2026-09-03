"""Governed in-process adapters for registry and internal Agent Connectors."""
from __future__ import annotations

import contextvars
import inspect
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundMessage,
    InboundRequest,
)
from app.models.agent_connector import AgentConnector
from app.services.connector_executor import (
    ConnectorExecutionError,
    ConnectorExecutor,
    ConnectorInvocation,
)
from app.services.connector_external_registry import EXTERNAL_REGISTRY_KEYS
from app.services.connector_public_registry import PUBLIC_REGISTRY_KEYS


LOCAL_REGISTRY_KEYS = frozenset({
    "memory", "medical-calculator", "medical-coding", "interviewing",
})
EXTERNALLY_GATED_REGISTRY_KEYS = EXTERNAL_REGISTRY_KEYS
INTERNAL_AGENT_OPERATIONS = frozenset({"run", "delegate", "SendMessage"})
MAX_INTERNAL_AGENT_DEPTH = 8
_agent_call_chain: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "connector_agent_call_chain", default=(),
)


def _bounded_string(value: object, *, maximum: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
    result = value.strip()
    if (required and not result) or len(result) > maximum:
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
    return result


class GovernedRegistryAdapter:
    """Dispatch only explicitly approved, locally implemented capabilities."""

    def __init__(
        self,
        app: Any | None = None,
        *,
        public_registry_provider: Any | None = None,
        external_registry_provider: Any | None = None,
        memory_store: Any | None = None,
    ) -> None:
        self._app = app
        self._public_registry_provider = public_registry_provider
        self._external_registry_provider = external_registry_provider
        self._memory_store = memory_store

    async def __call__(
        self,
        _db: AsyncSession,
        _connector: AgentConnector,
        invocation: ConnectorInvocation,
        registry_key: str,
    ) -> dict[str, Any]:
        if registry_key in PUBLIC_REGISTRY_KEYS:
            if self._public_registry_provider is None:
                raise ConnectorExecutionError(
                    "CONNECTOR_REGISTRY_PROVIDER_UNAVAILABLE"
                )
            result = self._public_registry_provider(registry_key, invocation)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                raise ConnectorExecutionError("CONNECTOR_RESPONSE_INVALID")
            return result
        if registry_key in EXTERNALLY_GATED_REGISTRY_KEYS:
            if self._external_registry_provider is None:
                raise ConnectorExecutionError(
                    "CONNECTOR_REGISTRY_PROVIDER_UNAVAILABLE"
                )
            result = self._external_registry_provider(registry_key, invocation)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                raise ConnectorExecutionError("CONNECTOR_RESPONSE_INVALID")
            return result
        if registry_key == "memory":
            if invocation.operation in {"remember", "recall", "forget"}:
                if self._memory_store is None:
                    raise ConnectorExecutionError(
                        "CONNECTOR_REGISTRY_PROVIDER_UNAVAILABLE"
                    )
                return await self._memory_store.invoke(_db, invocation)
            return self._memory(invocation.operation, invocation.arguments)
        if registry_key == "medical-calculator":
            return self._calculator(invocation.operation, invocation.arguments)
        if registry_key == "interviewing":
            return self._interviewing(invocation.operation, invocation.arguments)
        if registry_key == "medical-coding":
            return await self._medical_coding(invocation)
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_ENTRY_UNAVAILABLE")

    @staticmethod
    def _memory(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation != "retrieve":
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_OPERATION_NOT_ALLOWED")
        from app.agents.experts.memory_expert import retrieve

        query = _bounded_string(arguments.get("query"), maximum=2000)
        messages = arguments.get("thread_messages", [])
        top_k = arguments.get("top_k", 5)
        if (
            not isinstance(messages, list)
            or len(messages) > 100
            or not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or not 1 <= top_k <= 20
        ):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        result = retrieve(query, messages, top_k)
        return {
            **asdict(result),
            "authoritative": False,
            "clinical_use": "context_retrieval_only",
        }

    @staticmethod
    def _calculator(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation != "calculate":
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_OPERATION_NOT_ALLOWED")
        from app.agents.experts.medical_calculator_expert import calculate

        calculator = _bounded_string(arguments.get("calculator"), maximum=64)
        inputs = arguments.get("inputs")
        if not isinstance(inputs, dict) or len(inputs) > 32:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        try:
            result = calculate(calculator, **inputs)
        except (NotImplementedError, TypeError, ValueError, OverflowError) as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_ARGUMENTS_INVALID"
            ) from exc
        return {
            **asdict(result),
            "authoritative": False,
            "clinical_use": "licensed_clinician_review_required",
        }

    @classmethod
    def _interviewing(
        cls, operation: str, arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from app.agents.experts.interviewing_expert import (
            QuestionSpec,
            advance,
            deserialize_state,
            serialize_state,
            start_interview,
            transcript,
        )

        raw_questions = arguments.get("questions")
        if not isinstance(raw_questions, list) or not 1 <= len(raw_questions) <= 64:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        questions: list[QuestionSpec] = []
        seen: set[str] = set()
        for item in raw_questions:
            if not isinstance(item, dict) or set(item) - {
                "key", "prompt", "kind", "choices", "required",
            }:
                raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
            key = _bounded_string(item.get("key"), maximum=64)
            prompt = _bounded_string(item.get("prompt"), maximum=1000)
            kind = _bounded_string(item.get("kind", "text"), maximum=16)
            choices = item.get("choices")
            required = item.get("required", True)
            if (
                key in seen
                or kind not in {"text", "number", "choice", "boolean"}
                or not isinstance(required, bool)
                or (
                    choices is not None
                    and (
                        not isinstance(choices, list)
                        or len(choices) > 32
                        or any(
                            not isinstance(choice, str) or len(choice) > 256
                            for choice in choices
                        )
                    )
                )
            ):
                raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
            seen.add(key)
            questions.append(QuestionSpec(
                key=key,
                prompt=prompt,
                kind=kind,
                choices=list(choices) if choices is not None else None,
                required=required,
            ))

        try:
            if operation == "start":
                state = start_interview(
                    _bounded_string(
                        arguments.get("questionnaire_key"), maximum=128,
                    ),
                    questions,
                )
                step = advance(state)
            elif operation == "advance":
                raw_state = arguments.get("state")
                if not isinstance(raw_state, dict):
                    raise ConnectorExecutionError(
                        "CONNECTOR_REGISTRY_ARGUMENTS_INVALID"
                    )
                state = deserialize_state(raw_state, questions)
                step = advance(state, arguments.get("answer"))
            elif operation == "transcript":
                raw_state = arguments.get("state")
                if not isinstance(raw_state, dict):
                    raise ConnectorExecutionError(
                        "CONNECTOR_REGISTRY_ARGUMENTS_INVALID"
                    )
                state = deserialize_state(raw_state, questions)
                return {"transcript": transcript(state), "state": serialize_state(state)}
            else:
                raise ConnectorExecutionError(
                    "CONNECTOR_REGISTRY_OPERATION_NOT_ALLOWED"
                )
        except ConnectorExecutionError:
            raise
        except (TypeError, ValueError, OverflowError) as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_ARGUMENTS_INVALID"
            ) from exc
        return {
            "complete": step.complete,
            "next_question": (
                asdict(step.next_question) if step.next_question is not None else None
            ),
            "skipped_keys": list(step.skipped_keys),
            "state": serialize_state(step.state),
        }

    async def _medical_coding(
        self, invocation: ConnectorInvocation,
    ) -> dict[str, Any]:
        if self._app is None:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ADAPTER_NOT_CONFIGURED")
        from jsonschema import ValidationError, validators

        from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload
        from app.icoder.mcp.server import resolve_handler
        from app.icoder.mcp.tool_registry import TOOL_REGISTRY

        descriptor = TOOL_REGISTRY.get(invocation.operation)
        if descriptor is None:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_OPERATION_NOT_ALLOWED")
        required_scopes = frozenset(descriptor.required_scopes)
        if required_scopes and not required_scopes.issubset(
            invocation.granted_scopes
        ):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_SCOPE_FORBIDDEN")
        try:
            input_validator = validators.validator_for(descriptor.input_schema)
            input_validator.check_schema(descriptor.input_schema)
            safe_arguments = redact_payload(dict(invocation.arguments)).value
            input_validator(descriptor.input_schema).validate(safe_arguments)
        except ValidationError as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_ARGUMENTS_INVALID"
            ) from exc
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_ARGUMENTS_INVALID"
            ) from exc
        try:
            request = SimpleNamespace(
                app=self._app,
                state=SimpleNamespace(
                    context_id=invocation.task_id or "",
                    run_id=invocation.run_id or "",
                ),
            )
            result = resolve_handler(descriptor.handler_ref)(safe_arguments, request)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, dict):
                raise ConnectorExecutionError("CONNECTOR_RESPONSE_INVALID")
        except ConnectorExecutionError:
            raise
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_EXECUTION_FAILED"
            ) from exc
        try:
            output_validator = validators.validator_for(descriptor.output_schema)
            output_validator.check_schema(descriptor.output_schema)
            output_validator(descriptor.output_schema).validate(result)
            return result
        except ConnectorExecutionError:
            raise
        except ValidationError as exc:
            raise ConnectorExecutionError("CONNECTOR_RESPONSE_INVALID") from exc
        except Exception as exc:
            raise ConnectorExecutionError("CONNECTOR_RESPONSE_INVALID") from exc

    def status(self) -> dict[str, object]:
        return {
            "local_keys": sorted(LOCAL_REGISTRY_KEYS),
            "public_keys": sorted(PUBLIC_REGISTRY_KEYS),
            "externally_gated_keys": sorted(EXTERNALLY_GATED_REGISTRY_KEYS),
            "public_provider": (
                self._public_registry_provider.status()
                if self._public_registry_provider is not None
                else {"configured": False}
            ),
            "external_provider": (
                self._external_registry_provider.status()
                if self._external_registry_provider is not None
                else {"configured": False}
            ),
            "memory_store": (
                self._memory_store.status()
                if self._memory_store is not None
                and hasattr(self._memory_store, "status")
                else {"configured": False}
            ),
        }


class GovernedInternalAgentAdapter:
    """Execute a tenant-owned target Agent with bounded recursive delegation."""

    def __init__(self, app: Any, *, handler: Any | None = None) -> None:
        self._app = app
        self._handler = handler

    def _get_handler(self):
        if self._handler is None:
            from app.icoder.agent_runtime.provider_a2a_handler import ProviderA2AHandler

            official_agents = Path(__file__).resolve().parents[2] / "official_agents"
            self._handler = ProviderA2AHandler(official_agents)
        return self._handler

    async def __call__(
        self,
        _db: AsyncSession,
        _connector: AgentConnector,
        invocation: ConnectorInvocation,
        target_agent_id: str,
    ) -> dict[str, Any]:
        if invocation.operation not in INTERNAL_AGENT_OPERATIONS:
            raise ConnectorExecutionError("CONNECTOR_AGENT_OPERATION_NOT_ALLOWED")
        reserved = {
            str(key) for key in invocation.arguments if str(key).startswith("_")
        }
        if reserved - set(invocation.trusted_server_channels):
            raise ConnectorExecutionError("CONNECTOR_AGENT_ARGUMENTS_FORBIDDEN")

        current = _agent_call_chain.get()
        chain = current or (invocation.agent_id,)
        if target_agent_id in chain:
            raise ConnectorExecutionError("CONNECTOR_AGENT_RUNTIME_CYCLE")
        if len(chain) >= MAX_INTERNAL_AGENT_DEPTH:
            raise ConnectorExecutionError("CONNECTOR_AGENT_RUNTIME_DEPTH_EXCEEDED")
        token = _agent_call_chain.set((*chain, target_agent_id))
        child_run_id = f"run-{uuid.uuid4()}"
        context_id = f"ctx-{uuid.uuid4()}"
        try:
            text = invocation.arguments.get("text", "")
            if not isinstance(text, str) or len(text) > 20_000:
                raise ConnectorExecutionError("CONNECTOR_AGENT_ARGUMENTS_INVALID")
            data = dict(invocation.arguments)
            data.pop("text", None)
            if "_dependencies" in data:
                data["connector_dependencies"] = data.pop("_dependencies")
            parts: list[dict[str, Any]] = []
            if text.strip():
                parts.append({"kind": "text", "text": text})
            if data:
                parts.append({"kind": "data", "data": data})
            if not parts:
                raise ConnectorExecutionError("CONNECTOR_AGENT_ARGUMENTS_INVALID")
            request = InboundRequest(
                message=InboundMessage(
                    role="user",
                    parts=parts,
                    interaction_id=f"connector-{uuid.uuid4()}",
                    context_id=context_id,
                ),
                metadata={
                    "organization_id": invocation.organization_id,
                    "run_id": child_run_id,
                    "trace_id": invocation.run_id or child_run_id,
                    "parent_run_id": invocation.run_id,
                    "connector_source_agent_id": invocation.agent_id,
                    "connector_call_depth": len(chain),
                },
                runtime_request=SimpleNamespace(app=self._app),
            )
            handler = self._get_handler()
            response = handler.handle_async(target_agent_id, request)
            if inspect.isawaitable(response):
                response = await response
            if getattr(response, "kind", "error") == "error":
                raw_code = str((getattr(response, "error", None) or {}).get("code") or "")
                mapping = {
                    "AGENT_NOT_FOUND": "CONNECTOR_TARGET_AGENT_NOT_FOUND",
                    "PROVIDER_UNAVAILABLE": "CONNECTOR_AGENT_PROVIDER_UNAVAILABLE",
                    "OUTPUT_CONTRACT_VIOLATION": "CONNECTOR_AGENT_OUTPUT_INVALID",
                    "RESULT_ATTESTATION_FAILED": "CONNECTOR_AGENT_OUTPUT_INVALID",
                }
                raise ConnectorExecutionError(
                    mapping.get(raw_code, "CONNECTOR_AGENT_EXECUTION_FAILED"),
                    retryable=raw_code in {"PROVIDER_UNAVAILABLE", "PROVIDER_EXECUTION_FAILED"},
                )
            parts_out = getattr(response, "parts", None)
            metadata = getattr(response, "metadata", None)
            if not isinstance(parts_out, list) or not isinstance(metadata, dict):
                raise ConnectorExecutionError("CONNECTOR_AGENT_OUTPUT_INVALID")
            return {
                "target_agent_id": target_agent_id,
                "child_run_id": child_run_id,
                "status": "completed",
                "parts": parts_out,
                "result_attestation": metadata.get("result_attestation"),
                "manual_review_required": bool(
                    metadata.get("manual_review_required", True)
                ),
            }
        finally:
            _agent_call_chain.reset(token)

    @staticmethod
    def status() -> dict[str, object]:
        return {
            "operations": sorted(INTERNAL_AGENT_OPERATIONS),
            "max_depth": MAX_INTERNAL_AGENT_DEPTH,
            "cycle_guard": True,
        }


__all__ = [
    "EXTERNALLY_GATED_REGISTRY_KEYS",
    "GovernedInternalAgentAdapter",
    "GovernedRegistryAdapter",
    "INTERNAL_AGENT_OPERATIONS",
    "LOCAL_REGISTRY_KEYS",
    "MAX_INTERNAL_AGENT_DEPTH",
    "PUBLIC_REGISTRY_KEYS",
]
