from __future__ import annotations

import hashlib

from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundMessage,
    InboundRequest,
    InboundResponse,
)
from app.icoder.agent_runtime.tenant_clone_a2a_dispatch_handler import (
    TenantCloneA2ADispatchHandler,
)
from app.services.agent_runtime_pack import TenantRuntimeResolution
from app.services.dedicated_project_policy import DedicatedProjectPolicy


def _request() -> InboundRequest:
    return InboundRequest(
        message=InboundMessage(
            context_id="ctx-1",
            parts=[{"kind": "text", "text": "synthetic de-identified input"}],
        ),
        metadata={
            "organization_id": "org_default1",
            "run_id": "run-clone-a2a-unit",
            "trace_id": "trace-clone-a2a-unit",
        },
    )


def _resolution(
    prompt: str,
    *,
    project_runtime: dict | None = None,
) -> TenantRuntimeResolution:
    return TenantRuntimeResolution(
        requested_agent_id="project12345",
        runtime_agent_id="medical-coding-agent",
        db_agent=None,
        pack={
            "system_prompt": prompt,
            "output_contract": {"schema_ref": "icoder/MedicalCodingAgentOutputV2/v8"},
            "project_runtime": project_runtime or {},
        },
        is_clone=True,
        source_agent_ref="icoder/medical-coding-agent@2.0.0",
    )


def test_dedicated_clone_success_is_remapped_and_resigned(monkeypatch) -> None:
    from app.icoder.agent_runtime import tenant_clone_a2a_dispatch_handler as module

    source_prompt = "source prompt"

    async def fake_resolve(agent_id: str, tenant_id: str):
        assert agent_id == "project12345"
        assert tenant_id == "org_default1"
        return _resolution(source_prompt)

    async def fake_attribute(**kwargs):
        assert kwargs["project_agent_id"] == "project12345"
        assert kwargs["source_runtime_agent_id"] == "medical-coding-agent"

    monkeypatch.setattr(
        TenantCloneA2ADispatchHandler, "_resolve", staticmethod(fake_resolve)
    )
    monkeypatch.setattr(
        TenantCloneA2ADispatchHandler,
        "_attribute_run",
        staticmethod(fake_attribute),
    )
    monkeypatch.setattr(
        module,
        "issue_result_attestation",
        lambda **kwargs: (
            f"proof:{kwargs['agent_id']}:{kwargs['schema_ref']}"
        ),
    )

    class Inner:
        def handle(self, agent_id, request):
            assert agent_id == "medical-coding-agent"
            return InboundResponse(
                kind="message",
                context_id="ctx-1",
                parts=[{"kind": "data", "data": {"coding_results": []}}],
                metadata={"run_id": "run-clone-a2a-unit"},
            )

    response = TenantCloneA2ADispatchHandler(Inner()).handle(
        "project12345", _request()
    )
    assert response.kind == "message"
    assert response.metadata["agent_id"] == "project12345"
    assert response.metadata["source_runtime_agent_id"] == "medical-coding-agent"
    assert response.metadata["result_attestation"].startswith(
        "proof:project12345:"
    )
    part_metadata = response.parts[0]["metadata"]
    assert part_metadata["schema_ref"] == "icoder/MedicalCodingAgentOutputV2/v8"
    assert part_metadata["result_attestation"] == response.metadata[
        "result_attestation"
    ]


def test_dedicated_clone_prompt_override_uses_verified_internal_policy_token(
    monkeypatch,
) -> None:
    from app.icoder.agent_runtime import tenant_clone_a2a_dispatch_handler as module

    sentinel = "PROJECT_POLICY_SENTINEL: prefer explicit chart evidence."
    digest = hashlib.sha256(sentinel.encode("utf-8")).hexdigest()

    async def fake_resolve(agent_id: str, tenant_id: str):
        return _resolution(
            "project override",
            project_runtime={
                "dedicated_project_policy": sentinel,
                "dedicated_project_policy_digest": digest,
                "project_prompt_overridden": True,
                "project_expert_ids": ["expert-project-1"],
                "dedicated_source_experts_fixed": True,
            },
        )

    async def fake_attribute(**kwargs):
        assert kwargs["project_agent_id"] == "project12345"

    monkeypatch.setattr(
        TenantCloneA2ADispatchHandler, "_resolve", staticmethod(fake_resolve)
    )
    monkeypatch.setattr(
        TenantCloneA2ADispatchHandler,
        "_attribute_run",
        staticmethod(fake_attribute),
    )
    monkeypatch.setattr(module, "issue_result_attestation", lambda **kwargs: "proof")

    class Inner:
        def handle(self, agent_id, request):
            assert agent_id == "medical-coding-agent"
            token = request.metadata.get("_dedicated_project_policy_token")
            assert isinstance(token, DedicatedProjectPolicy)
            assert token.instructions == sentinel
            assert token.digest == digest
            return InboundResponse(
                kind="message",
                context_id="ctx-1",
                parts=[{"kind": "text", "text": "safe synthetic result"}],
                metadata={"run_id": "run-clone-a2a-unit"},
            )

    response = TenantCloneA2ADispatchHandler(Inner()).handle(
        "project12345", _request()
    )
    assert response.kind == "message"
    assert response.metadata["agent_id"] == "project12345"
    assert response.metadata["project_policy_digest"] == digest
    assert response.metadata["project_prompt_overridden"] is True
    assert response.metadata["project_expert_ids"] == ["expert-project-1"]
    assert response.metadata["dedicated_source_experts_fixed"] is True
    assert sentinel not in str(response.metadata)


def test_dedicated_clone_rejects_tampered_policy_before_source_dispatch(
    monkeypatch,
) -> None:
    async def fake_resolve(agent_id: str, tenant_id: str):
        return _resolution(
            "project override",
            project_runtime={
                "dedicated_project_policy": "tampered policy",
                "dedicated_project_policy_digest": "not-the-real-digest",
            },
        )

    monkeypatch.setattr(
        TenantCloneA2ADispatchHandler, "_resolve", staticmethod(fake_resolve)
    )

    class Inner:
        def handle(self, agent_id, request):  # pragma: no cover - must not run
            raise AssertionError("tampered dedicated policy reached source runtime")

    response = TenantCloneA2ADispatchHandler(Inner()).handle(
        "project12345", _request()
    )
    assert response.kind == "error"
    assert response.error["code"] == "CLONE_DEDICATED_POLICY_INVALID"
    assert response.metadata["agent_id"] == "project12345"
