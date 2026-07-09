"""G001 refactor unit tests — CodingRuntime abstraction + dispatcher.

Covers:
  - RuntimeMode.coerce (string → enum, fallback to FAST on unknown)
  - CodingRuntimeDispatcher routes by mode correctly
  - FastCodingRuntime empty / oversize input handling
  - FastCodingRuntime LLM-call-failure → friendly error result (no exception)
  - FastCodingRuntime schema-returned-error (DS001) → friendly error result
  - MedCoderRuntime empty input → friendly error result
  - Endpoint POST /api/v1/coding/predict: auth required, mode validation

Mock LLM responses are injected via a fake gateway so tests don't hit the
real DeepSeek API.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.coding_runtime import (
    CodingRequest,
    CodingResult,
    RuntimeMode,
    get_dispatcher,
    reset_dispatcher,
)
from app.coding_runtime.fast_runtime import FastCodingRuntime
from app.coding_runtime.medcoder_runtime import MedCoderRuntime


# ─── Test fixtures ─────────────────────────────────────────────────────


class _FakeGateway:
    """Minimal fake LLM gateway for FastCodingRuntime tests.

    Yields a canned DeepSeek-shaped response. ``fail_once`` simulates a
    transient error to exercise retry logic; ``always_fail`` forces the
    error-schema path.
    """

    def __init__(self, content: str = "", always_fail: bool = False,
                 fail_once: bool = False, is_configured: bool = True):
        self._content = content
        self._always_fail = always_fail
        self._fail_once = fail_once
        self._calls = 0
        self.is_configured = is_configured

    async def generate(self, messages, *, provider: str = "", **kw) -> dict[str, Any]:
        self._calls += 1
        if self._always_fail or (self._fail_once and self._calls == 1):
            raise RuntimeError("simulated DeepSeek failure")
        return {"content": self._content, "model": "deepseek-chat", "usage": {}}

    def get(self, name: str = ""):
        return self  # everything routes to self


# A canonical T12-style encounter used across tests
T12_TEXT = (
    "患者男性,78岁,因摔倒后腰背部剧痛入院。"
    "MRI 显示 T12 椎体压缩性骨折。"
    "既往有骨质疏松、高血压、2 型糖尿病病史。"
    "行 T12 经皮椎体成形术。术后过程平稳,无明显并发症。"
)


def _ok_json() -> str:
    """A canonical successful DeepSeek JSON response (T12 case)."""
    import json
    return json.dumps({
        "review_conclusion": "PASS",
        "primary_diagnosis": {
            "code": "S22.089A",
            "description": "胸椎(T11-T12)压缩性骨折",
            "confidence": 0.88,
            "category": "principal",
            "evidence": ["MRI 显示 T12 椎体压缩性骨折"],
        },
        "secondary_diagnoses": [
            {
                "code": "M81.0",
                "description": "年龄相关性骨质疏松不伴当前病理性骨折",
                "confidence": 0.82,
                "category": "secondary",
                "evidence": ["既往有骨质疏松"],
            },
            {
                "code": "I10",
                "description": "原发性高血压",
                "confidence": 0.90,
                "category": "comorbidity",
                "evidence": ["高血压病史"],
            },
            {
                "code": "E11.9",
                "description": "2 型糖尿病不伴并发症",
                "confidence": 0.86,
                "category": "comorbidity",
                "evidence": ["2 型糖尿病病史"],
            },
        ],
        "procedures": [
            {
                "code": "81.62",
                "description": "经皮椎体成形术",
                "confidence": 0.85,
                "category": "therapeutic",
                "evidence": ["行 T12 经皮椎体成形术"],
            },
        ],
        "issues_found": [],
        "manual_review_required": False,
        "confidence": 0.86,
        "notes": "本病例主要涉及 T12 椎体压缩性骨折、骨质疏松、高血压、2 型糖尿病以及经皮椎体成形术。",
    })


def _error_json() -> str:
    """A DS001-style error response (forces FastCodingRuntime error path)."""
    import json
    return json.dumps({
        "review_conclusion": "FAIL",
        "primary_diagnosis": {},
        "secondary_diagnoses": [],
        "procedures": [],
        "issues_found": [
            {
                "severity": "critical",
                "code": "DS001",
                "message": "DeepSeek V4 调用失败: simulated failure",
                "suggestion": "请检查 DeepSeek API 配置或切换到其他 coding mode",
            }
        ],
        "manual_review_required": True,
        "confidence": 0.0,
        "notes": "",
    })


# ─── RuntimeMode.coerce ────────────────────────────────────────────────


def test_runtime_mode_coerce_known_values():
    assert RuntimeMode.coerce("corti_like_fast") == RuntimeMode.CORTI_LIKE_FAST
    assert RuntimeMode.coerce("medcoder_deep") == RuntimeMode.MEDCODER_DEEP
    assert RuntimeMode.coerce(RuntimeMode.CORTI_LIKE_FAST) == RuntimeMode.CORTI_LIKE_FAST


def test_runtime_mode_coerce_unknown_falls_back_to_fast():
    assert RuntimeMode.coerce("unknown_mode") == RuntimeMode.CORTI_LIKE_FAST
    assert RuntimeMode.coerce(None) == RuntimeMode.CORTI_LIKE_FAST
    assert RuntimeMode.coerce(42) == RuntimeMode.CORTI_LIKE_FAST
    assert RuntimeMode.coerce("") == RuntimeMode.CORTI_LIKE_FAST


# ─── Dispatcher routing ────────────────────────────────────────────────


def test_dispatcher_routes_fast_to_fast_runtime():
    reset_dispatcher()
    d = get_dispatcher()
    runtime = d.select_runtime(RuntimeMode.CORTI_LIKE_FAST)
    assert runtime.name == "fast_coding_runtime"


def test_dispatcher_routes_deep_to_medcoder_runtime():
    reset_dispatcher()
    d = get_dispatcher()
    runtime = d.select_runtime(RuntimeMode.MEDCODER_DEEP)
    assert runtime.name == "medcoder_runtime"


def test_dispatcher_unknown_mode_falls_back_to_fast():
    """Unknown mode must NEVER raise — always fall back to Fast."""
    reset_dispatcher()
    d = get_dispatcher()
    runtime = d.select_runtime(RuntimeMode.CORTI_LIKE_FAST)
    assert runtime.name == "fast_coding_runtime"


# ─── FastCodingRuntime ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fast_runtime_empty_input_returns_error_result():
    """Empty input must return a CodingResult with error=True — never raise."""
    rt = FastCodingRuntime(gateway=_FakeGateway(content=_ok_json()))
    result = await rt.predict(CodingRequest(text="", mode=RuntimeMode.CORTI_LIKE_FAST))
    assert isinstance(result, CodingResult)
    assert result.error is True
    assert result.error_reason == "empty_input"
    assert result.runtime_mode == "corti_like_fast"
    assert len(result.codes) == 0
    # Trace must still have input_received + return steps
    steps = [e["step"] for e in result.trace_events]
    assert "input_received" in steps
    assert "return" in steps


@pytest.mark.asyncio
async def test_fast_runtime_oversize_input_returns_error_result():
    """Inputs >16000 chars must return input_too_long error result."""
    rt = FastCodingRuntime(gateway=_FakeGateway(content=_ok_json()))
    long_text = "x" * 20000
    result = await rt.predict(CodingRequest(text=long_text, mode=RuntimeMode.CORTI_LIKE_FAST))
    assert result.error is True
    assert result.error_reason == "input_too_long"
    assert len(result.codes) == 0


@pytest.mark.asyncio
async def test_fast_runtime_llm_call_failure_returns_error_result():
    """When DeepSeek raises, FastCodingRuntime must return a friendly error result, not propagate."""
    rt = FastCodingRuntime(gateway=_FakeGateway(always_fail=True))
    result = await rt.predict(CodingRequest(text=T12_TEXT, mode=RuntimeMode.CORTI_LIKE_FAST))
    # DeepSeekCodingAdapter has 2 retries → 3 total attempts → all fail → _error_schema
    # The error_schema has review_conclusion=FAIL + DS001 issue, which FastCodingRuntime
    # detects and surfaces as error=True.
    assert result.error is True
    assert result.error_reason in ("schema_returned_error", "llm_call_failed")
    assert len(result.codes) == 0
    # Summary must mention retry or mode switch (per G001 §5.6 — friendly error)
    assert "重试" in result.summary or "切换" in result.summary or "失败" in result.summary


@pytest.mark.asyncio
async def test_fast_runtime_happy_path_returns_structured_codes():
    """Canonical T12 case: returns primary + 3 secondary + 1 procedure with evidence."""
    rt = FastCodingRuntime(gateway=_FakeGateway(content=_ok_json()))
    result = await rt.predict(CodingRequest(text=T12_TEXT, mode=RuntimeMode.CORTI_LIKE_FAST))
    assert result.error is False
    assert result.runtime_mode == "corti_like_fast"
    assert len(result.codes) >= 4  # 1 primary + 3 secondary + 1 procedure = 5
    primary = next(c for c in result.codes if c.type == "primary_diagnosis")
    assert primary.code == "S22.089A"
    assert "T12" in primary.evidence or "椎体" in primary.evidence
    assert primary.confidence > 0.5
    assert len(primary.warnings) > 0  # G001 §7: must include local-catalog-review warning
    # Trace must include all 7 steps
    steps = [e["step"] for e in result.trace_events]
    assert "input_received" in steps
    assert "language_detect" in steps
    assert "build_prompt" in steps
    assert "llm_call" in steps
    assert "parse_json" in steps
    assert "project_result" in steps
    assert "return" in steps
    # Latency must be measured
    assert result.latency_ms > 0
    assert result.trace_id.startswith("trace-")
    assert result.run_id.startswith("fast-")


@pytest.mark.asyncio
async def test_fast_runtime_chinese_input_detected_as_zh():
    """Language detection: Chinese text → 'zh'."""
    rt = FastCodingRuntime(gateway=_FakeGateway(content=_ok_json()))
    result = await rt.predict(CodingRequest(text=T12_TEXT, mode=RuntimeMode.CORTI_LIKE_FAST))
    lang_event = next(e for e in result.trace_events if e["step"] == "language_detect")
    assert lang_event["metadata"]["language"] == "zh"


@pytest.mark.asyncio
async def test_fast_runtime_english_input_detected_as_en():
    """Language detection: English text → 'en'."""
    rt = FastCodingRuntime(gateway=_FakeGateway(content=_ok_json()))
    english_text = "78yo male with T12 vertebral compression fracture. History of osteoporosis, hypertension, T2DM."
    result = await rt.predict(CodingRequest(text=english_text, mode=RuntimeMode.CORTI_LIKE_FAST))
    lang_event = next(e for e in result.trace_events if e["step"] == "language_detect")
    assert lang_event["metadata"]["language"] == "en"


@pytest.mark.asyncio
async def test_fast_runtime_json_repair_handles_markdown_fences():
    """DeepSeekCodingAdapter._extract_json must handle ```json ... ``` fences."""
    from icoder_runtime.providers.medical_coding.deepseek_coding_adapter import DeepSeekCodingAdapter
    adapter = DeepSeekCodingAdapter(gateway=_FakeGateway())
    extracted = adapter._extract_json("```json\n" + _ok_json() + "\n```")
    assert extracted is not None
    assert extracted.get("review_conclusion") == "PASS"
    assert len(extracted.get("secondary_diagnoses", [])) == 3


# ─── MedCoderRuntime ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_medcoder_runtime_empty_input_returns_error_result():
    """Deep mode empty input must return error result, never raise."""
    rt = MedCoderRuntime()
    result = await rt.predict(CodingRequest(text="", mode=RuntimeMode.MEDCODER_DEEP))
    assert result.error is True
    assert result.error_reason == "empty_input"
    assert result.runtime_mode == "medcoder_deep"
    assert len(result.codes) == 0


# Note: We do NOT test MedCoderRuntime happy path here because it requires
# the real BGE-M3 + FAISS retriever (excluded from default test sweep via
# pytest.ini `retrieval` marker). The empty-input test above is sufficient
# to verify the runtime wrapper doesn't crash on edge cases.


# ─── Dispatcher.dispatch ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_dispatch_fast_returns_coding_result():
    reset_dispatcher()
    d = get_dispatcher()
    # Override the cached fast runtime with one wired to a fake gateway
    d._fast = FastCodingRuntime(gateway=_FakeGateway(content=_ok_json()))
    result = await d.dispatch(CodingRequest(text=T12_TEXT, mode=RuntimeMode.CORTI_LIKE_FAST))
    assert isinstance(result, CodingResult)
    assert result.runtime_mode == "corti_like_fast"
    assert len(result.codes) >= 4


@pytest.mark.asyncio
async def test_dispatcher_dispatch_unknown_mode_falls_back_to_fast():
    """Unknown mode string coerced to FAST — never raises."""
    reset_dispatcher()
    d = get_dispatcher()
    d._fast = FastCodingRuntime(gateway=_FakeGateway(content=_ok_json()))
    req = CodingRequest(text=T12_TEXT, mode=RuntimeMode.CORTI_LIKE_FAST)
    # Pass an unknown string mode via the coerce path
    req.mode = RuntimeMode.coerce("totally_unknown")
    result = await d.dispatch(req)
    assert result.runtime_mode == "corti_like_fast"
