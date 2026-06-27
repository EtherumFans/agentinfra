"""M2 — MCP handler tests (~10 cases).

Each handler is a 1:1 thin wrapper around an existing service:
  - search_icd → MedCodERStrategy.stage2_retrieve
  - verify_code → icd10cn_loader
  - get_differentiation_hint → coding_differentiation_kb.json
  - rerank_codes → MedCodERStrategy.stage4_rerank
  - calibrate_confidence → confidence_calibrator.calibrate_all

These tests verify the wrapper logic with stub services / data; they
do NOT hit real BGE-M3, real LLM, or real catalog files (those are
integration concerns covered by e2e_medcoder_validation.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# All tests in this module are async; project uses pytest-asyncio strict mode.
pytestmark = pytest.mark.asyncio


# ── Fixtures ──


@pytest.fixture
def mock_request() -> MagicMock:
    """Stub ``Request`` with ``app.state.medcoder_strategy`` + app.state.phi_redactor=None.

    M2.5: also set ``app.state.medcoder_index_health`` to a healthy report
    so the search_icd handler's governance gate doesn't raise
    ``-32002 Retriever Unavailable`` for handler unit tests.

    E1.1 (2026-06-26): ``stage2_retrieve`` returns ``Stage2Result`` envelope
    (candidates + degraded + error_code). The default mock returns an
    empty Stage2Result (candidates=[], degraded=False, is_ok=True).
    Individual tests can override the mock to return a populated result.
    """
    from icoder_runtime.providers.medical_coding.medcoder_strategy import (
        Stage2Result,
    )

    req = MagicMock()
    app_state = MagicMock()
    strategy = MagicMock()
    strategy.stage2_retrieve = AsyncMock(return_value=Stage2Result(candidates=[]))
    strategy.stage4_rerank = AsyncMock(return_value=[])
    strategy._get_rule_set = MagicMock(return_value=MagicMock())
    app_state.medcoder_strategy = strategy
    app_state.phi_redactor = None
    # M2.5: default to a healthy index so existing handler tests still pass.
    # The dedicated ``test_search_icd_degraded_returns_32002`` test exercises
    # the degraded path explicitly.
    app_state.medcoder_index_health = {
        "status": "ok",
        "reason": None,
        "ntotal": 37897,
        "dim": 1024,
    }
    req.app.state = app_state
    req.state.context_id = None
    return req


# ── search_icd ──


async def test_search_icd_calls_strategy_stage2(mock_request: MagicMock):
    """``search_icd`` invokes ``strategy.stage2_retrieve`` with the right args."""
    from app.icoder.mcp.handlers.search_icd import handle
    from icoder_runtime.providers.medical_coding.medcoder_strategy import (
        Stage2Result,
    )

    expected = [
        {"code": "I50.900", "name": "心力衰竭", "score": 0.9,
         "chapter": "第9章", "source": "retrieve"},
    ]
    # E1.1: stage2_retrieve now returns Stage2Result envelope
    mock_request.app.state.medcoder_strategy.stage2_retrieve = AsyncMock(
        return_value=Stage2Result(candidates=expected),
    )

    out = await handle({"emr_text": "胸痛 2 小时", "top_k": 5}, mock_request)

    mock_request.app.state.medcoder_strategy.stage2_retrieve.assert_awaited_once_with(
        "胸痛 2 小时", top_k=5,
    )
    # E1.1 (2026-06-26): handler now also surfaces Stage 2 envelope
    # fields (degraded + error_code + error_detail) so MCP consumers
    # can detect degraded retrieval without parsing the result list.
    assert out["candidates"] == expected
    assert out["source"] == "retrieve"
    assert out["degraded"] is False
    assert out["error_code"] == "MEDCODER_RETRIEVE_OK"
    assert out["error_detail"] == ""


async def test_search_icd_empty_emr_yields_empty_candidates(mock_request: MagicMock):
    """Empty input returns empty candidates (not an error)."""
    from app.icoder.mcp.handlers.search_icd import handle

    out = await handle({"emr_text": "", "top_k": 5}, mock_request)
    # E1.1: also check the envelope surface. The mock's default
    # Stage2Result has error_code="MEDCODER_RETRIEVE_OK" (NOT the
    # production short-circuit "MEDCODER_RETRIEVE_EMPTY_INPUT", which
    # is only set by the real stage2 method when called with empty
    # input). This test exercises the handler surface, not the
    # production short-circuit; the latter is covered by the strategy
    # unit test ``test_stage2_retrieve_empty_text_returns_empty``.
    assert out["candidates"] == []
    assert out["source"] == "retrieve"
    assert out["degraded"] is False
    assert out["error_code"] == "MEDCODER_RETRIEVE_OK"
    assert out["error_detail"] == ""


async def test_search_icd_degraded_returns_32002(mock_request: MagicMock):
    """M2.5 governance: when ``medcoder_index_health.status != 'ok'``,
    ``search_icd`` raises ``-32002 Retriever Unavailable`` instead of
    silently returning empty candidates.
    """
    from app.icoder.mcp.errors import MCPError, MCPErrorCode
    from app.icoder.mcp.handlers.search_icd import handle

    # Simulate a degraded health report (e.g. FAISS index missing).
    mock_request.app.state.medcoder_index_health = {
        "status": "degraded",
        "reason": "FAISS index not found at data/medcoder/faiss.index",
        "ntotal": None,
        "dim": None,
    }

    with pytest.raises(MCPError) as exc_info:
        await handle({"emr_text": "胸痛", "top_k": 5}, mock_request)
    assert exc_info.value.code == MCPErrorCode.RETRIEVER_UNAVAILABLE
    assert "FAISS index not found" in exc_info.value.message
    # The strategy's stage2_retrieve must NOT be called when degraded —
    # that's the whole point of the gate.
    mock_request.app.state.medcoder_strategy.stage2_retrieve.assert_not_awaited()


# ── verify_code ──


async def test_verify_code_in_catalog(mock_request: MagicMock):
    """``verify_code`` returns ``in_catalog=True`` + chapter/name for known code."""
    from app.icoder.mcp.handlers.verify_code import handle

    fake_entry = MagicMock()
    fake_entry.name_cn = "心力衰竭"
    fake_entry.synonyms_cn = ("心衰", "充血性心力衰竭")

    fake_loader = MagicMock()
    fake_loader.has = MagicMock(return_value=True)
    fake_loader.get = MagicMock(return_value=fake_entry)
    fake_loader.chapter_for = MagicMock(return_value="第9章 循环系统疾病")

    with patch(
        "app.services.icd10cn_loader.get_loader", return_value=fake_loader,
    ):
        out = await handle({"code": "I50.900"}, mock_request)

    assert out["code"] == "I50.900"
    assert out["in_catalog"] is True
    assert out["name"] == "心力衰竭"
    assert out["chapter"] == "第9章 循环系统疾病"
    assert "心衰" in out["aliases"]


async def test_verify_code_not_in_catalog(mock_request: MagicMock):
    """``verify_code`` returns ``in_catalog=False`` for unknown code."""
    from app.icoder.mcp.handlers.verify_code import handle

    fake_loader = MagicMock()
    fake_loader.has = MagicMock(return_value=False)

    with patch(
        "app.services.icd10cn_loader.get_loader", return_value=fake_loader,
    ):
        out = await handle({"code": "X99.999"}, mock_request)

    assert out["in_catalog"] is False
    assert out["name"] == ""
    assert out["chapter"] == ""


# ── get_differentiation_hint ──


async def test_get_differentiation_hint_returns_empty_when_kb_missing(
    mock_request: MagicMock,
):
    """When the KB file is absent, handler returns empty hints (not an error)."""
    from app.icoder.mcp.handlers.get_differentiation_hint import handle, _KB_PATH

    with patch("os.path.isfile", return_value=False):
        out = await handle({"disease_text": "心力衰竭"}, mock_request)

    assert out == {"hints": []}


async def test_get_differentiation_hint_filters_p0_p1(
    mock_request: MagicMock, tmp_path: Path,
):
    """Handler returns only P0/P1 hints mentioning the disease text."""
    from app.icoder.mcp.handlers.get_differentiation_hint import handle
    from app.icoder.mcp.handlers import get_differentiation_hint as h_mod

    kb = {
        "rules": [
            {"priority": "P0", "text": "心衰与心功能不全区分: 注意 LVEF",
             "code_a": "I50.900", "code_b": "I50.000"},
            {"priority": "P1", "text": "糖尿病分型确认", "code_a": "E11.900"},
            {"priority": "P2", "text": "should be filtered (P2)", "code_a": "I50.900"},
        ]
    }
    (tmp_path / "kb.json").write_text(json.dumps(kb), encoding="utf-8")

    with patch.object(h_mod, "_KB_PATH", str(tmp_path / "kb.json")):
        # code_a / code_b set + disease_text mentioned → P0 match
        out = await handle({
            "disease_text": "心力衰竭",
            "code_a": "I50.900",
            "code_b": "I50.000",
        }, mock_request)

    assert any("心衰" in h for h in out["hints"])
    # P2 entries should be filtered out
    assert not any("P2" in h or "should be filtered" in h for h in out["hints"])


# ── rerank_codes ──


async def test_rerank_codes_calls_strategy_stage4(mock_request: MagicMock):
    """``rerank_codes`` invokes ``strategy.stage4_rerank`` with the right args."""
    from app.icoder.mcp.handlers.rerank_codes import handle

    expected = [
        {"code": "I50.900", "name": "心力衰竭", "confidence": 0.92,
         "rationale": "best match"},
    ]
    mock_request.app.state.medcoder_strategy.stage4_rerank = AsyncMock(
        return_value=expected,
    )

    candidates = [{"code": "I50.900", "name": "心力衰竭", "score": 0.85}]
    out = await handle({
        "disease_text": "心力衰竭",
        "evidence": "胸闷气短",
        "candidates": candidates,
    }, mock_request)

    mock_request.app.state.medcoder_strategy.stage4_rerank.assert_awaited_once()
    call_args = mock_request.app.state.medcoder_strategy.stage4_rerank.call_args
    assert call_args.kwargs["disease_text"] == "心力衰竭"
    assert call_args.kwargs["evidence"] == "胸闷气短"
    assert call_args.kwargs["candidates"] == candidates
    assert out == {"ranked": expected}


async def test_rerank_codes_normalizes_output(mock_request: MagicMock):
    """Output entries are normalized to dict with the expected keys."""
    from app.icoder.mcp.handlers.rerank_codes import handle

    mock_request.app.state.medcoder_strategy.stage4_rerank = AsyncMock(
        return_value=[
            {"code": "I50.900", "name": "心力衰竭",
             "confidence": "0.85", "rationale": None},  # string / None types
        ],
    )

    out = await handle({
        "disease_text": "心力衰竭",
        "candidates": [{"code": "I50.900", "score": 0.8}],
    }, mock_request)

    assert len(out["ranked"]) == 1
    entry = out["ranked"][0]
    assert entry["code"] == "I50.900"
    assert isinstance(entry["confidence"], float)
    assert entry["confidence"] == pytest.approx(0.85)


# ── calibrate_confidence ──


async def test_calibrate_confidence_delegates_to_calibrate_all(mock_request: MagicMock):
    """``calibrate_confidence`` calls ``confidence_calibrator.calibrate_all`` 1:1."""
    from app.icoder.mcp.handlers.calibrate_confidence import handle

    fake_result = {
        "coding_confidences": [
            {"code": "I50.900", "calibrated_score": 0.85, "code_type": "primary_diagnosis"},
        ],
        "routing_decisions": [
            {"code": "I50.900", "tier": "review", "risk_factors": []},
        ],
        "metrics": {"total_codes": 1, "auto_count": 0, "review_count": 1,
                    "escalate_count": 0, "auto_accept_rate": 0.0,
                    "override_count": 0, "calibration_error_avg": 0.0,
                    "false_confidence_rate": 0.0},
    }
    with patch(
        "app.services.confidence_calibrator.calibrate_all",
        return_value=fake_result,
    ) as mock_calibrate:
        args = {
            "diagnosis_candidates": [
                {"code": "I50.900", "name": "心力衰竭", "score": 0.85},
            ],
            "procedure_candidates": [],
            "primary_diagnosis": {"code": "I50.900"},
            "evidence_ranking": {},
            "disagreement_analysis": {},
            "primary_diag_reasoning": {},
        }
        out = await handle(args, mock_request)

    mock_calibrate.assert_called_once()
    assert out is fake_result


async def test_calibrate_confidence_passes_gold_codes_when_provided(
    mock_request: MagicMock,
):
    """Gold diagnosis/procedure codes are forwarded to ``calibrate_all``."""
    from app.icoder.mcp.handlers.calibrate_confidence import handle

    fake_result = {"coding_confidences": [], "routing_decisions": [], "metrics": {}}
    with patch(
        "app.services.confidence_calibrator.calibrate_all",
        return_value=fake_result,
    ) as mock_calibrate:
        await handle({
            "diagnosis_candidates": [],
            "procedure_candidates": [],
            "primary_diagnosis": {},
            "evidence_ranking": {},
            "disagreement_analysis": {},
            "primary_diag_reasoning": {},
            "gold_diagnosis_codes": ["I50.900"],
            "gold_procedure_codes": ["00.00"],
        }, mock_request)

    kwargs = mock_calibrate.call_args.kwargs
    assert kwargs["gold_diagnosis_codes"] == ["I50.900"]
    assert kwargs["gold_procedure_codes"] == ["00.00"]