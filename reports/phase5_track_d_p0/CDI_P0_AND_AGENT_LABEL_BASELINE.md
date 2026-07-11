# Gate 0 — CDI P0 + Agent Label Baseline Audit

**Date**: 2026-07-11
**Auditor**: Real code inspection (not report descriptions)
**Verdict entering Gate 0**: `READY_FOR_REMEDIATION` (multiple P0 blockers confirmed)

---

## Executive summary

Phase 5 Track D landed the CDI framework but 8 P0-class issues remain.
This audit verified each issue by reading actual code, not prior reports.
Findings below are the input to Gates 1-7.

The codebase is *honest*: stubs are clearly labeled, gaps are documented
in docstrings, and Gate 9 already returned 501 for unimplemented reads.
This means Gate 0 has a clean foundation — no hidden mocks disguised as
real calls.

## A. CDI P0 findings (8 issues)

### A1. CDI Runtime uses stub_runner in production path — CONFIRMED

**Evidence**: `backend/app/api/cdi.py:35,203`:

```python
from app.icoder.agent_runtime.cdi import (
    CDIOrchestrator,
    stub_runner,  # <-- imported
)
# ...
orchestrator = CDIOrchestrator(runner=stub_runner)  # <-- used in POST /runs
```

**Stub behavior** (`backend/app/icoder/agent_runtime/cdi/orchestrator.py:242`):

```python
def stub_runner(stage: str, case: CDICase, kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "encounter_synthesis": lambda: {"key_points": [], "encounter_metadata": {}},
        "gap_identification": lambda: {"gaps": []},
        "expert_consultation": lambda: {},
        "query_generation": lambda: {"queries": []},
        "specialist_trace_emit": lambda: {},
    }.get(stage, lambda: {})()
```

**Result**: every CDI run returns ZERO gaps, ZERO queries, ZERO trace.
`completion_state` is always `AUTO_PASS` because `documentation_gaps`
and `risk_flags` are always empty.

**PDF violation**: A1 (生产路径默认使用 stub_runner) + 8 (将 Stub 输出伪装为真实模型输出)

### A2. Expert/Capability is metadata-only — CONFIRMED

**Evidence**: CDI agent pack declares 4 Experts in `experts` array, but:

1. The orchestrator's `expert_consultation` stage calls
   `self.runner("expert_consultation", case, {})` which routes to
   `stub_runner` returning `{}`. No Expert invocation occurs.
2. `app.services.expert_runner.ExpertRunner` exists and is wired to
   real DeepSeek (`llm_service.chat_with_tools`), but the CDI
   orchestrator never calls it.
3. Specialist trace is empty for every run.

**PDF violation**: A2 (Expert/Capability 可能只是 Agent Pack 声明, 没有真实调用)

### A3. DB persistence is wired at schema level only — CONFIRMED

**Evidence**:

| Object | Migration 011 table | POST /runs writes? | GET reads? |
|---|---|---|---|
| CDI Case | `cdi_cases` ✓ | ✗ no write | ✗ 501 stub |
| Documentation Gap | `cdi_documentation_gaps` ✓ | ✗ no write | n/a |
| Provider Query | `cdi_provider_queries` ✓ | ✗ no write | n/a |
| Clinician Response | `cdi_clinician_responses` ✓ | ✗ no write | n/a |
| Document Version | `cdi_document_versions` ✓ | ✗ no write | n/a |
| Specialist Trace | (no table) | n/a | n/a |
| Risk Flag | (no table) | n/a | n/a |
| Audit Event | `audit_logs` ✓ (shared) | ✗ not used by CDI | n/a |
| Notification Subscription | (no table) | n/a | n/a |
| SLA state | (no table) | n/a | n/a |

DB row counts: `cdi_cases: 0, cdi_documentation_gaps: 0, cdi_provider_queries: 0, cdi_clinician_responses: 0, cdi_document_versions: 0`.

`GET /api/v1/cdi/runs/{case_id}` returns `501 not_implemented` (`backend/app/api/cdi.py`).

**PDF violation**: A3 (没有形成完整数据库持久化闭环) + 4 (接口返回成功但实际没有写入数据库)

### A4. NLQ Gate misses implicit leading queries — CONFIRMED

**Evidence**: `backend/app/icoder/agent_runtime/cdi/nlq_gate.py:36`:

```python
_YES_NO_OPENING_PATTERNS = [
    r"^\s*(是不是|是否|是否为|能否|能不能|是不是说)",  # <-- ^\s* anchors to sentence start
    ...
]
```

The regex requires the leading word to be at the start of the string
(allowing only whitespace before). PDF A4 example:

> 根据痰培养结果，该患者肺炎是否可以明确为肺炎链球菌性肺炎？

This passes NLQ-001 because "是否" is mid-sentence. **PDF requires BLOCK.**

Additionally:
- NLQ-002 (no_diagnosis_presumption) is a stub — always returns `passed=True`
- No structural rule checks for ICD/DRG codes embedded in response_options
- No semantic layer (LLM-based reviewer)

**PDF violation**: A4 (无法识别"是否可以明确为"等隐性诱导问法)

### A5. Evidence binding is single-span, not claim-aligned — CONFIRMED

**Evidence**: `backend/app/icoder/agent_runtime/cdi/domain.py`:

```python
@dataclass
class ProviderQuery:
    # ...
    evidence_span: EvidenceSpan  # singular, not list
```

`EvidenceSpan` is a single object per query. PDF A5 requires:

```python
evidence_spans: list[EvidenceSpan]  # multiple
# Each span has: document_id, quote, char_start, char_end, documented_at, supports_claim
# Query must specify supports_claim per span
# Claim-evidence alignment metric: claim_count, supported_claim_count,
# evidence_coverage_rate, unsupported_claims
```

Current NLQ-007 only checks `bool(query.evidence_quote)` — that's "any
evidence exists", not "every claim is supported".

**PDF violation**: A5 (Query 证据绑定可能只检查"有证据", 没有检查每个关键事实是否均被原文支持)

### A6. Clinician-facing UI leaks coding info — CONFIRMED

**Evidence**: `frontend/src/pages/CDIWorkbenchPage.tsx`:

- Line 135 (chart_excerpt context, shown in left pane):
  `'J18.9 (肺炎, 未特指) vs J13 (肺炎链球菌性肺炎) — 编码特异性差异'`
- Line 162 (response_option shown as radio button to clinician):
  `'A. 肺炎病原体为肺炎链球菌 (J13)'`
- Line 179 (specialist trace):
  `'J18.9 vs J13 编码特异性缺口已确认'`

**PDF violation**: A6 (医生端选项可能直接展示 ICD 编码、DRG、CMI 或编码收益信息)

### A7. Gap classifier has no unknown bucket — CONFIRMED

**Evidence**: `backend/app/icoder/agent_runtime/cdi/domain.py:classify_gap_type()`:

The function returns one of 8 known GapTypes. When no keyword matches,
behavior depends on the fallback — currently silent fall-through to
`diagnostic_specificity` (the first literal in the type). PDF A7
requires `unknown | other | needs_human_classification` with
`classification_confidence` + `classification_source` fields.

**PDF violation**: A7 (Gap 分类器在无法分类时可能默认归入 diagnostic_specificity)

### A8. Frontend production route uses SAMPLE_CASE — CONFIRMED

**Evidence**: `frontend/src/pages/CDIWorkbenchPage.tsx:116,216,218`:

```typescript
const SAMPLE_CASE: CDICase = { ... };  // line 116, hardcoded fixture
const [selectedCase] = useState<CDICase>(SAMPLE_CASE);  // line 216
const [selectedQueryId, setSelectedQueryId] = useState<string | null>(
  SAMPLE_CASE.proposed_provider_queries[0]?.query_id ?? null  // line 218
);
```

No `useEffect` fetching from `/api/v1/cdi/runs/{case_id}`. No action
button calls `POST /queries/{id}/transition`. The page is purely
decorative.

**PDF violation**: A8 (前端 CDI Workbench 可能仍依赖 SAMPLE_CASE, 按钮没有真正驱动后端工作流)

## B. Agent label findings

### B1. Engineering labels leak into user-visible UI — CONFIRMED

**Evidence scan** (raw strings):

| Field | Where it appears |
|---|---|
| `mvpBanner: 'MVP - production_ready=false, human_review=required'` | `frontend/src/i18n/locales.ts:1549` (zh), `:2839` (en) |
| `aiAssistedBanner: 'AI-assisted coding - 不替代编码员'` | `frontend/src/i18n/locales.ts:1550` (zh), `:2840` (en) |
| `agentCardProductionReadyFalse: 'production_ready=false'` | `frontend/src/i18n/locales.ts:2421` (zh), `:3700` (en) |
| `maturity: string` field exposed in card | `frontend/src/services/agentHubApi.ts:53` |
| `production_ready: boolean` exposed in card | `frontend/src/services/agentHubApi.ts:54` |
| `isMvp = card.runnable && !card.production_ready` | `frontend/src/pages/AgentsPage.tsx:411` |
| `!card.production_ready && (...)` shown as badge | `frontend/src/pages/AgentsPage.tsx:440` |
| `card.human_review === 'required'` shown as badge | `frontend/src/pages/AgentsPage.tsx:446` |
| `card.maturity` shown as text | `frontend/src/pages/AgentsPage.tsx:466` |

**PDF violation**: B1 + B3 (用户界面显示 MVP / AI-assisted / production_ready=false 等内部工程字段)

### B2. Pack metadata distribution (29 packs)

```
Maturity counts:
  metadata-only  15 packs
  mvp             8 packs (CDI, Medical Coding, Compliance, Discharge Structuring,
                          DRG, Evidence Extractor, Principal Diagnosis, Procedure)
  runnable        2 packs (Code Validation, Note Completeness)
  stub            3 packs (Code Reconciler, Index Navigator, Tabular Validator)
  internal        1 pack  (MedCoder Coding Review)

production_ready: false for all 29 packs (100%)
human_review: required=19, optional=2, (empty)=8
hidden_from_hub: 6 packs
deprecated: 2 packs (cdi-review, documentation-gap)
```

### B3. No unified status mapper — CONFIRMED

There is no `deriveAgentDisplayStatus()` function. Each page renders
badges inline based on raw `production_ready` / `maturity` /
`human_review` fields. Hub, Detail, and Workbench would diverge.

### B4. CDI display status today

Currently `maturity=mvp, production_ready=false, human_review=required`
→ on the user card shows: `MVP · production_ready=false · Human review required`.

**PDF-required display**: `预览版 · 发送前需审批` (2 badges max).

## C. Real LLM Gateway exists — confirmed reusable

`backend/app/services/llm_service.py` exposes:

```python
class LLMService:
    async def chat(messages, system_prompt, temperature, max_tokens, response_format) -> dict
    async def chat_with_tools(messages, tools, temperature) -> dict
    async def chat_stream(messages, temperature) -> AsyncIterator[str]
```

This is the real DeepSeek V4 client. Existing agents (note-completeness,
code-validation, etc.) already call it. CDI orchestrator just needs to
swap `stub_runner` → a real runner that invokes `llm_service.chat`.

## D. Test infrastructure already in place

- `backend/tests/conftest.py` provides `_make_mock_user(role)` for RBAC tests
- `ICODER_DISABLE_AUTH_FOR_TESTS=1` bypasses JWT in API tests
- 29 + 26 + 35 + 17 + 41 + 18 = 166 existing CDI tests pass
- `tests/unit/icoder/cdi/` directory structure ready for new suites

## E. Risk register (PDF §八 forbidden items recap)

| # | Forbidden action | Risk if violated |
|---|---|---|
| 1 | Delete production_ready=false to mask unfinished | high — would lie about maturity |
| 2 | Mark all agents as 可用 | high — users would trust stub outputs |
| 3 | Disguise stub as real model output | critical — patient safety |
| 4 | Pass acceptance with fixed SAMPLE_CASE | critical — false confidence |
| 5 | Only fix frontend labels, not state source | high — divergence returns |
| 6 | Add regex only, ignore implicit leading | high — false negative |
| 7 | Let clinicians see ICD/DRG/CMI | critical — leading by coding |
| 8 | Auto-modify hospital chart | critical — patient safety |
| 9 | Auto-send to real clinicians | critical — spam / patient safety |
| 10 | Auto production writeback | critical |
| 11 | Train models | critical — compliance violation |
| 12 | Declare CDI production-ready | critical — false verdict |
| 13 | Forge Corti mechanisms | high — false advertising |
| 14 | Hardcode test cases to pass | high — false confidence |

All 14 will be respected in subsequent gates.

## F. Gate-by-gate remediation plan

| Gate | Scope | Estimated effort | Key files |
|---|---|---|---|
| 1 | Label state model + deriveAgentDisplayStatus + i18n + Hub/Detail refactor | 3-4h | agentHubApi.ts, AgentsPage.tsx, AgentDetailPage.tsx, locales.ts, + new mapper module |
| 2 | Real LLM runner + Expert wiring + per-stage trace + DEGRADED state | 4-6h | orchestrator.py, expert_runner.py, cdi.py, + new real_runner.py |
| 3 | Repository + service layer for 11 object types + optimistic lock + transactional transitions | 4-6h | + new cdi_repository.py, cdi_service.py; rewrite cdi.py endpoints |
| 4 | 3-layer NLQ + multi-evidence schema + claim-evidence alignment + gap unknown + clinician de-coding | 4-6h | nlq_gate.py, domain.py, + new nlq_semantic.py |
| 5 | Remove SAMPLE_CASE + real API + loading/error/empty/degraded/stale states + role-aware action matrix + refresh-persistent | 4-6h | CDIWorkbenchPage.tsx, runtimeApi.ts |
| 6 | Browser E2E for 5 scenarios + screenshots | 2-3h | Playwright scripts |
| 7 | Final report + terminal output per PDF §11 | 1h | .md report |

**Total**: 22-32h, 7+ commits.

## G. Verdict entering remediation

```
============================================================
Gate 0 Baseline Audit — COMPLETE
============================================================
1. CDI Runtime Mode (today):          stub (production path)
2. Real LLM Provider (today):         not wired for CDI
3. Expert Calls Wired (today):        no (metadata-only)
4. Persistence (today):               schema only, 0 rows written
5. GET Case API (today):              501 Not Implemented
6. Query Lifecycle Persistence:       none (logic only)
7. Audit Dashboard:                   empty stub
8. Frontend Mock Removed:             no (SAMPLE_CASE in production)
9. NLQ 3-Layer Gate:                  1 layer (lexical, partial)
10. Hidden Leading Query Test:        would PASS (false negative)
11. Multi-Evidence Binding:           single span only
12. Clinician Coding Info Hidden:     no (J13/J18.9 visible)
13. Browser E2E:                       not yet run
14. Agent Status Mapper:              does not exist
15. Raw Engineering Labels Removed:   no (MVP / AI-assisted visible)
16. CDI Display Status:               MVP · production_ready=false · Human review
17. Backend Tests:                    166 pass (will need additions)
18. Frontend Tests:                   0 CDI-specific
19. E2E Tests:                        0 CDI-specific
20. Remaining Blockers:               8 P0 (A1-A8) + 2 label (B1, B3)
21. Final Verdict:                    READY_FOR_REMEDIATION (Gates 1-7 next)
============================================================
```

Next: Gate 1 — Label state model + unified mapper.
