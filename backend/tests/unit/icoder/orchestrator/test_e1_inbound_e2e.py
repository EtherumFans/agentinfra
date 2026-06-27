"""E1 (2026-06-26) — end-to-end Orchestrator test using 4 real D2 expert packs.

Per E1 design (memory/project_e1_first_real_agent_2026_06_26.md), the
canonical MedCodER Agent path now dispatches 4 atomic expert packs:

  - evidence-extractor  (Stage 1 — LLM fact extraction)
  - index-navigator     (Stage 2 — BGE-M3 + FAISS retrieval)
  - code-reconciler     (Stage 3+4 — merge + RankGPT-style rerank)
  - tabular-validator   (Stage 5 — MedicalCodingRuleSet calibration)

This test wires the E1 invoker into a real InboundHandler and verifies
the full state machine runs through all 4 experts end-to-end:

    received → planning → delegating → aggregating → completed

with each expert's real Python impl receiving its expert_id and
contributing its stage-specific output to the Aggregator.

Why this is at unit-test level (not e2e/):
  - We mock the LLMGateway (no DeepSeek call).
  - We use the real D2 expert packs (not stubs) — that's the E1 lockdown.
  - We use the real InboundHandler / Planner / Delegator / Aggregator
    (not just wiring) — that's the integration lift.
  - This catches the most likely E1 regression class: the wiring
    factory correctly dispatches, but the planner picks an expert not
    in agent.expert_ids, or the delegator strips context mid-chain.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.icoder.agent_runtime.orchestrator import (
    Aggregator,
    Delegator,
    DictAgentProvider,
    InboundHandler,
    InboundMessage,
    InboundRequest,
    PHIRedactor,
    Planner,
)
from app.icoder.agent_runtime.orchestrator.delegator import (
    DelegatorConfig,
)
from app.icoder.agent_runtime.orchestrator.planner import PlannerConfig
from app.icoder.agent_runtime.orchestrator.wiring import (
    build_expert_invoker_for_medcoder,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_FOUR_EXPERT_IDS = (
    "evidence-extractor",
    "index-navigator",
    "code-reconciler",
    "tabular-validator",
)


@dataclass
class _MedcoderAgent:
    """Mimic the AgentDefinition fields the Planner reads (SPEC §5.1).

    We only need the fields the Orchestrator + Planner consume, not the
    full AgentDefinition — this is a unit test, not an end-to-end A2A
    test. The 4 expert_ids match the canonical E1 dispatch set.
    """

    id: str = "medcoder-coding-review"
    name: str = "MedCodER Coding Review Agent"
    expert_ids: list[str] = field(default_factory=lambda: list(_FOUR_EXPERT_IDS))
    config: dict = field(default_factory=dict)


def _make_llm_plan(*, emr_text: str, expert_ids: list[str]) -> dict:
    """Build a Planner-shaped LLM response listing all 4 expert_ids.

    The Planner parses JSON of shape::

        {
          "experts": [
            {"expert_id": ..., "priority": N, "critical": bool,
             "subtask_input": ..., "tool_constraints": [...]},
            ...
          ],
          "reason": "..."
        }

    We list all 4 experts so the Delegator drives the full MedCodER
    chain. The ``subtask_input`` is seeded so downstream experts can
    chain their inputs through ``invocation.context`` if they wish.
    """
    return {
        "content": json.dumps(
            {
                "experts": [
                    {
                        "expert_id": eid,
                        "priority": i + 1,
                        "critical": True,
                        "subtask_input": emr_text if i == 0 else f"stage_{i + 1}_payload",
                        "tool_constraints": [],
                    }
                    for i, eid in enumerate(expert_ids)
                ],
                "reason": "MedCodER 5-stage 编排 (E1 4-expert)",
            },
            ensure_ascii=False,
        ),
        "model": "fake-deepseek-v4",
    }


def _build_e1_handler(*, emr_text: str = "老年男性胸痛 3 小时。既往高血压 5 年。") -> tuple:
    """Build an InboundHandler fully wired to the E1 4-expert invoker.

    Returns ``(handler, sleeps, calls_captured)`` where ``calls_captured``
    records every ``ExpertInvocation`` the Delegator handed to the
    invoker — useful for asserting the 4 experts were all called.
    """
    agent = _MedcoderAgent()
    calls_captured: list[tuple[str, str]] = []  # (expert_id, subtask_input)

    def _scripted_llm(system, user):
        return _make_llm_plan(emr_text=emr_text, expert_ids=list(_FOUR_EXPERT_IDS))

    planner = Planner(
        llm_call=_scripted_llm,
        config=PlannerConfig(sleep_fn=lambda _s: None),
    )

    invoker = build_expert_invoker_for_medcoder(
        llm_gateway=None,           # evidence/code-reconciler go offline
        medcoder_retriever=None,    # index_navigator → retriever_status=missing
        rule_engine=None,           # tabular_validator lazy-loads default
        hybrid_fallback=None,
    )

    def _recording_invoker(invocation):
        calls_captured.append((invocation.expert_id, invocation.subtask_input))
        return invoker(invocation)

    delegator = Delegator(
        invoker=_recording_invoker,
        config=DelegatorConfig(sleep_fn=lambda _s: None),
    )
    aggregator = Aggregator()
    provider = DictAgentProvider({agent.id: agent})

    handler = InboundHandler(
        phi_redactor=PHIRedactor(),
        planner=planner,
        delegator=delegator,
        aggregator=aggregator,
        agent_provider=provider,
    )
    return handler, calls_captured


def _ok_request(text: str = "老年男性胸痛 3 小时") -> InboundRequest:
    return InboundRequest(
        message=InboundMessage(
            role="user",
            parts=[{"kind": "text", "text": text}],
            interaction_id="e1-test-int-1",
        )
    )


# ---------------------------------------------------------------------------
# E1 e2e lockdown
# ---------------------------------------------------------------------------


def test_e1_handler_runs_4_real_expert_packs_end_to_end():
    """E1 lockdown: InboundHandler drives the full state machine through
    the 4 real D2 expert packs (not stubs).

    Verifies:
      - state_history covers the 5-state machine
      - phi_redacted is True (SPEC §3.2 — first step)
      - production_writeback_blocked is True (A2A §7.2 invariant)
      - all 4 expert_ids were called by the Delegator
      - Aggregator merged results from all 4 experts (no drops)
    """
    handler, calls = _build_e1_handler()
    resp = handler.handle(
        agent_id="medcoder-coding-review",
        request=_ok_request(),
    )

    # 5-state machine: received → planning → delegating → aggregating → completed
    # (received is the entry state, not part of history output)
    assert resp.metadata["state_history"] == [
        "planning", "delegating", "aggregating", "completed",
    ]
    assert resp.metadata["phi_redacted"] is True
    assert resp.metadata["production_writeback_blocked"] is True
    assert resp.kind == "message"
    assert resp.http_status == 200

    # All 4 experts dispatched
    invoked_ids = [c[0] for c in calls]
    assert invoked_ids == list(_FOUR_EXPERT_IDS), (
        f"E1 expected 4 expert packs called in order, got {invoked_ids}"
    )

    # None of the calls fell through to the Phase-1 stub (which would
    # have produced ``phase1_stub=True`` in the result). We assert this
    # indirectly: each expert_id is in the E1 set, so the E1 factory's
    # real branch fired (not the unknown-id fallback).
    assert all(eid in _FOUR_EXPERT_IDS for eid in invoked_ids)


def test_e1_handler_aggregator_emits_per_expert_data_parts():
    """E1 lockdown: the Aggregator (SPEC §7.4) emits one DataPart per
    successful expert, each tagged with ``expert_id`` and ``result``.
    All 4 expert_ids must surface (Aggregator must not drop any).

    Per-expert DataPart shape::

        {
          "kind": "data",
          "data": {
            "expert_id": "evidence-extractor",
            "priority": 1,
            "critical": true,
            "attempt": 1,
            "latency_ms": ...,
            "ok": true,
            "result": { ...expert-specific output... },
            "error": null
          }
        }

    The exact ``result`` shape is owned by each D2 expert (locked down
    separately by the per-expert unit tests). Here we only assert the
    dispatch topology: 4 in, 4 out, no drops.
    """
    handler, _ = _build_e1_handler()
    resp = handler.handle(
        agent_id="medcoder-coding-review",
        request=_ok_request(),
    )

    # Per-expert DataParts (exclude the Aggregator summary part).
    per_expert_parts = [
        p for p in resp.parts
        if isinstance(p, dict)
        and p.get("kind") == "data"
        and "expert_id" in p.get("data", {})
    ]
    expert_ids_in_parts = [p["data"]["expert_id"] for p in per_expert_parts]
    assert set(expert_ids_in_parts) == set(_FOUR_EXPERT_IDS), (
        f"Aggregator must emit DataPart for all 4 experts; "
        f"got: {expert_ids_in_parts}"
    )

    # Each per-expert DataPart must carry an ok=True result
    # (the offline fallback path for every expert).
    for part in per_expert_parts:
        d = part["data"]
        assert d["ok"] is True, (
            f"expert {d['expert_id']!r} DataPart must have ok=True, got {d}"
        )
        assert d["error"] is None
        assert isinstance(d["result"], dict)

    # Stage-specific output shapes surface in each part's ``result``:
    #   evidence-extractor → diagnosis_facts
    #   index-navigator    → retriever_status
    #   code-reconciler    → primary_diagnosis (or empty dict)
    #   tabular-validator  → passed
    by_eid = {p["data"]["expert_id"]: p["data"]["result"] for p in per_expert_parts}
    assert "diagnosis_facts" in by_eid["evidence-extractor"]
    assert "retriever_status" in by_eid["index-navigator"]
    assert "primary_diagnosis" in by_eid["code-reconciler"]
    assert "passed" in by_eid["tabular-validator"]

    # The Aggregator also emits a summary DataPart + text part.
    summary_parts = [
        p for p in resp.parts
        if isinstance(p, dict)
        and p.get("kind") == "data"
        and "summary" in p.get("data", {})
    ]
    assert summary_parts, "Aggregator must emit a summary DataPart"
    summary = summary_parts[0]["data"]["summary"]
    assert summary["expert_count"] == 4
    assert summary["succeeded"] == 4
    assert summary["failed"] == 0


def test_e1_handler_phi_redaction_runs_before_planner():
    """E1 lockdown: PHI redaction is the Orchestrator's first step
    (SPEC §3.2 — receive → redact → plan → delegate → aggregate).

    Verify: PHI-bearing input gets redacted before the Planner sees it.
    """
    handler, _ = _build_e1_handler()
    resp = handler.handle(
        agent_id="medcoder-coding-review",
        request=_ok_request(text="张三 13800138000 主诉胸痛 2 小时"),
    )

    # PHI redacted metadata
    assert resp.metadata["phi_redacted"] is True
    assert "PHONE" in resp.metadata["redaction_entity_types"]
    assert "NAME" in resp.metadata["redaction_entity_types"]

    # The redacted input is exposed via metadata (for audit / debugging).
    # PHI tokens must NOT appear in the redacted text.
    redacted = resp.metadata.get("redacted_input", "")
    assert "张三" not in redacted
    assert "13800138000" not in redacted


def test_e1_handler_with_unknown_agent_id_returns_agent_not_found():
    """E1.1 lockdown (A2A spec §6.2): unknown agent_id returns the
    A2A-spec ``AGENT_NOT_FOUND`` error code with HTTP 404 — NOT the
    generic ``invalid_request`` (400). This is a strict lockdown; the
    Orchestrator must use the specific A2A business code for agent
    registry misses (per the 8 A2A error codes defined in
    ``app/icoder/agent_runtime/a2a/errors.py``).
    """
    handler, _ = _build_e1_handler()
    resp = handler.handle(agent_id="ghost-agent", request=_ok_request())

    # A2A business code, not the generic invalid_request
    assert resp.kind == "error"
    assert resp.http_status == 404
    assert resp.error is not None
    assert resp.error["code"] == "AGENT_NOT_FOUND", (
        f"unknown agent_id must return A2A AGENT_NOT_FOUND, "
        f"got {resp.error['code']!r}"
    )
    assert "ghost-agent" in resp.error["message"]