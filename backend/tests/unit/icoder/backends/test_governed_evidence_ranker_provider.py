from __future__ import annotations

import json

import pytest

from icoder_runtime.backends.contracts import AgentRunContext, BackendRequest
from icoder_runtime.backends.governed_evidence_ranker_provider import (
    GovernedEvidenceRankerProvider,
)


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        run_id="run-evidence-ranker",
        context_id="context-evidence-ranker",
        agent_id="evidence-ranker",
        redacted_input="",
        agent_pack={
            "output_contract": {"schema_ref": "icoder/EvidenceRankerOutput/v4"}
        },
    )


@pytest.mark.asyncio
async def test_health_is_local_and_does_not_claim_clinical_support() -> None:
    health = await GovernedEvidenceRankerProvider().health()
    assert health.state == "ok"
    assert health.details["network_required"] is False
    assert health.details["llm_required"] is False
    assert health.details["clinical_support_assessed"] is False
    assert health.details["policy_version"] == "1.0.0"


@pytest.mark.asyncio
async def test_invoke_returns_strict_public_candidate_and_zero_cost() -> None:
    payload = {
        "candidate_code": "I21.0",
        "evidence_items": [{
            "evidence_id": "A", "source": "入院记录", "content": "I21.0 记录片段"
        }],
    }
    response = await GovernedEvidenceRankerProvider().invoke(
        BackendRequest(input={"text": json.dumps(payload, ensure_ascii=False)}),
        _ctx(),
    )
    assert response.status == "requires_review"
    assert response.finish_state == "completed"
    assert response.backend_provider == "icoder.governed-evidence-ranker.v1"
    assert response.backend_type == "rule_engine"
    assert response.cost_usd == 0.0
    assert response.raw_provider_response["ranking_basis"] == "DOCUMENTATION_GROUNDING_ONLY"
    assert response.raw_provider_response["ranked_evidence"][0]["lexical_code_mention"] is True


@pytest.mark.asyncio
async def test_invoke_empty_input_is_input_required_not_synthetic_success() -> None:
    response = await GovernedEvidenceRankerProvider().invoke(
        BackendRequest(input={"text": ""}), _ctx()
    )
    assert response.status == "incomplete"
    assert response.finish_state == "input-required"
    assert response.finish_reason == "explicit_evidence_items_required"
    assert response.raw_provider_response["ranked_evidence"] == []


def test_capabilities_are_deterministic_and_tool_free() -> None:
    provider = GovernedEvidenceRankerProvider()
    capability = provider.capabilities()
    assert provider.output_contract() == "icoder/EvidenceRankerOutput/v4"
    assert capability.backend_type == "rule_engine"
    assert capability.deterministic is True
    assert capability.supports_tool_calling is False
    assert capability.supported_tools == []
