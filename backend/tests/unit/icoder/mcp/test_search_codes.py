"""Phase 4-C: ``search_codes`` handler tests.

Verifies the wrapper that aliases ``search_icd`` with Corti-style
``query`` input parameter.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = pytest.mark.asyncio


def _make_mock_request() -> MagicMock:
    """Stub Request with healthy FAISS index + mock strategy."""
    from icoder_runtime.providers.medical_coding.medcoder_strategy import Stage2Result

    req = MagicMock()
    app_state = MagicMock()
    strategy = MagicMock()
    strategy.stage2_retrieve = AsyncMock(return_value=Stage2Result(candidates=[]))
    app_state.medcoder_strategy = strategy
    app_state.phi_redactor = None
    app_state.medcoder_index_health = {
        "status": "ok",
        "reason": None,
        "ntotal": 37897,
        "dim": 1024,
    }
    req.app.state = app_state
    req.state.context_id = None
    return req


# ── query → emr_text normalization ───────────────────────────────────


async def test_search_codes_query_normalized_to_emr_text():
    """``query`` param is forwarded to search_icd as ``emr_text``."""
    from app.icoder.mcp.handlers.search_codes import handle

    req = _make_mock_request()
    expected = [
        {"code": "I50.900", "name": "心力衰竭", "score": 0.9,
         "chapter": "第9章", "source": "retrieve"},
    ]
    from icoder_runtime.providers.medical_coding.medcoder_strategy import Stage2Result
    req.app.state.medcoder_strategy.stage2_retrieve = AsyncMock(
        return_value=Stage2Result(candidates=expected),
    )

    out = await handle({"query": "胸痛 2 小时", "top_k": 5}, req)

    # search_icd was called with emr_text="胸痛 2 小时"
    req.app.state.medcoder_strategy.stage2_retrieve.assert_awaited_once_with(
        "胸痛 2 小时", top_k=5,
    )
    assert out["candidates"] == expected
    assert out["source"] == "retrieve"


# ── backwards compat: emr_text still accepted ────────────────────────


async def test_search_codes_accepts_legacy_emr_text_param():
    """When caller passes ``emr_text`` instead of ``query``, it still works."""
    from app.icoder.mcp.handlers.search_codes import handle

    req = _make_mock_request()
    from icoder_runtime.providers.medical_coding.medcoder_strategy import Stage2Result
    req.app.state.medcoder_strategy.stage2_retrieve = AsyncMock(
        return_value=Stage2Result(candidates=[]),
    )

    await handle({"emr_text": "心衰", "top_k": 3}, req)

    req.app.state.medcoder_strategy.stage2_retrieve.assert_awaited_once_with(
        "心衰", top_k=3,
    )


# ── query preferred over emr_text ────────────────────────────────────


async def test_search_codes_query_takes_precedence_over_emr_text():
    """If both ``query`` and ``emr_text`` are passed, ``query`` wins."""
    from app.icoder.mcp.handlers.search_codes import handle

    req = _make_mock_request()
    from icoder_runtime.providers.medical_coding.medcoder_strategy import Stage2Result
    req.app.state.medcoder_strategy.stage2_retrieve = AsyncMock(
        return_value=Stage2Result(candidates=[]),
    )

    await handle({"query": "stemi", "emr_text": "心衰", "top_k": 5}, req)

    req.app.state.medcoder_strategy.stage2_retrieve.assert_awaited_once_with(
        "stemi", top_k=5,
    )


# ── empty query ──────────────────────────────────────────────────────


async def test_search_codes_empty_query_returns_empty_candidates():
    """Empty query → search_icd called with empty string → empty candidates."""
    from app.icoder.mcp.handlers.search_codes import handle

    req = _make_mock_request()
    from icoder_runtime.providers.medical_coding.medcoder_strategy import Stage2Result
    req.app.state.medcoder_strategy.stage2_retrieve = AsyncMock(
        return_value=Stage2Result(candidates=[]),
    )

    out = await handle({"query": "", "top_k": 5}, req)

    req.app.state.medcoder_strategy.stage2_retrieve.assert_awaited_once_with(
        "", top_k=5,
    )
    assert out["candidates"] == []


# ── degraded health gate (-32002) ────────────────────────────────────


async def test_search_codes_propagates_retriever_unavailable():
    """When FAISS index is degraded, ``-32002`` propagates through the wrapper."""
    from app.icoder.mcp.handlers.search_codes import handle
    from app.icoder.mcp.errors import MCPError, MCPErrorCode

    req = _make_mock_request()
    req.app.state.medcoder_index_health = {
        "status": "degraded",
        "reason": "faiss.index not found",
        "ntotal": 0,
        "dim": 0,
    }

    with pytest.raises(MCPError) as exc_info:
        await handle({"query": "心衰", "top_k": 5}, req)

    assert exc_info.value.code == MCPErrorCode.RETRIEVER_UNAVAILABLE


# ── default top_k ────────────────────────────────────────────────────


async def test_search_codes_default_top_k_is_5():
    """When top_k is omitted, defaults to 5."""
    from app.icoder.mcp.handlers.search_codes import handle

    req = _make_mock_request()
    from icoder_runtime.providers.medical_coding.medcoder_strategy import Stage2Result
    req.app.state.medcoder_strategy.stage2_retrieve = AsyncMock(
        return_value=Stage2Result(candidates=[]),
    )

    await handle({"query": "心衰"}, req)  # no top_k

    req.app.state.medcoder_strategy.stage2_retrieve.assert_awaited_once_with(
        "心衰", top_k=5,
    )
