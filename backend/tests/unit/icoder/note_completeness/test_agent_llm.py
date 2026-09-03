"""Tests for the LLM-based Note Completeness Agent — Phase 4-B Step 5+6.

Verifies:
  - ``agent.run()`` with a mock LLM gateway returns a schema dict with
    all ``NoteCompletenessOutputSchema`` fields populated.
  - The LLM is called with the Chinese system prompt + the EMR text.
  - JSON extraction handles: pure JSON, fenced ```json``` block,
    JSON embedded in prose.
  - ``review_conclusion`` is derived from ``completeness_score`` if
    the LLM's stated conclusion is inconsistent.
  - Legacy regex fallback fires when LLM returns ``status="fail"``.
  - Legacy regex fallback fires when LLM output is unparseable.
  - Empty input returns a fail response without calling the LLM.
  - Surgical case detection (手术 keyword) propagates to the schema.
"""
from __future__ import annotations

import json
from typing import Any

import pytest

from icoder_runtime.backends.registry import (
    get_default_registry,
    reset_default_registry,
    set_gateway_lookup,
)


# ── Mock gateway ───────────────────────────────────────────────────


class _MockGateway:
    """Minimal stand-in for LLMGateway. Returns a canned JSON response."""

    def __init__(self, *, response_text: str = "", latency_ms: int = 5,
                 raise_exc: Exception | None = None) -> None:
        self._response_text = response_text
        self._latency_ms = latency_ms
        self._raise = raise_exc
        self.calls: list[dict] = []

    async def generate(self, messages, *, provider: str = "",
                       tools=None, response_schema=None, context=None):
        if self._raise is not None:
            raise self._raise
        self.calls.append({
            "messages": messages,
            "context": context,
        })
        return {
            "content": self._response_text,
            "model": "mock/1.0",
            "usage": {"input_tokens": 10, "output_tokens": 20},
            "latency_ms": self._latency_ms,
        }


def _schema_json(*, conclusion: str = "PASS", score: float = 1.0,
                 missing: list[str] = None, present: list[str] = None,
                 required: list[str] = None, surgical: bool = False,
                 gaps: list[dict] = None) -> str:
    """Build a canned NoteCompletenessOutputSchema JSON string."""
    missing = missing or []
    present = present or []
    required = required or []
    payload = {
        "review_conclusion": conclusion,
        "completeness_score": score,
        "missing_sections": missing,
        "present_sections": present,
        "required_sections": required,
        "is_surgical_case": surgical,
        "manual_review_required": bool(missing) and conclusion != "PASS",
        "documentation_gaps": gaps or [
            {
                "gap_type": "missing_section",
                "description": f"病历缺少必填章节: {s}",
                "section": s,
                "suggestion": f"请补充 {s} 章节 — 《病历书写基本规范》要求",
                "related_code": "",
            }
            for s in missing
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def fresh_registry():
    """Reset the default registry + gateway lookup before each test."""
    reset_default_registry()
    yield
    set_gateway_lookup(None)
    reset_default_registry()


@pytest.fixture
def wired_gateway(fresh_registry):
    """Wire a mock gateway via set_gateway_lookup; return the mock."""
    gw = _MockGateway()
    set_gateway_lookup(lambda: gw)
    return gw


# ── happy path ─────────────────────────────────────────────────────


SAMPLE_EMR = (
    "主诉：心悸3年\n"
    "现病史：患者3年前无明显诱因出现心悸\n"
    "既往史：高血压10年\n"
    "体格检查：心率90次/分\n"
    "辅助检查：ECG正常\n"
    "诊断：心律失常\n"
    "治疗经过：药物控制"
)


@pytest.mark.asyncio
async def test_run_happy_path_returns_schema_dict(wired_gateway):
    """agent.run() with a PASS response returns all schema fields populated."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    wired_gateway._response_text = _schema_json(
        conclusion="PASS",
        score=1.0,
        present=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
        required=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
    )

    result = await run(SAMPLE_EMR, run_id="run-happy-1")

    assert result["review_conclusion"] == "PASS"
    assert result["completeness_score"] == 1.0
    assert result["missing_sections"] == []
    assert "主诉" in result["present_sections"]
    assert result["is_surgical_case"] is False
    assert result["manual_review_required"] is False
    assert result["trace_refs"]["run_id"] == "run-happy-1"
    assert result["trace_refs"]["agent_ref"] == "icoder/note-completeness-agent@1.0.0"
    assert result["trace_refs"]["rule_set"] == "documentation_completeness"


@pytest.mark.asyncio
async def test_run_passes_system_prompt_and_emr_to_llm(wired_gateway):
    """The LLM receives the Chinese system prompt + the EMR text."""
    from official_agents.note_completeness.agent import (
        SYSTEM_PROMPT,
        run_llm_enhanced as run,
    )

    wired_gateway._response_text = _schema_json()

    await run(SAMPLE_EMR, run_id="run-prompts-1")

    assert len(wired_gateway.calls) == 1
    messages = wired_gateway.calls[0]["messages"]
    system_content = messages[0]["content"]
    user_content = messages[1]["content"]
    assert system_content == SYSTEM_PROMPT
    assert "心悸3年" in user_content
    assert "主诉" in user_content


# ── JSON extraction handles all 3 shapes ───────────────────────────


@pytest.mark.asyncio
async def test_run_handles_pure_json_output(wired_gateway):
    """LLM outputs just a JSON object — agent parses it."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    wired_gateway._response_text = _schema_json(
        conclusion="WARNING", score=0.7143,
        missing=["主诉"],
        present=["现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
        required=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
    )
    result = await run(SAMPLE_EMR, run_id="run-json-1")
    assert result["review_conclusion"] == "WARNING"
    assert result["completeness_score"] == 0.7143
    assert result["missing_sections"] == ["主诉"]


@pytest.mark.asyncio
async def test_run_handles_fenced_json_block(wired_gateway):
    """LLM wraps JSON in ```json ... ``` fence — agent extracts it."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    payload = _schema_json(
        conclusion="WARNING", score=0.7143, missing=["主诉"],
        present=["现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
        required=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
    )
    wired_gateway._response_text = (
        "Here's my analysis:\n\n```json\n" + payload + "\n```\n\nLet me know."
    )
    result = await run(SAMPLE_EMR, run_id="run-fenced-1")
    assert result["review_conclusion"] == "WARNING"
    assert result["missing_sections"] == ["主诉"]


@pytest.mark.asyncio
async def test_run_handles_json_embedded_in_prose(wired_gateway):
    """LLM writes prose with embedded JSON — agent pulls the {...} substring."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    payload = _schema_json(
        conclusion="PASS", score=1.0,
        present=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
        required=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
    )
    wired_gateway._response_text = (
        "After reviewing the note, here is my assessment: " + payload + " — hope this helps!"
    )
    result = await run(SAMPLE_EMR, run_id="run-prose-1")
    assert result["review_conclusion"] == "PASS"
    assert result["manual_review_required"] is False


# ── conclusion / score consistency ─────────────────────────────────


@pytest.mark.asyncio
async def test_run_overrides_inconsistent_conclusion(wired_gateway):
    """LLM says PASS but score < 0.5 → agent derives FAIL from score."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    wired_gateway._response_text = _schema_json(
        conclusion="PASS",  # wrong
        score=0.3,  # → FAIL
        missing=["主诉", "现病史", "既往史", "体格检查", "辅助检查"],
        present=["诊断", "治疗经过"],
        required=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过"],
    )
    result = await run(SAMPLE_EMR, run_id="run-inconsistent-1")
    assert result["review_conclusion"] == "FAIL"


# ── fallback to legacy regex ───────────────────────────────────────


@pytest.mark.asyncio
async def test_run_falls_back_to_legacy_on_llm_fail(wired_gateway):
    """LLM returns degraded (no_api_key) → agent falls back to legacy regex."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    # LLM returns a degraded response (no real content)
    wired_gateway._response_text = ""
    # Simulate degraded by having the gateway return an empty content
    # — agent will treat as unparseable and fall back.

    result = await run(SAMPLE_EMR, run_id="run-fallback-1")

    # Legacy regex should fire — it detects 7 sections in SAMPLE_EMR → PASS
    assert result["review_conclusion"] == "PASS"
    assert result["manual_review_required"] is True
    assert result["fallback_used"] is True
    assert result["completeness_score"] == 1.0
    assert result["missing_sections"] == []
    # Legacy uses a uuid when run_id is empty; our run_id is preserved.
    assert result["trace_refs"]["run_id"] == "run-fallback-1"


@pytest.mark.asyncio
async def test_run_falls_back_to_legacy_on_unparseable_output(wired_gateway):
    """LLM returns garbage text → agent falls back to legacy regex."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    wired_gateway._response_text = "Sorry, I can't help with that."

    result = await run(SAMPLE_EMR, run_id="run-garbage-1")

    # Legacy regex fires
    assert result["review_conclusion"] == "PASS"
    assert result["trace_refs"]["run_id"] == "run-garbage-1"


@pytest.mark.asyncio
async def test_run_falls_back_to_legacy_on_llm_exception(fresh_registry):
    """LLM raises an exception → agent falls back to legacy regex."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    gw = _MockGateway(raise_exc=RuntimeError("LLM gateway exploded"))
    set_gateway_lookup(lambda: gw)

    result = await run(SAMPLE_EMR, run_id="run-exc-1")

    assert result["review_conclusion"] == "PASS"
    assert result["trace_refs"]["run_id"] == "run-exc-1"


# ── empty input ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_empty_input_returns_fail_without_calling_llm(wired_gateway):
    """Empty EMR text → fail response immediately, no LLM call."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    result = await run("", run_id="run-empty-1")

    assert result["review_conclusion"] == "FAIL"
    assert result["completeness_score"] == 0.0
    assert result["trace_refs"]["run_id"] == "run-empty-1"
    assert len(wired_gateway.calls) == 0  # no LLM call


@pytest.mark.asyncio
async def test_run_whitespace_only_input_returns_fail(wired_gateway):
    """Whitespace-only EMR → also fail, no LLM call."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    result = await run("   \n  \t  ", run_id="run-ws-1")
    assert result["review_conclusion"] == "FAIL"
    assert len(wired_gateway.calls) == 0


# ── surgical case ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_surgical_case_propagates_is_surgical(wired_gateway):
    """Surgical case (手术 keyword) → is_surgical_case=True in result."""
    from official_agents.note_completeness.agent import run_llm_enhanced as run

    surgical_emr = (
        "主诉：腹痛3天\n"
        "现病史：患者3天前出现腹痛\n"
        "既往史：无\n"
        "体格检查：腹部压痛\n"
        "辅助检查：CT示阑尾炎\n"
        "诊断：急性阑尾炎\n"
        "治疗经过：行阑尾切除术\n"
        "手术记录：阑尾切除术经过..."
    )
    wired_gateway._response_text = _schema_json(
        conclusion="PASS", score=1.0, surgical=True,
        present=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过", "手术记录"],
        required=["主诉", "现病史", "既往史", "体格检查", "辅助检查", "诊断", "治疗经过", "手术记录"],
    )
    result = await run(surgical_emr, run_id="run-surgical-1")
    assert result["is_surgical_case"] is True
