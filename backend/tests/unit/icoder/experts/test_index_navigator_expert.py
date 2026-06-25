"""IndexNavigatorExpert tests (~10 cases).

Covers:
  - Metadata (EXPERT_ID / EXPERT_NAME)
  - No retriever → status="missing" with empty candidates
  - Retriever not loaded → status="degraded"
  - Mocked retriever returns candidates in correct shape
  - Empty facts list → empty candidates but status="ok"
  - Empty fact text → empty candidates (per-fact fallback)
  - Per-fact retriever error → that fact's candidates is empty, others succeed
  - __call__ alias matches invoke_sync
  - JSON payload parsing in invoke_sync
  - Error translation on hard failure
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.icoder.agent_runtime.experts.index_navigator_expert import (
    IndexNavigatorExpert,
)
from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)


# ── Metadata ──


class TestMetadata:
    def test_expert_id(self):
        assert IndexNavigatorExpert.EXPERT_ID == "index-navigator"

    def test_expert_name(self):
        assert "Stage 2" in IndexNavigatorExpert.EXPERT_NAME
        assert "MedCodER" in IndexNavigatorExpert.EXPERT_NAME


# ── Helpers ──


class _FakeCandidate:
    """Plain candidate with literal attributes (avoids MagicMock attr magic)."""
    def __init__(self, code, name, score, chapter=""):
        self.code = code
        self.name = name
        self.score = score
        self.chapter = chapter


def _candidate(code: str = "I50.900", name: str = "心力衰竭", score: float = 0.95):
    return _FakeCandidate(code=code, name=name, score=score, chapter="IX 循环系统")


def _empty_invocation(payload: dict | None = None) -> ExpertInvocation:
    return ExpertInvocation(
        expert_id="index-navigator",
        subtask_input=json.dumps(payload) if payload is not None else "",
        context={},
        attempt=1,
    )


# ── Shape ──


class TestShape:
    def test_invoke_sync_returns_required_fields(self):
        exp = IndexNavigatorExpert()
        result = exp.invoke_sync(_empty_invocation({"diagnosis_facts": []}))
        assert isinstance(result, dict)
        assert "diagnosis_candidates" in result
        assert "procedure_candidates" in result
        assert "retriever_status" in result
        assert result["expert_id"] == "index-navigator"

    @pytest.mark.asyncio
    async def test_invoke_async_returns_required_fields(self):
        exp = IndexNavigatorExpert()
        result = await exp.invoke_async({"diagnosis_facts": []})
        assert isinstance(result, dict)
        assert "diagnosis_candidates" in result
        assert result["retriever_status"] in {"ok", "degraded", "missing"}

    def test_callable_equals_invoke_sync(self):
        exp = IndexNavigatorExpert()
        inv = _empty_invocation({"diagnosis_facts": []})
        assert exp(inv) == exp.invoke_sync(inv)


# ── Retriever presence / state ──


class TestRetrieverState:
    @pytest.mark.asyncio
    async def test_no_retriever_returns_missing(self):
        exp = IndexNavigatorExpert()
        result = await exp.invoke_async({"diagnosis_facts": [{"fact": "心衰"}]})
        assert result["retriever_status"] == "missing"
        assert result["diagnosis_candidates"] == []
        assert result["procedure_candidates"] == []

    @pytest.mark.asyncio
    async def test_retriever_not_loaded_returns_degraded(self):
        retriever = MagicMock()
        retriever.is_loaded.return_value = False
        retriever.ensure_loaded = MagicMock()
        retriever._index = None
        exp = IndexNavigatorExpert(retriever=retriever)
        result = await exp.invoke_async({"diagnosis_facts": [{"fact": "心衰"}]})
        assert result["retriever_status"] == "degraded"

    @pytest.mark.asyncio
    async def test_retriever_ensure_loaded_raises_returns_degraded(self):
        retriever = MagicMock()
        retriever.ensure_loaded.side_effect = RuntimeError("disk error")
        exp = IndexNavigatorExpert(retriever=retriever)
        result = await exp.invoke_async({"diagnosis_facts": [{"fact": "心衰"}]})
        assert result["retriever_status"] == "degraded"


# ── Mocked retriever path ──


class TestMockedRetriever:
    @pytest.mark.asyncio
    async def test_returns_candidate_shape(self):
        retriever = MagicMock()
        retriever.is_loaded.return_value = True
        retriever._index = MagicMock()  # non-None
        retriever.ensure_loaded = MagicMock()
        retriever.retrieve_async = AsyncMock(return_value=[
            _candidate("I50.900", "心力衰竭", 0.95),
            _candidate("I50.100", "左心衰竭", 0.82),
        ])
        exp = IndexNavigatorExpert(retriever=retriever)
        result = await exp.invoke_async({"diagnosis_facts": [{"fact": "心衰"}]})
        assert result["retriever_status"] == "ok"
        dx = result["diagnosis_candidates"]
        assert len(dx) == 1
        assert dx[0]["fact"] == "心衰"
        assert len(dx[0]["candidates"]) == 2
        first = dx[0]["candidates"][0]
        assert first["code"] == "I50.900"
        assert first["name"] == "心力衰竭"
        assert first["score"] == 0.95
        assert first["match_type"] == "vector"

    @pytest.mark.asyncio
    async def test_empty_facts_returns_ok_with_empty_lists(self):
        retriever = MagicMock()
        retriever.is_loaded.return_value = True
        retriever._index = MagicMock()
        exp = IndexNavigatorExpert(retriever=retriever)
        result = await exp.invoke_async({})
        assert result["retriever_status"] == "ok"
        assert result["diagnosis_candidates"] == []
        assert result["procedure_candidates"] == []
        # Retriever should NOT have been called
        retriever.retrieve_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_fact_text_skips_retrieval(self):
        retriever = MagicMock()
        retriever.is_loaded.return_value = True
        retriever._index = MagicMock()
        retriever.retrieve_async = AsyncMock()
        exp = IndexNavigatorExpert(retriever=retriever)
        result = await exp.invoke_async({"diagnosis_facts": [{"fact": ""}]})
        assert result["diagnosis_candidates"][0]["candidates"] == []
        retriever.retrieve_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_per_fact_retrieve_error_doesnt_fail_batch(self):
        retriever = MagicMock()
        retriever.is_loaded.return_value = True
        retriever._index = MagicMock()

        async def _maybe_fail(text, top_k=None, expand_synonyms=True):
            if "fail" in text:
                raise RuntimeError("intentional")
            return [_candidate()]
        retriever.retrieve_async = AsyncMock(side_effect=_maybe_fail)
        exp = IndexNavigatorExpert(retriever=retriever)
        result = await exp.invoke_async({
            "diagnosis_facts": [
                {"fact": "心衰"},
                {"fact": "this should fail"},
                {"fact": "高血压"},
            ]
        })
        assert result["retriever_status"] == "ok"
        cands = result["diagnosis_candidates"]
        # 2 succeeded, 1 failed
        assert len(cands) == 3
        assert len(cands[0]["candidates"]) == 1
        assert cands[1]["candidates"] == []
        assert len(cands[2]["candidates"]) == 1

    @pytest.mark.asyncio
    async def test_top_k_override_from_context(self):
        retriever = MagicMock()
        retriever.is_loaded.return_value = True
        retriever._index = MagicMock()
        retriever.retrieve_async = AsyncMock(return_value=[_candidate()])
        exp = IndexNavigatorExpert(retriever=retriever, default_top_k=20)
        await exp.invoke_async(
            {"diagnosis_facts": [{"fact": "心衰"}]},
            ctx={"top_k": 5, "expand_synonyms": False},
        )
        # retrieve_async called with top_k=5 and expand_synonyms=False
        retriever.retrieve_async.assert_called_once_with(
            "心衰", top_k=5, expand_synonyms=False,
        )


# ── invoke_sync JSON parsing ──


class TestInvokeSyncJSON:
    def test_json_payload_parsed(self):
        retriever = MagicMock()
        retriever.is_loaded.return_value = True
        retriever._index = MagicMock()
        retriever.retrieve_async = AsyncMock(return_value=[_candidate()])
        exp = IndexNavigatorExpert(retriever=retriever)
        payload = {
            "diagnosis_facts": [{"fact": "心衰"}],
            "procedure_facts": [],
        }
        result = exp.invoke_sync(_empty_invocation(payload))
        assert result["retriever_status"] == "ok"
        assert len(result["diagnosis_candidates"]) == 1

    def test_invalid_json_falls_back_to_empty_facts(self):
        exp = IndexNavigatorExpert(retriever=MagicMock(
            is_loaded=MagicMock(return_value=True),
            _index=MagicMock(),
        ))
        inv = ExpertInvocation(
            expert_id="index-navigator",
            subtask_input="not valid json {",
            context={},
            attempt=1,
        )
        result = exp.invoke_sync(inv)
        # Empty facts dict → no error, empty candidates
        assert result["diagnosis_candidates"] == []


# ── Error handling ──


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_unexpected_error_translated_to_expert_invocation_error(self):
        exp = IndexNavigatorExpert()

        # Patch _navigate to raise unexpected error
        async def _bad(_f, _c):
            raise RuntimeError("intentional crash")
        exp._navigate = _bad
        with pytest.raises(ExpertInvocationError) as exc_info:
            await exp.invoke_async({"diagnosis_facts": []})
        assert "navigation failed" in str(exc_info.value)
        assert exc_info.value.stage == "retrieving"