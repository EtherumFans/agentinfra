# iCoDer 14 Agent Runtime Inventory (B-1.2)

**Date:** 2026-07-11
**Backend:** `http://127.0.0.1:8000` (uvicorn, startup 05:18:11 UTC)
**Frontend:** 未启动（B-1.2 走 API；前端走查合并到 B-1.4）
**Sources:**
- `GET /api/icoder/agents/hub` → `outputs/phase5_track_b/icoder_agents_hub.json` (14 agents, full hub metadata)
- `GET /api/runtime-platform/agents` → `outputs/phase5_track_b/icoder_runtime_platform_agents.json` (14 agents, E/T counts)
- `GET /.well-known/agent.json` → A2A v0.3 multi-agent discovery (5 agents only)
- `GET /api/icoder/agents/{id}/card` → A2A single card (5 agents only)

## Key findings

| Dimension | Count | Notes |
|-----------|-------|-------|
| Hub-declared agents | 14 | vs seed.py declared 16 (10 missing — see §3 below) |
| Runnable agents | **9** | All in `medical-coding` category |
| Metadata-only agents | 5 | maturity=metadata-only, no run path |
| A2A-discoverable agents | **5** | Per `.well-known/agent.json`; hardcoded list |
| Agents with experts wired | 10/14 | E≥1; 4 metadata-only agents have E=0 |
| Agents with MCP tools wired | 8/14 | T≥1; 6 metadata-only share default 6 MCP tools |
| production_ready=True | **0/14** | All agents are MVP / runnable / metadata-only |
| Chinese-named categories | 5 | "编码" / "医保" / "质控" / "护理" / "文书" + medical-coding mapped to Corti category |

**Critical finding**: 9 runnable agents exist in Hub but only 5 are A2A-discoverable. **4 "runnable" agents lack A2A cards** — they cannot be discovered by external A2A clients (Corti SDK style). This is a **P1 gap** (not P0 because runtime platform still serves them via `/api/runtime-platform/agents/{ref}/run`).

## 1. Full inventory (14 agents)

### 1.1 Runnable (9) — all category=medical-coding

| # | agent_id | 中文 name | Experts | Tools | Runtime modes | Corti match |
|---|----------|-----------|---------|-------|---------------|-------------|
| 1 | drg-analyzer | DRG/DIP 风险复核智能体 | 1 | 0 | a2a_pure_llm | (none — iCoDer ADVANTAGE) |
| 2 | principal-diagnosis-review | 主诊断复核智能体 | 1 | 0 | a2a_pure_llm | (none — iCoDer ADVANTAGE) |
| 3 | discharge-summary-structuring | 出院小结结构化智能体 | 1 | 0 | a2a_pure_llm | (none direct — Corti has CDI agent closest) |
| 4 | medical-coding-agent | 医学编码智能体 | 1 | 5 | corti_like_fast + medcoder_deep | **medical-coding-icd-10-cpt-agent** |
| 5 | compliance-guardrail-agent | 合规护栏智能体 | 1 | 1 | rule_engine + a2a_pure_llm | **compliance-guardrail-agent** |
| 6 | procedure-extractor | 手术提取智能体 | 1 | 0 | a2a_pure_llm | **procedure-entity-extractor-agent** |
| 7 | note-completeness-agent | 病历完整性智能体 | 1 | 1 | a2a_pure_llm | **note-completeness-agent** |
| 8 | code-validation-agent | 编码校验智能体 | 2 | 4 | (none — has runtime modes but not declared) | **code-validation-agent** |
| 9 | evidence-extractor | 证据提取智能体 | 1 | 0 | a2a_pure_llm | (none — iCoDer ADVANTAGE) |

**Maturity distribution:** MVP=7, runnable=2 (note-completeness + code-validation), production_ready=0.

### 1.2 Metadata-only (5) — declared but not executable

| # | agent_id | 中文 name | Experts | Tools | Reason | Corti match |
|---|----------|-----------|---------|-------|--------|-------------|
| 10 | denial-appeals | 拒付申诉智能体 | 0 | 6 | metadata-only | **denial-appeals-agent** |
| 11 | evidence-ranker | 证据排序智能体 | 0 | 6 | metadata-only | (none — iCoDer-specific) |
| 12 | diagnosis-extractor | 诊断提取智能体 | ? | ? | metadata-only | **diagnostic-entity-extractor-agent** |
| 13 | cdi-review | CDI 审核智能体 | 0 | 6 | metadata-only | **clinical-documentation-improvement-cdi-agent** |
| 14 | documentation-gap | 病历缺口智能体 | 0 | 6 | metadata-only | (none — overlaps CDI) |

**Note:** 4 of 5 metadata-only agents share the same default 6 MCP tools (likely the platform-default MCP server tools, not agent-specific). This is a "phantom tool wiring" pattern — metadata-only agents show tools but can't execute them.

## 2. A2A discovery gap analysis

`.well-known/agent.json` returns only **5 agents** (hardcoded in `routes_discovery.py:138-148`):

```python
for agent_id, factory in [
    ("medcoder-coding-review", medcoder_coding_review_card),
    ("medical-coding-agent", medical_coding_agent_card),
    ("code-validation-agent", code_validation_agent_card),
    ("compliance-guardrail-agent", compliance_guardrail_agent_card),
    ("note-completeness-agent", note_completeness_agent_card),
]:
```

**Missing from A2A discovery (4 runnable + 5 metadata-only = 9 agents):**
- drg-analyzer ❌ (runnable but no card)
- principal-diagnosis-review ❌ (runnable but no card)
- discharge-summary-structuring ❌ (runnable but no card)
- procedure-extractor ❌ (runnable but no card)
- evidence-extractor ❌ (runnable but no card)
- denial-appeals, evidence-ranker, diagnosis-extractor, cdi-review, documentation-gap (metadata-only — acceptable to omit)

**P1 GAP-13-01**: 4 of 9 runnable agents have no A2A card. External A2A clients (Corti SDK style) cannot discover them. Fix: extend `_list_all_cards` in `routes_discovery.py` to include all runnable agents dynamically from registry.

## 3. seed.py vs Hub discrepancy

`backend/app/seed.py:847` declares **16 PREBUILT_AGENTS** but Hub shows **14 agents** with different distribution:

| seed.py key | In Hub? | Notes |
|-------------|---------|-------|
| icd10-navigator | ❌ | 404 on /card, not in hub |
| rule-explainer | ❌ | 404 on /card, not in hub |
| compliance-guardrail | ✅ | compliance-guardrail-agent |
| code-validation | ✅ | code-validation-agent |
| procedure-extractor | ✅ | procedure-extractor |
| diagnosis-extractor | ✅ | diagnosis-extractor (metadata-only) |
| surgical-registry | ❌ | 404 on /card, not in hub |
| icu-summary | ❌ | 404 on /card, not in hub |
| triage | ❌ | 404 on /card, not in hub |
| note-completeness | ✅ | note-completeness-agent |
| med-reconciliation | ❌ | 404 on /card, not in hub |
| denial-appeals | ✅ | denial-appeals (metadata-only) |
| discharge-edu | ❌ | 404 on /card, not in hub |
| nursing-handoff | ❌ | 404 on /card, not in hub |
| prior-auth | ❌ | 404 on /card, not in hub |
| referral-gen | ❌ | 404 on /card, not in hub |

**Hub adds 4 extra agents not in seed.py:** drg-analyzer / principal-diagnosis-review / discharge-summary-structuring / medical-coding-agent / evidence-extractor / evidence-ranker / cdi-review / documentation-gap (these come from `.icoder/agent_registry.json` + official_agents pack).

**P0 GAP-13-02**: 10 of 16 seed.py-declared agents are missing from runtime. Either:
- (a) seed.py declares agents that runtime doesn't load → fix seed.py
- (b) seed.py declares agents that should be loaded but aren't → fix loader
- (c) seed.py is stale and agents were intentionally removed → fix seed.py to remove

This is **AUDIT_BLOCKER-eligible** but doesn't block Track B audit (Corti has equivalent agents; we just can't compare them). Logging as **P0 GAP-13-02** in Gap Backlog.

## 4. Category mapping to Corti

| iCoDer category | iCoDer category_display | Corti equivalent | # iCoDer agents |
|-----------------|-------------------------|------------------|-----------------|
| medical-coding | Coding and Revenue Cycle / 编码与收入周期 | Coding and Revenue Cycle | 9 (all runnable) |
| 编码 | (none) | Coding and Revenue Cycle (partial) | 2 (diagnosis-extractor + evidence-ranker) |
| 医保 | (none) | Coding and Revenue Cycle (denials) | 1 (denial-appeals) |
| 质控 | (none) | Documentation / Notes + CDI | 2 (cdi-review + documentation-gap) |
| 护理 | (none) | Care Coordination | 0 (declared in seed.py but not loaded) |
| 文书 | (none) | Documentation / Notes | 0 (declared in seed.py but not loaded) |
| 急诊 | (none) | Point of Care Tools | 0 (declared in seed.py but not loaded) |
| 药学 | (none) | Point of Care Tools | 0 (declared in seed.py but not loaded) |

**Findings:**
- iCoDer has 9 runnable agents vs Corti's 10 Coding/Revenue agents → near parity for core coding
- iCoDer's "Coding and Revenue Cycle / 编码与收入周期" display string already maps 1:1 to Corti
- 4 Corti categories have **0 runnable iCoDer equivalents**: Point of Care Tools / Clinical Evidence and Research / Care Coordination / Clinical Documentation Improvement

## 5. iCoDer advantages preserved (vs Corti)

1. **DRG/DIP Risk Review Agent** — Corti has no DRG/DIP equivalent (Corti is US-focused with ICD-10-CM/PCS)
2. **Principal Diagnosis Review Agent** — Corti has no direct equivalent (Corti's Medical Coding doesn't separate this)
3. **Discharge Summary Structuring Agent** — Corti has no direct equivalent (closest is CDI)
4. **Evidence Extractor Agent** — Corti has no direct equivalent (Corti's coding-expert bundles this)
5. **medical-coding-agent dual mode** — corti_like_fast + medcoder_deep (5-stage MedCodER pipeline); Corti has only one mode
6. **6 MCP tools on metadata-only agents** — declared intent (even if not executable yet)

## 6. Permission / runtime limitations

- No login required to query Hub + cards (development mode)
- All 9 runnable agents return 200 on `/run` endpoint (smoke test reserved for B-1.4 5-pair deep audit)
- A2A cards limited to 5 hardcoded agents
- seed.py vs runtime discrepancy (10 missing)

## 7. What's NOT in B-1.2 (deferred)

- Per-agent UI screenshots (deferred to B-1.4 — combined with Corti comparison)
- Smoke runs for all 9 runnable agents (deferred to B-1.4 — only 5 deep-dive targets)
- Frontend walkthrough (deferred to B-1.4 — Agents Hub page + AgentChatPage per agent)
- Settings/Code/Tools/Experts tab content per agent (deferred to B-1.4)

## 8. Status

**B-1.2 complete.** Move to B-1.3 (agent mapping).

**Gap Backlog entries raised:**
- **P0 GAP-13-02**: 10/16 seed.py agents missing from runtime
- **P1 GAP-13-01**: 4/9 runnable agents missing A2A card discovery
- **P1 GAP-13-03**: 5/14 agents are metadata-only (no run path) — denial-appeals / diagnosis-extractor / cdi-review are Corti-equivalent → should be promoted to runnable
- **P2 GAP-13-04**: 4 Corti categories with 0 runnable iCoDer agents (Point of Care / Clinical Evidence / Care Coordination / CDI)
- **P2 GAP-13-05**: iCoDer category_display empty for 5/14 agents (consistency with Corti mapping)
