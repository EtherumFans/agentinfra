from __future__ import annotations

import json

import pytest

from icoder_runtime.backends.contracts import AgentRunContext, BackendRequest
from icoder_runtime.backends.governed_code_validation_provider import (
    GovernedCodeValidationProvider,
)


@pytest.mark.asyncio
async def test_provider_invokes_public_contract_without_external_llm(monkeypatch):
    provider = GovernedCodeValidationProvider()

    async def governed_run(*_args, **_kwargs):
        return {
            "review_conclusion": "WARNING",
            "validated_codes": [{
                "code": "I50.900",
                "status": "valid",
                "in_catalog": True,
                "assignable": True,
                "catalog_name": "心力衰竭",
                "issue": "development catalog only",
                "suggested_replacement": "",
            }],
            "cross_code_issues": [{
                "code": "catalog",
                "issue": "manual review",
                "severity": "warning",
                "manual_review_required": True,
            }],
            "manual_review_required": True,
            "summary": "catalog baseline",
            "markdown": "catalog baseline",
            "runtime_mode": "governed_local_catalog_baseline",
            "trace_refs": {
                "catalog_integrity_verified": True,
                "catalog_asset_ids": ["cn.icd10cn.catalog"],
                "catalog_asset_versions": ["test-v1"],
                "catalog_authority_statuses": ["source_unverified"],
                "catalog_license_statuses": ["external_review_required"],
                "semantic_enhancement_used": False,
            },
        }

    monkeypatch.setattr(
        "official_agents.code_validation.agent.run",
        governed_run,
    )
    monkeypatch.setattr(provider, "_emit_backend_metadata", lambda *_args: None)
    response = await provider.invoke(
        BackendRequest(input={"text": "待校验 I50.900"}),
        AgentRunContext(
            run_id="run-provider",
            context_id="ctx-provider",
            agent_id="code-validation-agent",
            redacted_input="待校验 I50.900",
            agent_pack={
                "manifest": {"human_review": "required"},
                "output_contract": {"schema_ref": "icoder/CodeValidationOutput/v7"},
            },
        ),
    )
    assert response.status == "requires_review"
    assert response.backend_provider == provider.provider_id
    assert response.backend_type == "hybrid"
    assert response.cost_usd == 0.0
    assert response.finish_state == "completed"
    public = json.loads(response.markdown)
    assert public["validated_codes"][0]["status"] == "valid"
    assert public["manual_review_required"] is True


@pytest.mark.asyncio
async def test_provider_health_exposes_only_bounded_catalog_evidence(monkeypatch):
    provider = GovernedCodeValidationProvider()
    monkeypatch.setattr(
        "official_agents.code_validation.catalog_validation.verify_catalog_health",
        lambda: {
            "integrity_verified": True,
            "assets": [{
                "asset_id": "cn.icd10cn.catalog",
                "version": "test-v1",
            }],
            "catalog_counts": {"ICD-10-CN": 3},
        },
    )
    health = await provider.health()
    assert health.state == "ok"
    assert health.details["integrity_verified"] is True
    assert health.details["asset_ids"] == ["cn.icd10cn.catalog"]
    assert "loaded_from" not in health.details
