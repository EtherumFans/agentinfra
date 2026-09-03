from __future__ import annotations

import pytest

from icoder_runtime.backends.contracts import AgentRunContext, BackendRequest
from icoder_runtime.backends.governed_evidence_extractor_provider import (
    GovernedEvidenceExtractorProvider,
)


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        run_id="run-evidence-extractor",
        context_id="context-evidence-extractor",
        agent_id="evidence-extractor",
        redacted_input="",
        agent_pack={"output_contract": {"schema_ref": "icoder/CodedEvidence/v11"}},
    )


@pytest.mark.asyncio
async def test_health_is_local_and_does_not_claim_clinical_support() -> None:
    health = await GovernedEvidenceExtractorProvider().health()
    assert health.state == "ok"
    assert health.details["network_required"] is False
    assert health.details["llm_required"] is False
    assert health.details["clinical_support_assessed"] is False
    assert health.details["integrity_verified"] is True


@pytest.mark.asyncio
async def test_invoke_returns_strict_public_candidate_and_zero_cost() -> None:
    response = await GovernedEvidenceExtractorProvider().invoke(
        BackendRequest(input={
            "text": "待核查编码：N18.803。\n病历文本：慢性肾脏病3期。"
        }),
        _ctx(),
    )

    assert response.status == "requires_review"
    assert response.finish_state == "completed"
    assert response.backend_provider == "icoder.governed-evidence-extractor.v1"
    assert response.backend_type == "rule_engine"
    assert response.cost_usd == 0.0
    assert response.raw_provider_response["match_basis"] == (
        "EXACT_CATALOG_TERM_OR_CODE_LITERAL_ONLY"
    )
    assert response.raw_provider_response["located_mentions"][0][
        "clinical_support_assessed"
    ] is False


@pytest.mark.asyncio
async def test_invoke_empty_input_is_input_required_not_synthetic_success() -> None:
    response = await GovernedEvidenceExtractorProvider().invoke(
        BackendRequest(input={"text": "无候选编码。"}), _ctx()
    )
    assert response.status == "incomplete"
    assert response.finish_state == "input-required"
    assert response.finish_reason == "explicit_candidate_codes_required"
    assert response.raw_provider_response["located_mentions"] == []


def test_capabilities_are_deterministic_and_tool_free() -> None:
    provider = GovernedEvidenceExtractorProvider()
    capability = provider.capabilities()
    assert provider.output_contract() == "icoder/CodedEvidence/v11"
    assert capability.backend_type == "rule_engine"
    assert capability.deterministic is True
    assert capability.supports_tool_calling is False
    assert capability.supported_tools == []
