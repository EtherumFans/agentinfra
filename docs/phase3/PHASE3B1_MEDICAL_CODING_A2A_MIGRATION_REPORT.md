# Phase 3-B1 Section D — Medical Coding Agent A2A Mainline Migration Report

**Date**: 2026-07-04
**Status**: COMPLETE — Medical Coding Agent runs through A2A InboundHandler mainline; 12/12 contract tests pass; 38/38 Phase 3-B1 cumulative tests pass (B+C+D)

## D.1 Problem

Before Section D, the Medical Coding Agent had two parallel run paths:

1. **Legacy `/api/runtime-platform/agents/{ref}/run`** — called `HybridCodingAdapter` directly (5-stage MedCodER pipeline), bypassed the A2A InboundHandler, and returned the v1 `MedicalCodingOutputSchema` (technical 5-stage output).
2. **A2A `/api/icoder/agents/{agent_id}/v1/message:send`** — the canonical A2A mainline, but only `medcoder-coding-review` (the internal engine) was registered. `medical-coding-agent` (the user-facing MVP) had **no A2A card factory**, so it 404'd at `agent_not_found`.

The Corti-style 8-field contract (`MedicalCodingAgentOutputV2`) was defined in `official_agents/medical_coding/schema.py` but **never produced on the A2A mainline** — it existed only as a Python dataclass with no wiring.

## D.2 Solution

Section D adds three changes that together route Medical Coding Agent through the A2A mainline with the 8-field output contract.

### D.2.1 `medical_coding_agent_card()` factory (agent_card.py)

Added the second public card factory alongside `medcoder_coding_review_card()`:

```python
def medical_coding_agent_card(base_url: str = "") -> AgentCard:
    return AgentCard(
        name="Medical Coding Agent (Corti-style MVP)",
        description="Hospital revenue compliance coding with Corti 7-step workflow.",
        url="/api/icoder/agents/medical-coding-agent/v1/message:send",
        version="2.0.0",
        provider={"name": "iCoDer"},
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False, stateTransitionHistory=True),
        skills=[Skill(id="corti_7_step_workflow", name="Corti 7-step workflow", ...)],
        metadata={
            "icoder": {
                "agent_ref": "icoder/medical-coding-agent@2.0.0",
                "rule_sets": ["medical_coding"],
                "experts": ["coding-expert"],
                "internal_engine": "medcoder-coding-review",
                "non_goals": [...],
                "production_writeback_blocked": True,
                "phi_redaction": "required",
                "no_upcoding": True,
                "no_inference": True,
                "evidence_required": True,
                "human_review": "required",
                "maturity": "mvp",
                "production_ready": False,
                "output_contract": {
                    "schema": "icoder/MedicalCodingAgentOutputV2/v1",
                    "required_fields": [
                        "encounter_summary", "documentation_analysis", "code_assignment",
                        "documentation_gaps", "uncodable_items", "validation_summary",
                        "human_review", "trace_refs",
                    ],
                },
            }
        },
    )
```

### D.2.2 `_list_all_cards()` enumerates BOTH agents (routes_discovery.py)

The discovery router previously enumerated only `medcoder-coding-review`. Now it enumerates both agents via the provider-or-factory fallback:

```python
def _list_all_cards(provider: AgentProvider) -> list[AgentCard]:
    cards: list[AgentCard] = []
    for agent_id, factory in [
        ("medcoder-coding-review", medcoder_coding_review_card),
        ("medical-coding-agent", medical_coding_agent_card),
    ]:
        card = _resolve_card(provider, agent_id)
        if card is None:
            card = factory()
        cards.append(card)
    return cards
```

This closes the Section C gate test `test_medical_coding_agent_appears_in_a2a_after_section_d`.

### D.2.3 `_MedicalCodingV2ProjectingHandler` wrapper (main.py)

The coding-expert returns v1 `MedicalCodingOutputSchema` (MedCodER 5-stage technical output) for both `medcoder-coding-review` and `medical-coding-agent`. But `medical-coding-agent` is the user-facing MVP — it must return the v2 8-field `MedicalCodingAgentOutputV2` per the Corti contract.

The wrapper sits between `InboundHandler` and the route, projects v1 → v2 only for `medical-coding-agent`, and passes v1 through for `medcoder-coding-review` (internal engine, no projection):

```python
class _MedicalCodingV2ProjectingHandler:
    def __init__(self, inner):
        self._inner = inner

    def handle(self, agent_id, request):
        response = self._inner.handle(agent_id, request)
        if agent_id == "medical-coding-agent" and response.kind == "message":
            response = self._project_v1_to_v2(response)
        return response

    def _project_v1_to_v2(self, response):
        # For each data part, detect v1 shape (has primary_diagnosis /
        # extracted_diagnoses / review_conclusion), build MedicalCodingOutputSchema
        # from it, project to MedicalCodingAgentOutputV2, replace the part.
        # Orchestrator trace fields (expert_id, latency_ms) move into part.metadata.
        # Response metadata gets v1_to_v2_projected=true +
        # output_contract=icoder/MedicalCodingAgentOutputV2/v1.
```

The InboundHandler's Aggregator wraps each expert result as `part.data = {"expert_id": ..., "result": <v1 schema>, ...}`. The wrapper inspects `data["result"]` for v1 markers (preferred) or `data` itself (back-compat for flat v1 parts).

### D.2.4 Bug fix in `_parse_evidence` (schema.py)

Discovered during testing: `EvidenceSpan.from_dict(item)` raised `'EvidenceSpan' object has no attribute 'get'` when `item` was already an `EvidenceSpan` (not a dict). The bug was in `_parse_evidence`:

```python
# Before (buggy):
def _parse_evidence(raw: list) -> list:
    spans = []
    for item in raw or []:
        spans.append(EvidenceSpan.from_dict(item))  # fails if item is EvidenceSpan
    return spans

# After (idempotent):
def _parse_evidence(raw: list) -> list:
    spans = []
    for item in raw or []:
        if isinstance(item, EvidenceSpan):
            spans.append(item)
        else:
            spans.append(EvidenceSpan.from_dict(item))
    return spans
```

This bug only surfaced when the projection wrapper called `from_legacy_v1(legacy)` on a v1 schema whose `extracted_diagnoses` already had `EvidenceSpan` objects (the typical runtime path). The legacy `/run` path never hit it because it never called `from_legacy_v1`.

## D.3 Files changed

| File | Change | LOC |
|---|---|---|
| `backend/app/icoder/agent_runtime/a2a/agent_card.py` | Added `medical_coding_agent_card()` factory | +85 |
| `backend/app/icoder/agent_runtime/a2a/routes_discovery.py` | `_list_all_cards()` enumerates BOTH agents (provider-or-factory) | +12 / -3 |
| `backend/app/main.py` | Extended `_phase1_agent_provider` + `_build_phase1_agent_provider` to register `_medical_agent` AgentDefinition (with system_prompt + experts=[coding-expert] + version=2.0.0 + output_contract=MedicalCodingAgentOutputV2, enriched from medical_coding/agent_pack.json); added `_MedicalCodingV2ProjectingHandler` wrapper class | +130 |
| `backend/official_agents/medical_coding/schema.py` | `_parse_evidence` idempotent fix (handles EvidenceSpan input) | +3 / -1 |
| `backend/tests/integration/icoder/test_phase3b1_medical_coding_a2a_migration.py` | **new** — 12 contract tests | +366 |
| **Total** | | **+596 / -4** |

## D.4 Tests added (12 new tests, all pass)

| Test | Verifies | Status |
|---|---|---|
| `test_a2a_medical_coding_agent_endpoint_accepts_request` | POST `/api/icoder/agents/medical-coding-agent/v1/message:send` accepts well-formed A2A envelope; HTTP not 404 | ✅ |
| `test_a2a_medical_coding_agent_appears_in_discovery` | A2A discovery `/api/icoder/agents` returns medical-coding-agent (Section C gate closed) | ✅ |
| `test_a2a_medical_coding_agent_card_url_points_to_canonical_path` | AgentCard url = `/api/icoder/agents/medical-coding-agent/v1/message:send`, version=2.0.0, output_contract.required_fields has 8 Corti fields | ✅ |
| `test_a2a_medical_coding_agent_returns_v2_8_fields_on_success` | Response parts contain a DataPart with all 8 v2 fields (encounter_summary, documentation_analysis, code_assignment, documentation_gaps, uncodable_items, validation_summary, human_review, trace_refs) | ✅ |
| `test_a2a_medical_coding_agent_red_lines_in_metadata` | AgentCard metadata has 4 red lines (no_upcoding, no_inference, evidence_required, production_writeback_blocked) + phi_redaction=required + human_review=required + maturity=mvp + production_ready=false | ✅ |
| `test_a2a_medical_coding_agent_response_red_lines` | Response metadata has phi_redacted=true + production_writeback_blocked=true (red lines enforced in run path) | ✅ |
| `test_a2a_medical_coding_agent_state_history_in_metadata` | Response metadata has state_history with all 4 A2A mainline states (planning, delegating, aggregating, completed); state machine records transitions (initial "received" implicit as from_state of first transition) | ✅ |
| `test_a2a_unknown_agent_returns_agent_not_found` | Unknown agent_id returns 404 + JSON-RPC error code AGENT_NOT_FOUND (-32601) | ✅ |
| `test_a2a_medical_coding_agent_missing_protocol_version_returns_400` | Missing A2A-Protocol-Version header returns 400 (parse error) — honest degraded state, no silent mock | ✅ |
| `test_a2a_medical_coding_agent_malformed_body_returns_parse_error` | Malformed JSON-RPC body returns parse error (400), not silent mock | ✅ |
| `test_a2a_medical_coding_agent_v1_to_v2_projection_metadata` | Response metadata has v1_to_v2_projected=true + output_contract=icoder/MedicalCodingAgentOutputV2/v1 (projection wrapper ran) | ✅ |
| `test_a2a_medcoder_coding_review_not_projected_to_v2` | medcoder-coding-review (internal engine) response does NOT have v1_to_v2_projected=true (projection only runs for medical-coding-agent) | ✅ |

**Result**: 12/12 PASS.

## D.5 Cumulative regression — 38/38 Phase 3-B1 tests pass

| Suite | Tests | Status |
|---|---|---|
| Section B (Agent Hub restoration) | 13 | ✅ 13/13 |
| Section C (Discovery unification contract) | 13 | ✅ 13/13 (gate test now passes) |
| Section D (Medical Coding A2A migration) | 12 | ✅ 12/12 |
| **Total** | **38** | ✅ **38/38** |

## D.6 State machine history clarification

The InboundHandler serializes `state_history` as `[h.to_state for h in sm.state_history]`. The state machine records **transitions** (not the initial state). The first transition is `received → planning`, so `to_state = "planning"`. The initial `received` is the implicit `from_state` of the first transition.

Result: `state_history = ["planning", "delegating", "aggregating", "completed"]` for a successful run. The test asserts all 4 are present and `state_history[0] == "planning"`.

## D.7 v1 → v2 projection path

```
[Client POST]
    ↓
[/api/icoder/agents/medical-coding-agent/v1/message:send]
    ↓
[routes_inbound._dispatch]
    ↓ validate_version_header (A2A-Protocol-Version: 0.3)
    ↓ parse_request (JSON-RPC envelope)
    ↓ parse_params (params.message)
    ↓ build InboundRequest
    ↓ to_thread(handler.handle, agent_id, inbound_req)
    ↓
[_MedicalCodingV2ProjectingHandler.handle(agent_id="medical-coding-agent", request)]
    ↓ inner = InboundHandler.handle(agent_id, request)
    │   ↓ PHIRedactor.redact(request.message.parts)
    │   ↓ Planner.plan(interaction) → plan.reason, expert_delegations
    │   ↓ Delegator.delegate(expert_delegations, run_ctx)
    │   │   ↓ build_expert_invoker_for_medcoder → coding-expert.invoke()
    │   │   │   ↓ HybridCodingAdapter.infer_async → MedCodERStrategy 5-stage
    │   │   │   ↓ Returns MedicalCodingOutputSchema (v1, 5-stage technical)
    │   │   ↓ expert_result.result = v1 schema
    │   ↓ Aggregator.aggregate(expert_results)
    │   │   ↓ parts = [{"kind":"data","data":{"expert_id":..., "result":<v1>, ...}}, {"kind":"data","data":{"summary":...}}, {"kind":"text","text":...}]
    │   ↓ state_history = ["planning", "delegating", "aggregating", "completed"]
    │   ↓ return InboundResponse(kind="message", parts=parts, metadata={..., state_history, phi_redacted=true, production_writeback_blocked=true})
    ↓ response.kind == "message" → project_v1_to_v2(response)
    ↓ For each data part with v1 markers (data.result has extracted_diagnoses etc.):
    │   ↓ v1 = MedicalCodingOutputSchema.from_dict(data["result"])
    │   ↓ v2 = MedicalCodingAgentOutputV2.from_legacy_v1(v1, run_id=...)
    │   ↓ replace part with {"kind":"data", "data":v2.to_dict(), "metadata":{"schema_ref":..., "projected_from":..., "phi_redacted":true, "production_writeback_blocked":true, "orchestrator_expert_id":..., ...}}
    ↓ response.metadata["v1_to_v2_projected"] = True
    ↓ response.metadata["output_contract"] = "icoder/MedicalCodingAgentOutputV2/v1"
    ↓ return projected response
    ↓
[_serialize_response → JSON-RPC success envelope → HTTP 200]
```

For `medcoder-coding-review`, the wrapper passes v1 through unchanged (no projection).

## D.8 Prompt success criteria mapping

| Prompt §D requirement | Implementation | Test |
|---|---|---|
| 1. `/api/icoder/agents/medical-coding-agent/v1/message:send` is the canonical A2A run path | D.2.1 + D.2.2 (card factory + discovery enumerate) | `test_a2a_medical_coding_agent_endpoint_accepts_request` ✅; `test_a2a_medical_coding_agent_card_url_points_to_canonical_path` ✅ |
| 2. A2A discovery returns Medical Coding Agent | D.2.2 (`_list_all_cards` enumerates both) | `test_a2a_medical_coding_agent_appears_in_discovery` ✅; Section C gate `test_medical_coding_agent_appears_in_a2a_after_section_d` ✅ |
| 3. Run path through InboundHandler (PHI redaction → Planner → Delegator → Aggregator) | D.2.3 (wrapper sits on top of InboundHandler, which already runs the full state machine) | `test_a2a_medical_coding_agent_state_history_in_metadata` ✅ (verifies planning→delegating→aggregating→completed) |
| 4. MedicalCodingAgentOutputV2 8 fields preserved in response | D.2.3 (wrapper projects v1→v2; replaces data part with v2.to_dict()) | `test_a2a_medical_coding_agent_returns_v2_8_fields_on_success` ✅ |
| 5. Phase 3-A red lines preserved (no_upcoding, human_review=required, production_writeback_blocked, phi_redacted) | D.2.1 (card metadata declares all 4 red lines + phi_redaction=required + human_review=required) + D.2.3 (response metadata has phi_redacted=true, production_writeback_blocked=true) | `test_a2a_medical_coding_agent_red_lines_in_metadata` ✅; `test_a2a_medical_coding_agent_response_red_lines` ✅ |
| 6. RunTrace records A2A state_history | D.2.3 (InboundHandler already populates state_history in metadata; wrapper preserves it) | `test_a2a_medical_coding_agent_state_history_in_metadata` ✅ |
| 7. Unknown agent returns AGENT_NOT_FOUND (404) | A2A spec §6.2 (already implemented in routes_inbound) | `test_a2a_unknown_agent_returns_agent_not_found` ✅ |
| 8. Missing config returns honest error (no silent mock) | A2A spec §6.1 (parse_error for missing protocol version + malformed body) | `test_a2a_medical_coding_agent_missing_protocol_version_returns_400` ✅; `test_a2a_medical_coding_agent_malformed_body_returns_parse_error` ✅ |
| 9. medcoder-coding-review (internal engine) NOT projected to v2 | D.2.3 (wrapper projects only for agent_id == "medical-coding-agent") | `test_a2a_medcoder_coding_review_not_projected_to_v2` ✅ |

## D.9 Verdict

**Section D verdict**: PASS — Medical Coding Agent runs through A2A InboundHandler mainline (PHI redaction → Planner → Delegator → Aggregator → state machine history); 8-field `MedicalCodingAgentOutputV2` is projected from v1 on the response; 4 Corti red lines enforced in both card metadata and response metadata; 12/12 contract tests pass; 38/38 cumulative Phase 3-B1 tests pass (B+C+D); state machine behavior documented; v1→v2 projection path documented.

The Medical Coding Agent is now invokable via the canonical A2A path `/api/icoder/agents/medical-coding-agent/v1/message:send` with the Corti-style 8-field output contract. The legacy `/run` bypass is no longer needed for Medical Coding Agent (Section E will classify its disposition).
