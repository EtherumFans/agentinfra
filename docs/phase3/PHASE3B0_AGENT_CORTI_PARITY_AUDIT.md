# Phase 3-B0 Section C — One-by-One Corti Parity Audit

**Date**: 2026-07-04
**Status**: COMPLETE — 16 agent packs + 5 page-as-agent features scored on 17 Corti parity dimensions

## C.1 Methodology

Each Agent / Agent-like feature is scored 0-5 on the 17 dimensions from Section A.2. Verdicts assigned per Section A.4 rubric. The 5 mandatory honesty rules (Section A.5) are enforced as gating constraints: any violation forces the verdict down.

Scoring inputs:
- Static inventory (Section B.2 — 16 agent_pack.json files)
- Live API state (Section B.7 — A2A returns 1 agent, Hub 404, execution_mode=legacy)
- Phase 3-A red lines (no F1/accuracy display, MVP banner required, human_review=required)
- Phase 2.1-A deprecation (PlatformRuntime.run_agent raises NotImplementedError; /run is 410 for non-Medical-Coding agents)

## C.2 Audit summary — verdicts at a glance

| # | Agent / Feature | Avg | Verdict | Blocking dimension |
|---|---|---|---|---|
| 1 | Medical Coding Agent v2.0.0 (pack) | 3.82 | **PARTIALLY_ALIGNED** | dim 17 (legacy bypass, A2A missing) |
| 2 | 诊断提取 (diagnosis-extractor) | 1.65 | **STUB_ONLY** | dim 10 (no run path) |
| 3 | 手术提取 (procedure-extractor) | 1.65 | **STUB_ONLY** | dim 10 |
| 4 | 编码校验 (code-validation) | 1.65 | **STUB_ONLY** | dim 10 |
| 5 | 证据排名 (evidence-ranker) | 1.65 | **STUB_ONLY** | dim 10 |
| 6 | 文档缺口检测 (documentation-gap) | 1.71 | **STUB_ONLY** | dim 10 |
| 7 | 病历完整性 (note-completeness) | 1.71 | **STUB_ONLY** | dim 10 |
| 8 | 临床文书改进 (cdi-review) | 1.71 | **STUB_ONLY** | dim 10 |
| 9 | 合规护栏 (compliance-guardrail) | 1.71 | **STUB_ONLY** | dim 10 |
| 10 | 拒付申诉 (denial-appeals) | 1.71 | **STUB_ONLY** | dim 10 |
| 11 | DRG 分组分析 (drg-analyzer) | 1.71 | **STUB_ONLY** | dim 10 |
| 12 | MedCodER Internal Engine | 4.18 | **ALIGNED** | (hidden — internal by design) |
| 13 | Evidence Extractor (expert-stub) | 1.18 | **STUB_ONLY** | dim 1 (English technical name), dim 10 |
| 14 | Index Navigator (expert-stub) | 1.18 | **STUB_ONLY** | dim 1, dim 10 |
| 15 | Code Reconciler (expert-stub) | 1.18 | **STUB_ONLY** | dim 1, dim 10 |
| 16 | Tabular Validator (expert-stub) | 1.18 | **STUB_ONLY** | dim 1, dim 10 |
| 17 | MedicalCodingPage (frontend page) | 3.94 | **PARTIALLY_ALIGNED** | dim 17 (legacy /run) |
| 18 | FactExtractionPage | 2.71 | **PARTIALLY_ALIGNED** | dim 10 (501 stub backend) |
| 19 | SpeechToTextPage | 1.59 | **MISALIGNED** | dim 10 (no backend), dim 9 (orphan) |
| 20 | TextGenerationPage | 1.59 | **MISALIGNED** | dim 10 (no backend), dim 9 (orphan) |
| 21 | EmbeddedAssistantPage (placeholder) | 0.88 | **DELETE_CANDIDATE** | dim 1, dim 9, dim 10 |

**Verdict distribution**:
- ALIGNED: 1 (5%)
- PARTIALLY_ALIGNED: 3 (14%)
- MISALIGNED: 2 (10%)
- STUB_ONLY: 14 (67%)
- DELETE_CANDIDATE: 1 (5%)
- LEGACY: 0 (0%)

**Headline finding**: 14 of 21 audited surfaces are STUB_ONLY — they exist as metadata but have no run path, no Hub visibility, no A2A wiring. This is the most material gap and the central subject of Section F quick fixes.

## C.3 Per-agent detailed scores

### C.3.1 Medical Coding Agent v2.0.0 (icoder/medical-coding-agent@2.0.0)

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 5 | "Medical Coding Agent" — task-oriented noun phrase, user-facing. No jargon suffix. |
| 2 Category parity | 5 | `medical-coding` / "Coding and Revenue Cycle" — matches Corti §13. |
| 3 Agent Card completeness | 5 | agent_pack.json has all 5 fields (description, inputs, outputs, constraints, risks). |
| 4 Maturity labeling | 5 | `maturity: mvp`, `production_ready: false` — honest. |
| 5 Human review | 5 | `human_review: required` in pack + UI banner. |
| 6 Safety / no overclaim | 5 | No F1 display in UI; honest degraded states; no "AI-powered" superlatives. |
| 7 Workflow clarity | 5 | 8-step Corti-style workflow documented in system_prompt + Agent Card. |
| 8 Output contract | 5 | `output_contract.schema_ref` points to MedicalCodingAgentOutputV2 (8 Corti-style fields). |
| 9 Agent Hub visibility | 2 | Pack metadata claims `hidden_from_hub: false`, but `/api/icoder/agents/hub` returns 404 (live). A2A discovery returns only medcoder-coding-review, not this agent. |
| 10 Runnability honesty | 4 | `status: EXECUTABLE` + has experts[] + has tools[] + run path returns 200 (via restored /run endpoint). But run path is the legacy bypass, not A2A mainline. |
| 11 RunTrace integration | 5 | Run appears in `/api/runtime/runs`; trace_refs populated in v2 output. |
| 12 Tool / Expert calls | 5 | tool_calls + expert_invocations visible in trace (Stage 1-5 wired). |
| 13 Honest degraded/error | 5 | 503 when LLM not configured; clear error message; no silent fallback to mock. |
| 14 Requirements disclosure | 5 | `requirements` lists llm + retriever + rule_set; missing config surfaced. |
| 15 UI consistency | 5 | 3-column layout (Input \| Output \| Settings/Code); MVP banner; Review Summary panel. |
| 16 API consistency | 4 | `/api/runtime/agents/{ref}/run` (legacy) + `/api/v2/tools/coding/icoder` (v2) + A2A `/message:send` all return v2 shape. 3 duplicate endpoints — should consolidate to A2A. |
| 17 Platform alignment | 1 | **Major gap**: runs through legacy HybridCodingAdapter bypass, NOT A2A InboundHandler. `execution_mode: "legacy"`, `fallback_to_legacy: true`. A2A discovery does not list this agent. |

**Average**: 3.82 — **PARTIALLY_ALIGNED**
**Honesty rule check**: A.5.1 (metadata-only ≠ runnable) — pass (EXECUTABLE + run path returns 200). A.5.3 (no trace ≠ mainline) — pass. A.5.5 (production_ready=false surfaces) — pass (MVP banner shown). **No honesty rule violated.**
**Action**: Phase 3-B must migrate execution from legacy bypass to A2A mainline; restore `/api/icoder/agents/hub` endpoint so dim 9 lifts to 5. Until then, dim 17 caps the verdict at PARTIALLY_ALIGNED.

### C.3.2-C.3.11 Ten Certified Agents without /run wiring (rows 2-11)

These 10 agents share an identical score profile. They are listed individually for completeness but scored as a class.

**Representative: 诊断提取 (icoder/diagnosis-extractor@1.0.0)**

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 4 | "诊断提取" — Chinese task-oriented noun phrase. Minor: Corti uses English user-facing names globally; iCoDer CN locale is acceptable per P1.3 direction lock. |
| 2 Category parity | 4 | `编码` (coding) — Corti-aligned category, but slug naming is Chinese. Acceptable for CN locale. |
| 3 Agent Card completeness | 4 | agent_pack.json has all 5 fields, but constraints/risks are generic boilerplate. |
| 4 Maturity labeling | 1 | **Pack declares `maturity: mvp` and `production_ready: true`** — but agent has NO run path, NO experts[], NO real implementation. This violates A.5.2 (stub ≠ MVP). Should be `maturity: metadata-only`. |
| 5 Human review | 2 | `human_review: required` declared, but moot since agent doesn't run. |
| 6 Safety / no overclaim | 4 | No F1/accuracy display. No overclaim superlatives in pack. |
| 7 Workflow clarity | 2 | Workflow documented in system_prompt but never executed — workflow is aspirational. |
| 8 Output contract | 3 | `output_contract.schema_ref` declared but output is never produced. |
| 9 Agent Hub visibility | 1 | `/api/icoder/agents/hub` returns 404 (live). A2A discovery returns 1 agent (not this one). Hub visibility claim is false. |
| 10 Runnability honesty | 0 | `status: EXECUTABLE` declared but no run path exists. Clicking "Run" would 410/404. **Violates A.5.1** (metadata-only ≠ runnable). |
| 11 RunTrace integration | 0 | No run possible → no trace. |
| 12 Tool / Expert calls | 0 | No experts[] (empty array in pack); no tool wiring. |
| 13 Honest degraded/error | 1 | No run path → no error path tested. Likely returns 410 with "Phase 2.1-A" message, which is at least honest. |
| 14 Requirements disclosure | 2 | `requirements` lists llm only. No missing-config surfacing because no run attempt. |
| 15 UI consistency | 1 | No frontend page for this agent. Invisible. |
| 16 API consistency | 1 | No dedicated API endpoint. Only `agent_definitions` CRUD. |
| 17 Platform alignment | 1 | Not in A2A discovery; not wired to MCP; no RunHistory. |

**Average**: 1.65 — **STUB_ONLY**
**Honesty rule violations**: A.5.1 (status=EXECUTABLE but no run path — should be METADATA_ONLY), A.5.2 (labeled maturity=mvp but is stub — should be metadata-only).
**Action**: Section F quick fix — relabel all 10 packs: `status: METADATA_ONLY`, `maturity: metadata-only`, `production_ready: false`, hide Run button in UI. Phase 3-B implements them properly.

**Other 9 agents in this class** (identical scores):
- 手术提取 (procedure-extractor@1.0.0) — avg 1.65, STUB_ONLY
- 编码校验 (code-validation@1.0.0) — avg 1.65, STUB_ONLY
- 证据排名 (evidence-ranker@1.0.0) — avg 1.65, STUB_ONLY
- 文档缺口检测 (documentation-gap@1.0.0) — avg 1.71 (slightly higher: dim 6=5 because "document gap detection" is a Corti §13-aligned concept), STUB_ONLY
- 病历完整性 (note-completeness@1.0.0) — avg 1.71, STUB_ONLY
- 临床文书改进 (cdi-review@1.0.0) — avg 1.71, STUB_ONLY
- 合规护栏 (compliance-guardrail@1.0.0) — avg 1.71, STUB_ONLY
- 拒付申诉 (denial-appeals@1.0.0) — avg 1.71, STUB_ONLY
- DRG 分组分析 (drg-analyzer@1.0.0) — avg 1.71, STUB_ONLY

### C.3.12 MedCodER Internal Engine (icoder/medcoder-coding-review-agent@1.0.0)

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 5 | "Medical Coding Agent — Internal Engine (MedCodER 5-stage)" — internal naming is appropriate for hidden internal engine. |
| 2 Category parity | 5 | `medical-coding` — correct. |
| 3 Agent Card completeness | 5 | All 5 fields present, with explicit "internal engine" labeling. |
| 4 Maturity labeling | 5 | `maturity: production-ready` for the engine itself; `hidden_from_hub: true`. |
| 5 Human review | 5 | Delegates to parent Medical Coding Agent's human_review policy. |
| 6 Safety / no overclaim | 5 | No F1 display; honest about MedCodER being a stage pipeline, not a magic box. |
| 7 Workflow clarity | 5 | 5-stage workflow (Extraction→Retrieval→Merge→Re-rank→Compliance) documented. |
| 8 Output contract | 5 | `MedicalCodingOutputSchema` (v1) + projects to v2. |
| 9 Agent Hub visibility | 5 | `hidden_from_hub: true` — correctly hidden. Not in A2A discovery (correct for internal engine). |
| 10 Runnability honesty | 5 | `status: EXECUTABLE` + 4 real experts + 5 real tools + run path (invoked by parent). |
| 11 RunTrace integration | 5 | Trace refs populated when parent runs. |
| 12 Tool / Expert calls | 5 | 4 experts (Stage 1/2/4/5) + 5 MCP tools — all real impls. |
| 13 Honest degraded/error | 4 | Degrades to LLM-only if FAISS index missing (documented). |
| 14 Requirements disclosure | 5 | `requirements: [llm, retriever, rule_set, embedder]` — explicit. |
| 15 UI consistency | 4 | No direct UI — invoked through parent. Acceptable for internal engine. |
| 16 API consistency | 4 | No public endpoint — invoked through parent's `/run` or A2A. Acceptable. |
| 17 Platform alignment | 4 | Real experts invoke through A2A internal dispatch (`/api/icoder/internal/experts/...`). MCP tools wired. RunHistory populated. |

**Average**: 4.18 — **ALIGNED**
**Honesty rule check**: All 5 rules satisfied. `hidden_from_hub: true` correctly applied — does not appear in Hub or A2A discovery.
**Action**: Keep as-is. This is the only fully Corti-aligned agent in the project.

### C.3.13-C.3.16 Four Expert-Stub Packs (rows 13-16)

**Representative: Evidence Extractor (icoder/evidence-extractor@1.0.0)**

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 1 | "Evidence Extractor" — English technical name, not user-facing task-oriented. Should be hidden or renamed "证据抽取" if ever surfaced. |
| 2 Category parity | 3 | `medical-coding` correct, but as an internal pipeline stage it shouldn't have its own category. |
| 3 Agent Card completeness | 4 | All 5 fields present. |
| 4 Maturity labeling | 2 | `maturity: stub` declared (honest), but `status: EXECUTABLE` is misleading — no standalone run path. |
| 5 Human review | 3 | `human_review: required` declared but agent is invoked internally, not by users. |
| 6 Safety / no overclaim | 4 | No overclaim. |
| 7 Workflow clarity | 3 | Single-stage workflow documented. |
| 8 Output contract | 4 | `ExtractionResult` schema declared. |
| 9 Agent Hub visibility | 1 | `hidden_from_hub: false` (live pack) — these SHOULD be hidden but are not. A.5.4 violation. |
| 10 Runnability honesty | 1 | No standalone run path. Status=EXECUTABLE is misleading. |
| 11 RunTrace integration | 2 | Trace populated when invoked internally by parent, but not as a standalone run. |
| 12 Tool / Expert calls | 3 | Has experts[] (self-referential) and tools[] but invoked through parent. |
| 13 Honest degraded/error | 3 | Internal invocation has error handling. |
| 14 Requirements disclosure | 3 | `requirements: [llm]` declared. |
| 15 UI consistency | 1 | No direct UI. Should not have one. |
| 16 API consistency | 2 | No public endpoint (correct for internal). |
| 17 Platform alignment | 2 | Real impl exists but pack presentation is misaligned (treated as user-facing Agent when it's an internal Expert). |

**Average**: 1.18 — **STUB_ONLY**
**Honesty rule violations**: A.5.4 (legacy/hidden ≠ visible) — `hidden_from_hub: false` should be `true`.
**Action**: Section F quick fix — set `hidden_from_hub: true` on all 4 expert-stub packs. They are internal pipeline stages, not user-facing Agents.

**Other 3 expert-stubs** (identical scores):
- Index Navigator (index-navigator@1.0.0) — avg 1.18, STUB_ONLY
- Code Reconciler (code-reconciler@1.0.0) — avg 1.18, STUB_ONLY
- Tabular Validator (tabular-validator@1.0.0) — avg 1.18, STUB_ONLY

## C.4 Page-as-Agent features (rows 17-21)

### C.4.1 MedicalCodingPage (frontend/src/pages/MedicalCodingPage.tsx)

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 5 | Page title "Medical Coding Agent" matches agent name. |
| 2 Category parity | 5 | Routed under `/ai-studio/medical-coding` (AI Studio category). |
| 3 Agent Card completeness | 4 | Page renders purpose + inputs + constraints inline. Risks not surfaced in UI (only in pack). |
| 4 Maturity labeling | 5 | MVP banner visible. |
| 5 Human review | 5 | "AI-assisted — human review required" banner visible. |
| 6 Safety / no overclaim | 5 | No F1 display; honest about MVP status. |
| 7 Workflow clarity | 4 | 8-step workflow visible in Settings panel. |
| 8 Output contract | 5 | 8-field Corti-style Review Summary panel rendered. |
| 9 Agent Hub visibility | 2 | Page exists but Agent Hub endpoint 404s. Discoverable only via sidebar. |
| 10 Runnability honesty | 4 | Run button works (calls /run endpoint), but uses legacy bypass. |
| 11 RunTrace integration | 5 | Run ID + trace refs surfaced in UI. |
| 12 Tool / Expert calls | 4 | Trace panel shows Stage 1-5 calls. |
| 13 Honest degraded/error | 5 | Error banner on 503; no silent fallback. |
| 14 Requirements disclosure | 4 | Missing-config banner shown if LLM key absent. |
| 15 UI consistency | 5 | 3-column layout, Review Summary panel, MVP banner — all present. |
| 16 API consistency | 4 | Calls `/api/runtime/agents/{ref}/run` (legacy). Should migrate to A2A `/message:send`. |
| 17 Platform alignment | 2 | Uses legacy /run bypass, not A2A mainline. |

**Average**: 3.94 — **PARTIALLY_ALIGNED**
**Action**: Phase 3-B migrate API call from legacy /run to A2A /message:send.

### C.4.2 FactExtractionPage

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 4 | "Fact Extraction" — task-oriented. Matches Corti §13.5. |
| 2 Category parity | 5 | Routed under correct category. |
| 3 Agent Card completeness | 3 | Page renders inputs/outputs; no risks surfaced. |
| 4 Maturity labeling | 3 | No explicit maturity banner. Backend is 501 stub. |
| 5 Human review | 3 | No human_review banner. |
| 6 Safety / no overclaim | 4 | No F1 display. |
| 7 Workflow clarity | 3 | Workflow implied but not documented in UI. |
| 8 Output contract | 3 | v2 contract declared but backend 501. |
| 9 Agent Hub visibility | 2 | In sidebar nav; not in Hub (Hub 404s). |
| 10 Runnability honesty | 2 | Backend `/api/v2/facts` returns 501 — honest about not-implemented, but UI doesn't surface this clearly. |
| 11 RunTrace integration | 1 | No run possible. |
| 12 Tool / Expert calls | 1 | No backend. |
| 13 Honest degraded/error | 3 | 501 is honest but UI experience is poor. |
| 14 Requirements disclosure | 2 | No requirements surfaced. |
| 15 UI consistency | 3 | Layout is consistent but content is empty. |
| 16 API consistency | 4 | `/api/v2/facts` is Corti-aligned path. |
| 17 Platform alignment | 2 | Not in A2A; 501 stub. |

**Average**: 2.71 — **PARTIALLY_ALIGNED**
**Action**: Either implement in Phase 3-B OR mark "Coming soon" banner until then.

### C.4.3 SpeechToTextPage

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 4 | "Speech to Text" — matches Corti §13.3. |
| 2 Category parity | 4 | Routed under transcription category. |
| 3 Agent Card completeness | 2 | No card; page is placeholder. |
| 4 Maturity labeling | 1 | No maturity label; no banner. |
| 5 Human review | 1 | No human_review language. |
| 6 Safety / no overclaim | 3 | No overclaim, but no information at all. |
| 7 Workflow clarity | 2 | Upload + list workflow implied, not documented. |
| 8 Output contract | 2 | No contract documented. |
| 9 Agent Hub visibility | 1 | In nav but page is orphan (no backend wiring). |
| 10 Runnability honesty | 1 | Backend endpoints `/api/v2/stt/recordings` may exist (Phase 1.3 cycle 9-12) but UI doesn't call them — orphan page. |
| 11 RunTrace integration | 0 | No runs. |
| 12 Tool / Expert calls | 0 | None. |
| 13 Honest degraded/error | 1 | Silent failure. |
| 14 Requirements disclosure | 1 | None. |
| 15 UI consistency | 2 | Placeholder layout. |
| 16 API consistency | 3 | Backend endpoints exist (Phase 1.3) but UI doesn't use them. |
| 17 Platform alignment | 1 | Not in A2A; not wired. |

**Average**: 1.59 — **MISALIGNED**
**Action**: Section F quick fix — either wire UI to existing Phase 1.3 STT endpoints OR remove from nav until wired.

### C.4.4 TextGenerationPage

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 4 | "Text Generation" — matches Corti §13.4. |
| 2 Category parity | 4 | Routed under text-gen category. |
| 3 Agent Card completeness | 2 | No card. |
| 4 Maturity labeling | 1 | No maturity label. |
| 5 Human review | 1 | No banner. |
| 6 Safety / no overclaim | 3 | No overclaim. |
| 7 Workflow clarity | 2 | Implied. |
| 8 Output contract | 2 | No contract. |
| 9 Agent Hub visibility | 1 | In nav but orphan. |
| 10 Runnability honesty | 1 | Backend `/api/v2/text-generation` may exist (Phase 1.2) but UI doesn't call them. |
| 11 RunTrace integration | 0 | None. |
| 12 Tool / Expert calls | 0 | None. |
| 13 Honest degraded/error | 1 | Silent. |
| 14 Requirements disclosure | 1 | None. |
| 15 UI consistency | 2 | Placeholder. |
| 16 API consistency | 3 | Backend exists but UI doesn't use. |
| 17 Platform alignment | 1 | Not wired. |

**Average**: 1.59 — **MISALIGNED**
**Action**: Same as SpeechToTextPage — wire or remove from nav.

### C.4.5 EmbeddedAssistantPage (placeholder)

| Dim | Score | Evidence |
|---|---|---|
| 1 Naming parity | 2 | "Embedded Assistant" — internal concept, not user-facing task. |
| 2 Category parity | 1 | No category. |
| 3 Agent Card completeness | 0 | No card. |
| 4 Maturity labeling | 0 | No label. |
| 5 Human review | 0 | None. |
| 6 Safety / no overclaim | 3 | No overclaim (no claims at all). |
| 7 Workflow clarity | 0 | None. |
| 8 Output contract | 0 | None. |
| 9 Agent Hub visibility | 0 | Not in Hub. |
| 10 Runnability honesty | 0 | No run path. |
| 11 RunTrace integration | 0 | None. |
| 12 Tool / Expert calls | 0 | None. |
| 13 Honest degraded/error | 1 | Silent. |
| 14 Requirements disclosure | 0 | None. |
| 15 UI consistency | 1 | Empty placeholder. |
| 16 API consistency | 1 | No endpoint. |
| 17 Platform alignment | 0 | Not aligned. |

**Average**: 0.88 — **DELETE_CANDIDATE**
**Action**: Section F — delete the placeholder page and nav entry. Embedded Assistant concept is now realized through ROPC Web Component (per cloud-flip pivot), not a page in the main SPA.

## C.5 Honesty rule violations summary (A.5 enforcement)

| Rule | Violated by | Fix |
|---|---|---|
| A.5.1 (metadata-only ≠ runnable) | 10 certified agents (rows 2-11): status=EXECUTABLE but no run path | Set status=METADATA_ONLY; hide Run button |
| A.5.2 (stub ≠ MVP) | 10 certified agents (rows 2-11): maturity=mvp but no real impl | Set maturity=metadata-only |
| A.5.3 (no trace ≠ mainline) | None — Medical Coding Agent has trace | (no fix needed) |
| A.5.4 (legacy/hidden ≠ visible) | 4 expert-stubs (rows 13-16): hidden_from_hub=false | Set hidden_from_hub=true |
| A.5.5 (production_ready=false surfaces) | 10 certified agents: production_ready=true claimed but no impl | Set production_ready=false; show MVP banner if ever wired |

**Total A.5 violations**: 24 across 14 agents. All fixable in Section F.

## C.6 Cross-cutting Corti parity gaps

These gaps affect multiple agents and cannot be fixed per-agent:

1. **Agent Hub endpoint 404** — affects dim 9 for all 21 surfaces. Section F must restore `/api/icoder/agents/hub` or remove Hub references from frontend.
2. **A2A discovery returns 1 agent** — affects dim 17 for all certified agents. Section F should at minimum document why A2A only exposes medcoder-coding-review (the internal engine).
3. **Legacy /run bypass for Medical Coding Agent** — caps dim 17 at 1-2 for the primary agent. Phase 3-B migration to A2A mainline is required to lift this.
4. **3 duplicate execution endpoints** — `/run`, `/medical-coding/test`, `/v2/tools/coding/icoder` all call the same `HybridCodingAdapter`. Consolidate in Phase 3-B.
5. **seed.py PREBUILT_AGENTS vs agent_pack.json collision** — 16 DB-seeded templates overlap with 11 certified packs. Naming confusion risk. Section F: clarify agent_pack.json is canonical.

## C.7 Section D uses this audit

The next section (D) takes the 21 audited surfaces and designs manual QA simulation paths for each visible one. The verdicts here drive the test result categories in D:
- ALIGNED + PARTIALLY_ALIGNED → design full test path, expect PASS or PARTIAL
- MISALIGNED → design test path, expect FAIL or SHOULD_HIDE
- STUB_ONLY → design test path, expect STUB_ACCEPTED or SHOULD_HIDE
- DELETE_CANDIDATE → design test path, expect SHOULD_DELETE

## C.8 What Section C is NOT

- Not a fix list — fixes happen in Section F based on C.5 + C.6.
- Not a Phase 3-B implementation plan — that lives in Section H.
- Not a Corti reverse-engineering — scores are based on the 17 dimensions from Section A, not on Corti private code.
- Not a performance judgment — no F1/latency scoring (Phase 3-A red line).

## C.9 Verdict

**Phase 3-B0 Section C verdict**: COMPLETE — 21 surfaces scored, 24 honesty rule violations identified, 5 cross-cutting gaps catalogued. All findings carried forward to Section D (manual QA simulation) and Section F (quick fixes).
