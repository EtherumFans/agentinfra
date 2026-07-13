"""Track H3.18 — response_options deterministic padding in _hydrate_query.

The query_generation prompt requires ≥4 response_options including ≥1 escape
hatch, but the LLM sometimes emits only 3 (narrow clinical scenarios). The
orchestrator now pads deterministically to satisfy the response_options_4plus
target (≥95%).
"""

from __future__ import annotations

from app.icoder.agent_runtime.cdi.orchestrator import CDIOrchestrator


def _hydrate(q_dict):
    return CDIOrchestrator._hydrate_query(q_dict)


def test_padding_adds_escape_when_missing() -> None:
    q = _hydrate({
        "query_id": "q1",
        "query_text": "请明确肝硬化严重程度",
        "response_options": ["A. 轻度", "B. 中度", "C. 重度"],
    })
    assert len(q.response_options) >= 4
    assert any("无法确定" in opt for opt in q.response_options)


def test_padding_preserves_existing_escape() -> None:
    q = _hydrate({
        "query_id": "q1",
        "query_text": "test",
        "response_options": ["A. 轻", "B. 中", "C. 无法确定"],
    })
    # Already has escape, may just need ≥4
    assert len(q.response_options) >= 4
    assert any("无法确定" in opt for opt in q.response_options)


def test_padding_leaves_full_options_unchanged() -> None:
    opts = ["A. 重症肺炎", "B. 普通肺炎", "C. 呼吸衰竭", "D. 无法确定"]
    q = _hydrate({
        "query_id": "q1",
        "query_text": "test",
        "response_options": opts,
    })
    assert q.response_options == opts


def test_padding_handles_empty_options() -> None:
    q = _hydrate({
        "query_id": "q1",
        "query_text": "test",
        "response_options": [],
    })
    assert len(q.response_options) >= 4


def test_padding_handles_5_options_unchanged() -> None:
    opts = ["A. x", "B. y", "C. z", "D. w", "E. 无法确定"]
    q = _hydrate({
        "query_id": "q1",
        "query_text": "test",
        "response_options": opts,
    })
    assert q.response_options == opts
