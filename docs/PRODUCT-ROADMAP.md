# iCoDer Product Roadmap
## Medical Revenue Compliance AI Runtime Platform

Target: Transform from a medical coding audit system into a self-service Agent Runtime platform for ISVs and developers.

---

## Phase 1: Developer Onboarding (Weeks 1-2)

Goal: A developer can `pip install icoder-runtime`, clone a template, and get a working compliance Agent in 5 minutes.

| # | Work Item | Effort | Deliverable |
|---|-----------|--------|-------------|
| 1.1 | **Agent clone endpoint** | 1 day | `POST /api/agents/{agent_id}/clone` — instantiate a template as a user-owned Agent. Prebuilt agents become editable copies. |
| 1.2 | **Quickstart documentation** | 3 days | One page: install → configure LLM → clone Medical Coding template → run → see evidence chain. With screenshots. |
| 1.3 | **SDK scenario tutorials** | 3 days | Three code-along guides: (a) Build a coding audit Agent, (b) Add a custom compliance Tool, (c) Export an evidence pack via API. |
| 1.4 | **Audit evidence pack export API** | 1 week | `POST /api/reviews/{id}/evidence-pack` → structured JSON/PDF: original text → evidence → code candidates → rule validation → human confirmations → timestamps. Ready for CA signing layer. |

**Phase 1 exit criteria:** A new developer, with no prior iCoDer knowledge, can `pip install` and create a running Agent within 5 minutes. Evidence pack API returns a complete audit trail for any review.

---

## Phase 2: Platform Extensibility (Weeks 3-4)

Goal: ISVs can register custom Tools and build Agents without touching iCoDer source code.

| # | Work Item | Effort | Deliverable |
|---|-----------|--------|-------------|
| 2.1 | **Tool registration API** | 1-2 weeks | `POST /api/tools` — ISV uploads a Tool spec (JSON: name, contract pre/post conditions, parameter schema, accuracy tags, Tier level). Runtime auto-registers and enforces contracts. |
| 2.2 | **Permission preset configuration** | 1 week | `POST /api/permissions/presets` — ISV defines custom permission sets. Which operations require `requires_human: true`, which auto-approve. |
| 2.3 | **Agent Tracing UI** | 2 weeks | Frontend dashboard: timeline view of Agent execution — tool calls, pre/post condition results, LLM invocations, state transitions. Color-coded pass/fail. Per-step evidence drill-down. |

**Phase 2 exit criteria:** An ISV can register a custom Tool (e.g., "Local Hospital Billing Rule Checker") with contract specs, bind it to an Agent, run it, and observe the full trace in the Dashboard.

---

## Phase 3: Marketplace as Distribution (Weeks 5-6)

Goal: Marketplace goes from "Agent list" to "Agent distribution platform" — install, rate, version-manage.

| # | Work Item | Effort | Deliverable |
|---|-----------|--------|-------------|
| 3.1 | **Marketplace install flow** | 3 days | One-click install: browse → install → Agent appears in user's workspace. Version compatibility check on install. |
| 3.2 | **Agent version management** | 2 days | Diff view between versions. Rollback to previous version. Changelog per version. |
| 3.3 | **Usage analytics per Agent** | 3 days | Agent owner sees: installs, runs, avg latency, error rate, token usage. Tenant-scoped (each org sees only their agents). |
| 3.4 | **ISV documentation pack** | 1 week | Complete ISV guide: Tool contract writing → Agent packaging → Marketplace publishing → pricing setup → analytics interpretation. |

**Phase 3 exit criteria:** A third-party ISV can publish an Agent to the Marketplace, another user can install it, run it, and the original ISV can see usage analytics.

---

## Phase 4: Developer Tooling (Weeks 7-8)

Goal: Developer productivity and self-service maturity.

| # | Work Item | Effort | Deliverable |
|---|-----------|--------|-------------|
| 4.1 | **CLI tool** | 1 week | `pip install icoder-cli` → `icoder init my-agent` (scaffolds project), `icoder deploy` (pushes to platform), `icoder test` (runs against local Runtime). |
| 4.2 | **Agent Playground** | 2 weeks | Web UI: select Agent, type input, see real-time trace output. No code needed. Test compliance rules interactively. |
| 4.3 | **Python SDK reference docs** | 1 week | Auto-generated from docstrings. Full API reference: Runtime, Agent, Tool, EvidencePack, Audit. |

---

## Dependency Graph

```
Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4
  │            │
  └── 1.4      └── 2.3 (Tracing UI depends on evidence chain data model)
  (Evidence     (Tool registration
   pack)         enables ISV tools)
```

Phase 1 is fully self-contained. Phase 2.1 (Tool registration) is the architectural gate — after this, ISVs can build without source access.

---

## What Does NOT Change

- Runtime core (contract engine, symbolic state, permissions, guardrails)
- Database schema
- Existing Agent template system (20 templates)
- Agent CRUD API
- Authentication / multi-tenancy

---

## Key Metrics Per Phase

| Phase | Success Metric |
|-------|---------------|
| Phase 1 | Time-to-first-Agent ≤ 5 minutes for a new developer |
| Phase 2 | 1 ISV successfully registers a custom Tool and builds an Agent with it |
| Phase 3 | 1 third-party Agent published, installed, and running in a separate org |
| Phase 4 | 1 Agent built entirely via CLI + Playground (no source code editing) |
