from __future__ import annotations

import json

import pytest

from icoder_runtime.backends.contracts import AgentRunContext, BackendRequest
from icoder_runtime.backends.governed_icd_navigator_provider import (
    GovernedICDNavigatorProvider,
)


def _context() -> AgentRunContext:
    return AgentRunContext(
        run_id="run-navigator-provider",
        context_id="context-navigator-provider",
        agent_id="icd10-navigator",
        redacted_input="慢性肾脏病3期",
        agent_pack={
            "output_contract": {
                "schema_ref": "icoder/Icd10NavigatorOutput/v4",
            },
        },
    )


@pytest.mark.asyncio
async def test_health_verifies_catalog_and_term_index() -> None:
    health = await GovernedICDNavigatorProvider().health()

    assert health.state == "ok"
    assert health.details["integrity_verified"] is True
    assert health.details["catalog_count"] == 37897
    assert health.details["term_index_count"] == 56424
    assert health.details["asset_id"] == "cn.icd10cn.catalog"
    assert "loaded_from" not in health.details


@pytest.mark.asyncio
async def test_invoke_returns_zero_cost_strict_public_json(monkeypatch) -> None:
    provider = GovernedICDNavigatorProvider()
    monkeypatch.setattr(provider, "_emit_backend_metadata", lambda *args: None)
    response = await provider.invoke(
        BackendRequest(
            input={"text": "诊断表述：慢性肾脏病3期。"},
            user_input="诊断表述：慢性肾脏病3期。",
        ),
        _context(),
    )

    assert response.status == "requires_review"
    assert response.finish_state == "completed"
    assert response.cost_usd == 0.0
    assert response.backend_provider == "icoder.governed-icd-navigator.v1"
    assert response.backend_type == "rule_engine"
    public = json.loads(response.markdown)
    assert public["search_status"] == "CANDIDATES_FOUND"
    assert public["candidate_codes"][0]["code"] == "N18.803"
    assert public["manual_review_required"] is True
    assert "catalog_governance" not in public
    assert response.raw_provider_response["catalog_governance"][
        "integrity_verified"
    ] is True


def test_capabilities_are_local_deterministic_and_non_tool_calling() -> None:
    provider = GovernedICDNavigatorProvider()
    capability = provider.capabilities()

    assert provider.output_contract() == "icoder/Icd10NavigatorOutput/v4"
    assert capability.backend_type == "rule_engine"
    assert capability.deterministic is True
    assert capability.supports_tool_calling is False
    assert capability.supported_tools == []
