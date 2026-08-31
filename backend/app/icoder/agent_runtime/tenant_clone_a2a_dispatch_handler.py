"""A2A dispatch bridge for tenant clones of dedicated clinical runtimes.

Provider-backed clones are executed by :class:`ProviderA2AHandler` using their
effective project Pack. Medical Coding and CDI have no registry Provider; this
wrapper resolves their immutable source implementation, delegates to the same
dedicated handler as the official Agent, then restores project identity for
the response, result proof, RunHistory and subsequent Trace lookup.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import app.database as database
from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundRequest,
    InboundResponse,
    extract_text_from_parts,
    make_run_id,
)
from app.services.agent_runtime_pack import (
    CloneRuntimeConfigurationError,
    TenantRuntimeResolution,
    resolve_tenant_runtime,
)
from app.services.dedicated_project_policy import (
    DedicatedProjectPolicy,
    policy_from_runtime_pack,
)
from app.services.result_attestation import issue_result_attestation


logger = logging.getLogger(__name__)

_DEDICATED_NO_PROVIDER_IDS = frozenset({
    "medical-coding-agent",
    "clinical-documentation-improvement-agent",
})


class TenantCloneA2ADispatchHandler:
    """Delegate dedicated source runtimes without losing project ownership."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def handle(self, agent_id: str, request: InboundRequest) -> InboundResponse:
        tenant_id = str(
            request.metadata.get("organization_id")
            or request.metadata.get("tenant_id")
            or "default"
        )
        try:
            resolution = asyncio.run(self._resolve(agent_id, tenant_id))
        except CloneRuntimeConfigurationError as exc:
            return self._error(agent_id, request, exc.code, exc.public_message)

        if (
            not resolution.is_clone
            or resolution.runtime_agent_id not in _DEDICATED_NO_PROVIDER_IDS
        ):
            return self._inner.handle(agent_id, request)

        assert resolution.pack is not None
        try:
            policy = policy_from_runtime_pack(resolution.pack)
        except ValueError:
            return self._error(
                agent_id,
                request,
                "clone_dedicated_policy_invalid",
                "The dedicated project policy could not be verified safely.",
            )

        request.metadata["project_agent_id"] = agent_id
        request.metadata["source_runtime_agent_id"] = resolution.runtime_agent_id
        request.metadata["_dedicated_project_policy_token"] = policy
        response = self._inner.handle(resolution.runtime_agent_id, request)
        try:
            self._remap_response(
                response,
                project_agent_id=agent_id,
                source_runtime_agent_id=resolution.runtime_agent_id,
                tenant_id=tenant_id,
                pack=resolution.pack,
                policy=policy,
            )
            asyncio.run(
                self._attribute_run(
                    response=response,
                    request=request,
                    project_agent_id=agent_id,
                    source_runtime_agent_id=resolution.runtime_agent_id,
                    tenant_id=tenant_id,
                )
            )
        except Exception as exc:
            logger.error(
                "Dedicated clone A2A remap failed agent_id=%s error_type=%s",
                agent_id,
                type(exc).__name__,
            )
            return self._error(
                agent_id,
                request,
                "clone_result_attribution_failed",
                "The dedicated Agent result could not be attributed to the project safely.",
            )
        return response

    @staticmethod
    async def _resolve(agent_id: str, tenant_id: str) -> TenantRuntimeResolution:
        async with database.AsyncSessionLocal() as db:
            return await resolve_tenant_runtime(agent_id, tenant_id, db)

    @staticmethod
    def _remap_response(
        response: InboundResponse,
        *,
        project_agent_id: str,
        source_runtime_agent_id: str,
        tenant_id: str,
        pack: dict[str, Any],
        policy: DedicatedProjectPolicy,
    ) -> None:
        metadata = dict(response.metadata or {})
        metadata["agent_id"] = project_agent_id
        metadata["source_runtime_agent_id"] = source_runtime_agent_id
        metadata.update(policy.safe_metadata())
        response.metadata = metadata
        if response.kind == "error" or response.error:
            return

        schema_ref = str((pack.get("output_contract") or {}).get("schema_ref") or "")
        run_id = str(metadata.get("run_id") or "")
        for part in response.parts or []:
            if not isinstance(part, dict):
                continue
            part_kind = part.get("kind") or part.get("type")
            data = part.get("data")
            if part_kind != "data" or not isinstance(data, dict) or not schema_ref:
                continue
            proof = issue_result_attestation(
                run_id=run_id,
                agent_id=project_agent_id,
                schema_ref=schema_ref,
                organization_id=tenant_id,
                result=data,
            )
            part_metadata = dict(part.get("metadata") or {})
            part_metadata["schema_ref"] = schema_ref
            part_metadata["result_attestation"] = proof
            part["metadata"] = part_metadata
            response.metadata["output_contract"] = schema_ref
            response.metadata["result_attestation"] = proof

    @staticmethod
    async def _attribute_run(
        *,
        response: InboundResponse,
        request: InboundRequest,
        project_agent_id: str,
        source_runtime_agent_id: str,
        tenant_id: str,
    ) -> None:
        from app.services.run_lifecycle import (
            RunStatus,
            get_run_status,
            record_run_start,
            set_status,
        )

        run_id = str(
            (response.metadata or {}).get("run_id")
            or request.metadata.get("run_id")
            or make_run_id()
        )
        trace_id = str(
            request.metadata.get("trace_id")
            or (response.metadata or {}).get("trace_id")
            or run_id
        )
        safe_input = extract_text_from_parts(request.message.parts)
        async with database.AsyncSessionLocal() as db:
            row = await get_run_status(db, run_id=run_id)
            if row is not None and row.organization_id not in {None, tenant_id}:
                raise RuntimeError("run tenancy mismatch")
            if row is None:
                row = await record_run_start(
                    db,
                    run_id=run_id,
                    trace_id=trace_id,
                    agent_id=project_agent_id,
                    organization_id=tenant_id,
                    input_text=safe_input,
                    runtime_mode="a2a_dedicated_project_clone",
                    context_id=request.message.context_id or None,
                )
            row.agent_id = project_agent_id
            row.organization_id = tenant_id
            row.runtime_mode = str(
                (response.metadata or {}).get("runtime_mode")
                or row.runtime_mode
                or "a2a_dedicated_project_clone"
            )
            row.output_summary = str(
                (response.metadata or {}).get("summary")
                or f"Dedicated runtime {source_runtime_agent_id} completed for project clone."
            )[:4096]
            failed = response.kind == "error" or bool(response.error)
            await set_status(
                db,
                run_id=run_id,
                status=RunStatus.FAILED if failed else RunStatus.COMPLETED,
                extra_fields={
                    "error": failed,
                    "error_reason": (
                        str((response.error or {}).get("code") or "runtime_error")
                        if failed
                        else None
                    ),
                },
            )
            await db.commit()

    @staticmethod
    def _error(
        agent_id: str,
        request: InboundRequest,
        code: str,
        message: str,
    ) -> InboundResponse:
        return InboundResponse(
            kind="error",
            context_id=request.message.context_id,
            metadata={
                "run_id": str(request.metadata.get("run_id") or make_run_id()),
                "agent_id": agent_id,
                "phi_redacted": True,
                "production_writeback_blocked": True,
            },
            error={"code": code.upper(), "message": message},
            http_status=422,
            redacted_input=extract_text_from_parts(request.message.parts),
        )


__all__ = ["TenantCloneA2ADispatchHandler"]
