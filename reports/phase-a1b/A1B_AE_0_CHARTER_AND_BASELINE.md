# Phase A1B-AE — Agent & Expert Clean-Room Replication Charter (A1B-AE.0)

**Date**: 2026-07-22
**Phase**: A1B-AE (Agent & Expert Clean-Room Replication + Human-Operation Simulation + Agent-Platform Technical-Debt Liquidation)
**Charter version**: v1.0 (2026-07-22) → **v1.1 (2026-07-22, mid-phase; see [A1B_AE_0_CHARTER_AMENDMENT_1_REVERSE_ENGINEERING_PERMITTED.md](A1B_AE_0_CHARTER_AMENDMENT_1_REVERSE_ENGINEERING_PERMITTED.md))**
**Worktree**: `E:/Corti4C-agent-expert`
**Branch (new, local-only)**: `phase-a1b/agent-expert-clean-room`
**Branch source**: verified HEAD `3d50b116597c992ac92de189fad70def11349dcb` on `phase-a1a/emergency-containment`
**Predecessor immutable anchors** (all preserved, NOT rewritten):
- `audit/phase-a0.1r-baseline` (annotated tag `3cd1bec`) on `64590fa`
- `audit/phase-a1a-gate4-pre4r-b3ea064` (annotated tag `fa0d461`) on `b3ea064`
- `audit/phase-a1a-gate4r-closure-24967da` (annotated tag `43c2395`) on `24967da`
- `3d50b11` — Phase A1A Gate 4R-I.11 final verdict (current HEAD of `phase-a1a/emergency-containment`)
- `a0b56da` — Phase A1A Gate 4R-I.10 development backlog (HEAD~1, NOT final — user-flagged ambiguity resolved)

> **v1.1 notice (effective 2026-07-22 mid-phase)**: §7 now defines two
> provenance tiers (`CLEAN_ROOM_PUBLIC` unchanged, plus new
> `REVERSE_ENGINEERED` permitting Corti Console observation and
> behavioural reverse engineering under an authorised developer
> account). All previously filed evidence retains its CLEAN_ROOM_PUBLIC
> classification. Forbidden verdicts unchanged. See
> [Charter Amendment 1](A1B_AE_0_CHARTER_AMENDMENT_1_REVERSE_ENGINEERING_PERMITTED.md)
> for binding details.

---

## §1. Why this Charter exists

Phase A1A Gate 4R-I closed a 12-sub-gate *integration* and *product-gap audit* of the
4R regression-reconciliation branch into `phase-a1a/emergency-containment`. Its
final verdict — `PASS_A1A_GATE4R_INTEGRATION_REPOSITORY_RECONCILIATION_AND_PRODUCT_GAP_AUDIT_FILED`
— was explicitly **FILED**, not **VERIFIED**. The verdict left five top-level state
flags unchanged:

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

The 4R-I.6 capability inventory (234 routes) and 4R-I.7 clean-room parity matrix
(weighted **52.6 %**) identified that the largest *qualitative* gap versus Corti's
public Agentic Framework documentation is the **Agent / Expert / Pack / Tool taxonomy
and runtime**. The iCoDer side has ~32 Pack directories, ~11 internal experts,
~41 API route files, and ~67 service files, but it has **no single canonical Agent
catalog**, **no unified Expert Registry**, **no deterministic Calculator Expert**,
**no PubMed / ClinicalTrials egress-audited Expert**, and **no schema-driven
Interviewing Expert**. Pack/Agent/Expert counts have historically been quoted as
"≈23", "≈29", "≈16" in different reports, and dual-naming (`code_validation` vs
`code-validation`, `compliance_guardrail` vs `compliance-guardrail`, `note_completeness`
vs `note-completeness`) has produced a class of clone-404 / Agent-Card-mismatch /
seed-shadows-Pack defects.

This Charter authorises a **clean-room** reconstruction of Corti's publicly
documented Agentic contracts (Agent, Expert, Tool, MCP Server, Agent Pack,
Preset Agent, Task, Context, Artifact, Memory), implemented on the iCoDer
side without copying any Corti-private code, prompts, UI assets, or trademarks.
It mandates **human-operation simulation**: every capability must be observed via
a headed browser against `docs.corti.ai` and verified against the iCoDer UI
through 10 explicit headed-browser journeys. It also liquidates the Agent/Expert
fraction of the technical-debt backlog (Pack-count assertions, seed/Pack/DB
shadowing, clone-404, Agent-Card inconsistency, MCP-rule assertions, singleton
pollution, schema drift, OpenAPI/SDK drift).

This Charter **does NOT close Gate 4**, **does NOT claim Corti parity**,
**does NOT claim production readiness**, and **does NOT modify any A1A-tagged
commit, branch, or tag**.

## §2. Authorization (in scope)

This Charter authorises, and only authorises:

A. Creation of a new local-only worktree `E:/Corti4C-agent-expert` on a new
   local-only branch `phase-a1b/agent-expert-clean-room` from the verified
   HEAD SHA `3d50b11…` (the worktree has already been created; see §5).
B. Headed-browser human observation of Corti public documentation at
   `https://docs.corti.ai/agentic/*` for the sole purpose of rebuilding
   public contracts in a clean-room fashion.
C. Clean-room design and implementation of:
   - canonical Agent / Expert / Pack / Tool catalogs (`backend/agent_catalog/`)
   - Expert Registry (model + alembic migration + REST API + service layer)
   - Agent CRUD + Agent Card + alias / version resolution
   - Message → Task → Context lifecycle (A2A v0.3 compatible)
   - Context deletion with content scrub + minimal audit retention
   - Memory Expert (lexical baseline; optional embedding tier)
   - Medical Calculator Expert (deterministic; BMI/BSA/HbA1c/unit conversions)
   - PubMed Expert (NCBI E-utilities; synthetic queries only; egress audit)
   - Clinical Trials Expert (clinicaltrials.gov; synthetic queries only)
   - Interviewing Expert (schema-driven questionnaire; deterministic flow)
   - Coding Expert wrapper around existing `icoder/medical-coding-agent`
   - DrugBank / POSOS external Experts (LICENSE_REQUIRED stubs, no LLM fallback)
   - Web Search Expert (DISABLED_BY_POLICY default; opt-in per Provider)
   - MCP Server Registry record format (URL/transport/auth-ref only; no plaintext secret)
D. Assembly of 5 iCoder clean-room Preset Agents:
   Clinical Research Assistant / Medication Reference Assistant /
   Coding Assistant / Structured Intake Assistant / Trial Matching Research Assistant.
   All tagged `origin=ICODER_CLEAN_ROOM`, `official_corti_preset=false`.
E. Orchestrator with explicit Expert selection, invocation trace, citation
   merge, Provider egress enforcement, tenant boundary, PHI classification.
F. Liquidation of Agent/Expert technical debt enumerated in §11 of this
   Charter (Pack-count assertions, seed/Pack/DB shadowing, clone-404,
   Agent-Card inconsistency, MCP-rule assertions, singleton pollution,
   targeted schema drift, OpenAPI/SDK drift, Windows async test issues).
G. Headed-browser execution of 10 explicit user journeys against the iCoDer
   UI, with screenshots, sanitized HAR, visible-text snapshots, and trace.
H. Generation of unit / contract / integration / browser evidence artefacts.
I. Creation of local-only audit tags at end of phase (NOT pushed).

## §3. Out of scope (NOT authorised)

This Charter does NOT authorise:

- Merge to `master`; modify `origin/master`; push; create PR; deploy.
- Use of real patient data; calls to real Corti API with production credentials;
  calls to real LLM Provider with real PHI.
- Rewrite, amend, rebase, or squash of any ancestor commit (including
  `b737eab`, `880f49c`, `b3ea064`, `24967da`, `3d50b11`, `a0b56da`,
  or any A0.1R / A1A-tagged object).
- Deletion of audit branches or audit tags.
- Modification of Medical Coding / CDI / DRG-DIP *clinical* prompts
  (a separate clinical-quality Charter is required for clinical prompt changes).
- Weakening of JWT, tenant boundary, encryption, redaction, egress, retention,
  or fail-closed controls to pass tests.
- Marketing-style Corti parity claims or "Corti-fully-replicated" verdicts.
- Copy of Corti proprietary source code, internal prompts, UI assets,
  logos, trademarks, or any non-public material into the iCoDer repository.
- Use of Corti documentation example prompts as production prompts without
  independent re-authoring (every new prompt MUST declare
  `clean_room_authored: true` per §7 below).
- Web scraping of DrugBank, POSOS, or any licensed content without a licence.
- Sending patient-identifiable data to PubMed, ClinicalTrials.gov, or any
  external Expert.
- Direct DB writes to fake user-operation results; bypassing the public
  API surface to simulate user actions.
- Use of `git add -A`, `git add .`, or `git commit -a`; every commit
  must use an explicit file list.

## §4. Snapshots preserved by this Charter

| Object | Role | Mutability after this Charter |
|---|---|---|
| `audit/phase-a0.1r-baseline` (tag `3cd1bec`) | A0.1R immutable anchor | IMMUTABLE |
| `audit/phase-a0.1r-freeze` (branch `64590fa`) | A0.1R freeze branch | NOT DELETED |
| `audit/phase-a1a-gate4-pre4r-b3ea064` (tag `fa0d461`) | Pre-4R Gate 4 closure snapshot | IMMUTABLE |
| `audit/phase-a1a-gate4r-closure-24967da` (tag `43c2395`) | 4R P0-5 closure snapshot | IMMUTABLE |
| `phase-a1a/gate4r-regression-reconciliation` (branch `24967da`) | 4R carrier | NOT DELETED |
| `phase-a1a/emergency-containment` (branch `3d50b11`) | A1A main work | NOT MODIFIED by A1B-AE |
| `phase-a1b/agent-expert-clean-room` (branch, new) | A1B-AE carrier | APPENDED only via new commits |
| `E:/Corti4C-agent-expert` (worktree, new) | A1B-AE workspace | APPENDED only via new commits |
| `E:/Corti4C` (worktree, existing) | A1A workspace | NOT MODIFIED by A1B-AE |

New annotated tags to be created at end of phase (local-only, never pushed):

- `audit/phase-a1b-agent-expert-clean-room-baseline-3d50b11` on `3d50b11`
- `audit/phase-a1b-agent-expert-clean-room-final-<SHA>` on final commit
  (only if all acceptance conditions in §10 are met)

## §5. Worktree and branch mechanics (already executed)

```
git worktree add -b phase-a1b/agent-expert-clean-room \
    E:/Corti4C-agent-expert \
    3d50b116597c992ac92de189fad70def11349dcb
```

Verified post-creation (this Charter, §6 baseline):

```
worktree path : E:/Corti4C-agent-expert
HEAD          : 3d50b116597c992ac92de189fad70def11349dcb
branch        : phase-a1b/agent-expert-clean-room
predecessors  : 3d50b11 (immediate)
                a0b56da (HEAD~1, NOT final)
```

No worktree previously existed at this path. No `phase-a1b/*` branch or tag
previously existed. No reset, stash, or forced operation occurred.

## §6. Baseline state (frozen at this commit)

### §6.1 Inherited 5-tuple state

```json
{
  "GATE4_8_NO_NEW_REGRESSION_CLAIM": "CONTRADICTED",
  "GATE4_9_FINAL_PASS":              "SUPERSEDED",
  "GATE4_ACCEPTANCE_STATUS":         "REOPENED",
  "CORTI_PARITY_VERDICT":            "NOT_DEMONSTRATED",
  "PRODUCTION_READINESS":            "NOT_VERIFIED"
}
```

These flags are inherited from Phase A1A Gate 4R-I.11 and are NOT modified by
this Charter. They will be re-checked at the end of A1B-AE; any change requires
a separate Charter amendment.

### §6.2 Environment manifest (extract; full JSON in companion file)

| Field | Value |
|---|---|
| Verified HEAD SHA | `3d50b116597c992ac92de189fad70def11349dcb` |
| Branch | `phase-a1b/agent-expert-clean-room` |
| Worktree | `E:/Corti4C-agent-expert` |
| OS | Windows 10 Home China 10.0.19045 |
| Shell | bash (Git for Windows; Unix-style paths) |
| Python | 3.12.3 |
| Node | v22.20.0 |
| Git | 2.50.1.windows.1 |
| Pack directories under `backend/official_agents/` | 32 |
| API route files under `backend/app/api/` | 41 (40 routes + `__init__.py`) |
| Internal experts under `backend/app/agents/experts/` | 11 + `__init__.py` |
| Service files under `backend/app/services/` | 67 |
| Frontend `.ts`/`.tsx` under `frontend/src/` | 70 |
| Total source/config files (pruned) | 2422 |

### §6.3 Pre-change SHA-256 sums

Captured for key files likely to be touched by A1B-AE, in
`A1B_AE_0_PRE_CHANGE_SHA256SUMS.txt`. Drift detection compares
these sums at end of phase.

### §6.4 Observed Pack-duality (version-shadowing risk)

The following Pack directories exist in dual form (underscore + hyphen),
producing the "version shadowing" / "clone 404" / "Agent Card mismatch"
defect class flagged in §9.4 of the originating brief:

| Underscore form | Hyphen form |
|---|---|
| `code_validation/` | `code-validation/` |
| `compliance_guardrail/` | `compliance-guardrail/` |
| `note_completeness/` | `note-completeness/` |

This is a known Phase A1B-AE.9 debt to liquidate; baseline captured here.

## §7. Clean-room authorship discipline

> **v1.1 in force** — see [Charter Amendment 1](A1B_AE_0_CHARTER_AMENDMENT_1_REVERSE_ENGINEERING_PERMITTED.md).
> §7 now defines two provenance tiers: `CLEAN_ROOM_PUBLIC` (the original
> v1.0 regime, unchanged below as §7.1) and `REVERSE_ENGINEERED` (new,
> see Amendment §A1.2 §7.2). The text below is the v1.0 §7.1 text,
> retained as the CLEAN_ROOM_PUBLIC tier definition.

Every prompt, schema, contract, or design artefact produced under this
Charter MUST declare (in its file header or sidecar metadata):

```yaml
clean_room_authored: true
author: <name>
date: 2026-07-22
design_source:
  - "Corti public docs (URL)"
  - "A2A public spec (v0.3)"
  - "MCP public spec"
  - "iCoDer original design"
contains_corti_private_material: false
version: "0.1.0"
sha256: "<computed at freeze>"
allowed_data_types:
  - synthetic_patient
  - synthetic_drug
  - synthetic_disease
  - synthetic_citation
forbidden_behaviours:
  - diagnostic_assertion
  - llm_arithmetic
  - llm_drug_safety_fallback
  - external_phle_notion_egress
rollback_version: null
```

The declaration is the author's attestment; the Charter audits it via
automated checks at end of phase (see §10 acceptance).

## §8. Human-operation simulation protocol (summary)

The full protocol lives in `A1B_AE_0_HUMAN_OPERATION_PROTOCOL.md`. Summary:

1. **Corti side** — Headed Chrome / Playwright headed. Start at
   `https://docs.corti.ai/`. Navigate via visible menus only. Step-by-step
   observation log per page. Stop on 401/403/captcha/non-public → mark
   `BLOCKED_BY_ACCESS_CONTROL`. No JavaScript injection. No DOM-state bypass.
2. **iCoDer side** — Headed Chrome against localhost (Frontend dev server).
   Login as synthetic test user. Operate via visible UI only. For capabilities
   without UI, fall back to one-curl-per-command API operation with full
   request/response capture. Direct DB writes forbidden as primary evidence.
3. **HUMAN_WORKFLOW_VERIFIED** — only granted when all 11 conditions in
   §1.3 of the originating brief are met (discovery, configuration, run,
   comprehensible result, comprehensible error, browser/API agreement,
   persistence, audit, cross-tenant negative test, no PHI leak, full
   evidence).
4. **API_WORKFLOW_VERIFIED** — strictly weaker; used only when no UI exists.
5. **BLOCKED_BY_BROWSER_ENVIRONMENT** — used when no headed browser is
   available; never replaced by static source-code inspection.

## §9. Taxonomy (binding for this phase)

| Concept | Definition (clean-room) |
|---|---|
| **Agent** | A named, tenant-owned aggregation of one or more Experts behind a single Agent Card, Orchestrator entrypoint, and run lifecycle. User-visible. |
| **Expert** | A discrete capability with structured input, structured output, declared dependencies, declared data egress, declared citations, declared failure modes, deterministic / non-deterministic flag, licence-required flag, and maturity (`EXPERIMENTAL` / `STABLE` / `DEPRECATED`). Not directly user-visible. Invoked by Orchestrator. |
| **Tool** | A low-level function used *inside* an Expert (PubMed search; BMI compute; ICD lookup; MCP tool call). Never user-visible. Never appears in Agent Hub. |
| **MCP Server** | An external tool service callable by Experts. Registry record only stores: server ID, name, transport, URL, auth type, secret reference, allowed tools, egress classification. **Never stores plaintext secret.** |
| **Agent Pack** | A distribution unit (code + config). One Pack may contain: an Agent definition, multiple Expert definitions, tools, prompts, UI metadata, tests. **Pack count ≠ Agent count ≠ Expert count.** |
| **Preset Agent** | An iCoDer-preconfigured Agent composed from multiple Experts. Tagged `origin=ICODER_CLEAN_ROOM`, `official_corti_preset=false` unless Corti's public docs explicitly enumerate it. |
| **Task** | A run-time state machine: `submitted` / `working` / `input_required` / `completed` / `failed` / `canceled`. Has `history`, `referenceTaskIds`, `contextId`, result artifacts, error envelope. |
| **Context** | A conversation-scoped message and memory container, tenant-owned. Deletion scrubs message content + memory chunks + artifact content; retains minimal audit metadata. |
| **Artifact** | A structured output (structured data / Markdown / source citations / expert invocation trace). Tenant-owned. |
| **Memory** | A retrieval index over current Context (TextPart + DataPart). Returns referenced message IDs / artifact IDs. Lexical baseline; embedding tier optional and gated by Provider egress policy. |

## §10. Acceptance conditions (verified at end of phase, A1B-AE.11)

A capability is `HUMAN_WORKFLOW_VERIFIED` only if all 11 conditions in §1.3
of the originating brief are independently reproduced from evidence. The
phase closes only when:

1. Corti public Agentic contracts rebuilt via headed-browser observation;
   unknown items marked `UNKNOWN`.
2. Agent / Expert / Pack / Tool taxonomy unified.
3. Expert Registry runnable.
4. Agent CRUD + Agent Card runnable and consistent across Hub / A2A / clone /
   admin / runtime registries.
5. Message → Task → Context lifecycle runnable.
6. Context deletion verified (content scrub; minimal audit retained).
7. Memory / Calculator / PubMed / Clinical Trials / Interviewing / Coding
   Experts runnable. DrugBank / POSOS kept `LICENSE_REQUIRED` (no fake run).
8. ≥4 iCoder Preset Agents operable via UI.
9. All 10 headed-browser journeys complete with evidence.
10. Cross-tenant negative tests pass.
11. No external-Expert PHI egress.
12. Pack/Agent count assertions no longer hardcoded.
13. Seed/Pack/DB shadowing resolved.
14. Clone-404 resolved.
15. Agent-Card consistency resolved.
16. MCP-rule assertion, singleton pollution, targeted schema drift resolved.
17. OpenAPI and SDK consistent (CI drift detection).
18. No new test FAIL or ERROR.
19. No unapproved security-test skip.

If any of the above fails, the verdict is the *filing* verdict only (see §11).

## §11. Verdict (binding; no substitution permitted)

This Charter authorises exactly one final verdict:

```
PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED
```

The following verdicts are FORBIDDEN (Charter §22 of the originating brief):

- `PRODUCTION_READY`
- `FULLY_VERIFIED`
- `PHI_BOUNDED`
- `CORTI_PARITY_VERIFIED`
- `PASS_A1A_GATE4_FINAL`
- `READY_FOR_HOSPITAL_DEPLOYMENT`
- `CLINICAL_GRADE_VERIFIED`
- `CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED`

Any commit, report, or conversation that emits a forbidden verdict is a
Charter violation and must be reverted.

## §12. Suggested commit sequence (non-binding; may be amended within scope)

| # | Commit | Scope |
|---|---|---|
| 1 | `A1B-AE.0` | Charter + baseline + human-operation protocol (this document + companions) |
| 2 | `A1B-AE.1` | Corti official Agentic manual observation + clean-room contracts |
| 3 | `A1B-AE.2` | Agent / Expert taxonomy + canonical catalogs |
| 4 | `A1B-AE.3` | Expert Registry (model + alembic + API) |
| 5 | `A1B-AE.4` | Agent CRUD + Agent Card + alias / version resolution |
| 6 | `A1B-AE.5` | Message → Task → Context + Memory Expert |
| 7 | `A1B-AE.6` | Calculator + PubMed + Clinical Trials Experts |
| 8 | `A1B-AE.7` | Interviewing Expert + Coding wrapper + external-Expert gates |
| 9 | `A1B-AE.8` | iCoder Preset Agents (5 clean-room agents) |
| 10 | `A1B-AE.9` | Agent/Expert tech-debt liquidation |
| 11 | `A1B-AE.10` | 10 headed-browser journeys + evidence |
| 12 | `A1B-AE.11` | Final reconciliation report + verdict |

Each commit MUST use an explicit `git add <file>` list. No `git add -A`.

## §13. Git evidence chain (binding)

Every commit MUST record, in its commit message body or a sidecar artefact:

- Verified HEAD SHA before commit
- Verified HEAD SHA after commit (the commit being added)
- Branch (must be `phase-a1b/agent-expert-clean-room`)
- Worktree path
- Explicit file list (no wildcards)
- Browser evidence path (for UI-verifying commits)
- Test log path
- SHA-256 of this Charter at commit time
- Charter-version binding (this document is v1.0)

The chain MUST be independently reproducible from `git log`, `git show`,
the `reports/phase-a1b/` directory, and the `reports/phase-a1b/evidence/`
directory. No claim may depend on a private artefact.

---

End of Charter.
