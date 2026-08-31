from __future__ import annotations

import json

import pytest

from icoder_runtime.backends.contracts import AgentRunContext, BackendRequest
from icoder_runtime.backends.governed_procedure_extractor_provider import (
    GovernedProcedureExtractorProvider,
)
from official_agents.procedure_extractor.agent import (
    extract_procedures,
    to_pack_output,
)


EXAMPLE = (
    "患者男性,78岁,因 T12 椎体压缩性骨折行 T12 椎体切开复位内固定术,"
    "手术顺利,术后恢复良好。"
)


def _ctx(text: str = EXAMPLE) -> AgentRunContext:
    return AgentRunContext(
        run_id="run-procedure-extractor",
        context_id="context-procedure-extractor",
        agent_id="procedure-extractor",
        redacted_input=text,
        agent_pack={
            "output_contract": {"schema_ref": "icoder/ProcedureCodingOutput/v8"}
        },
    )


def test_explicit_t12_procedure_maps_to_actual_pinned_catalog_entry() -> None:
    result = to_pack_output(extract_procedures(EXAMPLE))

    assert result["total_count"] == 1
    item = result["procedures"][0]
    assert item["code"] == "03.5304"
    assert item["code"] != "81.0100"
    assert item["display"] == "胸椎骨折切开复位内固定术"
    assert item["status"] == "performed"
    assert item["evidence_text"] == "行 T12 椎体切开复位内固定术"
    assert item["char_span"] == [22, 38]
    start, end = item["char_span"]
    assert EXAMPLE[start:end] == item["evidence_text"]
    assert "source_unverified" in " ".join(item["warnings"])
    assert result["manual_review_required"] is True


def test_unique_lexical_catalog_match_is_bounded_and_review_only() -> None:
    text = "手术记录：全麻下行腹腔镜胆囊切除术，术中顺利。"
    result = to_pack_output(extract_procedures(text))

    item = result["procedures"][0]
    assert item["code"] == "51.2300"
    assert item["display"] == "腹腔镜下胆囊切除术"
    assert item["confidence"] == 0.9
    assert any("不代表临床适用性" in warning for warning in item["warnings"])


def test_planned_then_cancelled_is_never_promoted_to_performed() -> None:
    text = (
        "病程记录：原拟行腹腔镜胆囊切除术，因患者拒绝已取消，"
        "本次住院未实施任何手术或操作。"
    )
    result = to_pack_output(extract_procedures(text))

    assert result["procedures"] == []
    assert result["total_count"] == 0
    assert result["non_billable_mentions"] == [{
        "text": "腹腔镜胆囊切除术",
        "status": "cancelled",
        "evidence_text": "原拟行腹腔镜胆囊切除术",
        "char_span": [5, 16],
    }]
    assert result["issues_found"]


def test_historical_mention_is_not_reclassified_by_current_negation() -> None:
    result = to_pack_output(extract_procedures("既往曾行阑尾切除术，本次未行手术。"))

    assert result["procedures"] == []
    assert result["non_billable_mentions"][0]["status"] == "historical"


def test_unmapped_performed_procedure_preserves_span_without_guessing_code() -> None:
    text = "手术记录：已行自定义试验性操作术。"
    result = to_pack_output(extract_procedures(text))

    item = result["procedures"][0]
    assert item["code"] == ""
    assert item["display"] == "自定义试验性操作术"
    assert item["confidence"] == 0.0
    assert text[slice(*item["char_span"])] == item["evidence_text"]
    assert any(issue["category"] == "procedure_code_unresolved" for issue in result["issues_found"])


@pytest.mark.asyncio
async def test_provider_returns_zero_cost_current_pack_candidate() -> None:
    provider = GovernedProcedureExtractorProvider()
    response = await provider.invoke(
        BackendRequest(input={"text": EXAMPLE}),
        _ctx(),
    )
    public = json.loads(response.markdown)

    assert response.status == "requires_review"
    assert response.finish_state == "completed"
    assert response.backend_provider == provider.provider_id
    assert response.backend_type == "rule_engine"
    assert response.cost_usd == 0.0
    assert public["procedures"][0]["code"] == "03.5304"
    assert "_catalog_governance" not in public


@pytest.mark.asyncio
async def test_empty_input_requires_source_and_never_succeeds_synthetically() -> None:
    provider = GovernedProcedureExtractorProvider()
    response = await provider.invoke(
        BackendRequest(input={"text": ""}),
        _ctx(""),
    )

    assert response.status == "incomplete"
    assert response.finish_state == "input-required"
    assert response.finish_reason == "procedure_source_required"
    assert response.raw_provider_response["procedures"] == []


@pytest.mark.asyncio
async def test_health_discloses_unverified_local_catalog_boundary() -> None:
    provider = GovernedProcedureExtractorProvider()
    health = await provider.health()
    capability = provider.capabilities()

    assert health.state == "ok"
    assert health.details["network_required"] is False
    assert health.details["llm_required"] is False
    assert health.details["authority_status"] == "source_unverified"
    assert health.details["license_status"] == "external_review_required"
    assert health.details["billing_authoritative"] is False
    assert capability.deterministic is True
    assert capability.default_output_contract == "icoder/ProcedureCodingOutput/v8"
