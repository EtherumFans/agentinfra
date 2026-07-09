# iCoDer Redesign Backlog — Post Phase 4-E3 Browser Walkthrough

**Date**: 2026-07-09
**Source**: `ICODER_CORTI_BROWSER_WALKTHROUGH_REPORT.md` + `ICODER_CORTI_GAP_MATRIX.csv` (60 findings)
**Scope**: P0-P3 prioritized refactor backlog based on Phase 4-E3 walkthrough findings

---

## P0 — Immediate (this sprint, 1 week)

### P0-1: Fix MedCodER 60s timeout (G001)

- **Severity**: S1 (Critical — blocks core medical coding use case)
- **Gap type**: RUNTIME_GAP
- **Module**: Medical Coding
- **Effort**: 3-5 days
- **Owner**: Backend Runtime

**Problem**: iCoDer MedCodER 5-stage pipeline (extract/retrieve/merge/rerank/compliance) exceeds 60s frontend timeout on T12 vertebral fracture case. Corti returns 7 ICD codes in ~8s with simpler single-stage LLM call.

**Backend changes**:
1. Warm-load BGE-M3 + FAISS at backend startup in `app/main.py` lifespan (`await medcoder_retriever.warm()`).
2. Parallelize Stage 1 (extraction) + Stage 2 (retrieval) via `asyncio.gather` — retrieval uses raw query embedding, not extraction output.
3. Add SSE streaming endpoint `GET /api/v2/tools/coding/stream` emitting `stage_started` / `stage_completed` / `partial_codes` / `final_codes` events.
4. Add prompt-only fast path: if `input.length < 200` OR `mode != "medcoder"`, skip Stage 2 + Stage 4 (single DeepSeek call like Corti).
5. Cache extraction embeddings in Redis with 1h TTL keyed by `hash(input_text)`.

**Frontend changes**:
1. Replace `POST` with `EventSource` in MedicalCodingPage to subscribe to SSE stream.
2. Add 5-dot stage progress indicator filling as stages complete.
3. Render partial codes as they arrive (show Stage 1 LLM codes first, then Stage 4 re-ranked codes).
4. Increase fallback timeout to 120s as stopgap.

**Acceptance criteria**:
- Simple case (<200 chars): <15s response
- Complex case: <45s response with SSE streaming
- 95th percentile <60s
- No 60s timeout failures on standard test cases

**Evidence**: `scenario_02_corti_result.png` + `scenario_05_icoder_timeout.png` + backend log (2 DeepSeek 200 OK calls at 16:12:10 + 16:12:15 but frontend timeout at 16:13:09)

---

## P1 — Next sprint (2 weeks)

### P1-1: Fix broken 语音转录 sidebar link (G002)

- **Severity**: S2 (Major — UX trust erosion)
- **Gap type**: IA_GAP
- **Module**: Speech to Text
- **Effort**: 0.5 day
- **Owner**: Frontend IA

**Problem**: Clicking 语音转录 in sidebar redirects to `/` (HomePage) silently. Route was removed in Phase 3-B2 (commit 5c4e0e3) but sidebar IA not synced.

**Recommended fix**: Option A — Remove 语音转录 from sidebar entirely (aligns with Phase 3-B2 route removal, STT not on near-term roadmap).

**Alternative**: Option B — Re-add `/ai-studio/speech-to-text` route stub with "敬请期待" (Coming Soon) page.

**Implementation (Option A)**:
1. Edit `frontend/src/components/layout/Sidebar.tsx` (or equivalent) to remove 语音转录 nav item.
2. Update i18n keys in `frontend/src/i18n/locales.ts` to drop `speechToText` label.
3. Run `tsc` + `vitest` to verify no broken references.
4. Browser walkthrough: verify sidebar no longer has 语音转录 link.

**Acceptance criteria**:
- Sidebar no longer shows 语音转录 link.
- No route 404s or silent redirects to `/`.
- tsc 0 errors + vitest pass.

**Evidence**: `App.tsx` lines 68-84 (route removed) + `icoder_03_ai_studio_overview.png` (sidebar still shows link)

### P1-2: Maintain Developer Quickstart advantage (G015)

- **Severity**: S0 (iCoDer exceeds Corti — maintain advantage)
- **Gap type**: DEVEX_WIN
- **Module**: Developer Quickstart
- **Effort**: Ongoing (quarterly investment)
- **Owner**: DevRel

**Action**: No immediate fix needed. Continue investing in:
- Add more use case examples (streaming / webhooks / batch)
- Add more AI coding tool examples (e.g. Windsurf / Replit)
- Add streaming code examples for SSE endpoints
- Add interactive API Playground for all major endpoints

**Evidence**: `cortic_22_developer_quickstart.png` (3 use cases + 1 SDK) vs `icoder_15_developer_quickstart.png` (4 use cases + 4 AI tools + API Playground)

### P1-3: Plan MedCodER pipeline streaming UI (G053, related to G001)

- **Severity**: S1 (depends on G001 backend fix)
- **Gap type**: CAPABILITY_WIN (advanced but currently broken)
- **Module**: Medical Coding
- **Effort**: 1 day UI planning (after G001 backend lands)
- **Owner**: Frontend + Product

**Action**: Design and prototype the streaming UI for MedCodER pipeline:
1. Stage progress indicator (5 dots: Extract → Retrieve → Merge → Re-rank → Compliance)
2. Partial codes display (Stage 1 LLM codes → Stage 4 re-ranked codes → Stage 5 calibrated codes)
3. Per-stage latency timer (debug mode)
4. Confidence score visualization per code

**Evidence**: `icoder_07_medical_coding.png` (current static UI) + MedCodER 5-stage architecture in `CLAUDE.md`

---

## P2 — Later this quarter (1-3 months)

### P2-1: Add live cost counter on AgentChatPage (G007)

- **Severity**: S2 (Major — billing transparency gap)
- **Gap type**: UX_GAP
- **Module**: Agent Chat
- **Effort**: 1-2 days
- **Owner**: Frontend + Backend

**Problem**: Corti agent detail page top breadcrumb bar shows live cost counter ($0.000000) + Reset live cost + API Client dropdown. iCoDer agent chat page top breadcrumb bar has no live cost counter — users cannot see real-time credit consumption during agent runs.

**Backend changes**:
1. Implement `GET /api/v1/usage/live-cost` SSE endpoint — emit `{cost: 0.060820, ts: 1690000000, agent_id, run_id}` on each LLM call.
2. Wire `UsageTracker` into `LLMGateway` — emit event on each successful DeepSeek response.
3. Add `POST /api/v1/usage/live-cost/reset` endpoint to zero the counter.

**Frontend changes**:
1. In AgentChatPage top breadcrumb bar, add `$0.000000` live cost link + Reset button (next to breadcrumb).
2. Subscribe to `/api/v1/usage/live-cost` SSE via `EventSource`.
3. On Reset click, send POST to reset endpoint and zero the counter.
4. On agent chat run, increment counter as costs arrive.
5. Persist counter across page reloads via localStorage.

**Acceptance criteria**:
- Live cost counter renders in agent chat top bar.
- Counter increments within 1s of backend LLM call completion.
- Reset button zeros the counter and persists across reloads.
- AA contrast ratio on counter text.

**Evidence**: `cortic_06_agent_detail_medical_coding.png` (has $0.000000 + Reset) vs `icoder_06_agent_chat_medical_coding.png` (no counter)

### P2-2: Build Web Component SDK (G056)

- **Severity**: S3 (Minor — feature gap for hospital embedded integration)
- **Gap type**: INTEGRATION_GAP
- **Module**: Embedded Assistant
- **Effort**: 5-7 days
- **Owner**: DevRel + Frontend

**Problem**: Corti has Embedded Assistant page with Web Component SDK + embed snippet. iCoDer Cloud-Flip architecture (2026-06-27) planned ROPC embedded pattern but Web Component SDK not yet built.

**Implementation**:
1. Extract `frontend/src/components/AgentChat.tsx` into a framework-agnostic Web Component.
2. Publish as `@icoder/web-component` npm package.
3. Add embed snippet wizard in `/developer-quickstart` showing:
   ```html
   <script src="https://cdn.icoder.cloud/widget.js"></script>
   <icoder-agent agent-id="..." tenant="..." auth="ropc" />
   ```
4. Document auth flow (ROPC vs backend-service) in `/developer-quickstart`.
5. Add sandbox playground for testing embed snippet.

**Acceptance criteria**:
- Web Component renders in plain HTML page.
- Auth flow works for both ROPC and backend-service patterns.
- Embed snippet wizard generates copy-pasteable code.
- Sandbox playground demonstrates live interaction.

**Evidence**: `cortic_12_embedded_assistant.png` (Corti Web Component SDK) vs App.tsx redirect line 82

### P2-3: Implement CN-DRG rule set (G046)

- **Severity**: S0 (iCoDer advantage — reserved but not implemented)
- **Gap type**: LOCALIZATION_WIN
- **Module**: DRG/DIP Compliance
- **Effort**: 10-15 days
- **Owner**: Backend + Clinical Expert

**Problem**: iCoDer has reserved rule structure for CN-DRG/DIP in `backend/app/compliance_services/` but rule set is not implemented. Corti has no DRG/DIP support (US/EU focus).

**Implementation**:
1. Partner with clinical coding expert for CN-DRG rule authoring (group rules / complication rules / outlier rules / DRG boundary rules).
2. Add `backend/app/compliance_services/drg_dip_rule_set.py` implementing `RuleSet` interface.
3. Register rule set in `RuleEngine` registry.
4. Add `/api/v1/drg/group` endpoint — input is ICD codes + procedure codes + demographics, output is DRG group + weight + outlier flag.
5. Add tests with real CN-DRG cases (use 国家医保局 CHS-DRG 376 groups as reference).
6. Frontend: Add DRG tab in MedicalCodingPage output pane showing group + weight + outlier.

**Acceptance criteria**:
- DRG grouping matches 95%+ of CHS-DRG reference cases.
- Outlier detection works for high-cost / long-stay cases.
- Frontend DRG tab renders alongside ICD codes.

**Evidence**: `backend/app/compliance_services/` rule set registry + CLAUDE.md architecture section

### P2-4: Add announcement banner slot (G049)

- **Severity**: S3 (Minor — feature announcements missed)
- **Gap type**: UX_GAP
- **Module**: Home
- **Effort**: 1 day
- **Owner**: Frontend + Backend

**Problem**: Corti has dismissible announcement banner on home (e.g. "Corti Models is here"). iCoDer has no announcement banner — users may miss new feature updates.

**Implementation**:
1. Backend: Add `GET /api/v1/announcements` endpoint returning active announcements (sorted by priority).
2. Frontend: Add dismissible banner slot at top of HomePage — render first active announcement.
3. Dismissal persisted via localStorage (don't re-show for 7 days).

**Acceptance criteria**:
- Banner renders at top of HomePage when active announcement exists.
- Dismiss button hides banner for 7 days.
- No banner when no active announcements.

**Evidence**: `cortic_02_console_home.png` (has banner) vs `icoder_02_home.png` (no banner)

---

## P3 — Backlog (>3 months)

### P3-1: Add Corti Models equivalent page (G003)

- **Severity**: S3 (Minor — China market may not need)
- **Gap type**: CAPABILITY_GAP
- **Module**: Corti Models
- **Effort**: 2 days
- **Owner**: Product + Backend

**Problem**: Corti has dedicated Corti Models page showcasing frontier LLMs hosted on EU infrastructure. iCoDer has no equivalent — LLM is implicit DeepSeek config.

**Recommendation**: Optional — China market uses DeepSeek (no need for EU-hosted frontier models). If built later, page should show:
- Available LLM providers (DeepSeek / Qwen / GLM / etc.)
- Capability matrix (coding accuracy / latency / cost / context length)
- Per-tenant LLM routing config

**Evidence**: `cortic_23_corti_models.png`

### P3-2: Plan STT sub-modes (G004)

- **Severity**: S3 (Minor — STT is Corti core feature, iCoDer hasn't built)
- **Gap type**: CAPABILITY_GAP
- **Module**: Speech to Text
- **Effort**: 10-15 days
- **Owner**: Backend + ML

**Problem**: Corti has 3 STT modes: Dictation (real-time) / Ambient (background) / Pre-recorded (audio file upload). iCoDer has no STT capability.

**Recommendation**: Plan Phase 5+ integration:
- Evaluate Whisper-large (open-source, multilingual) vs 阿里云 ASR (China-optimized).
- Medical domain fine-tuning (medical terms / drug names / procedure names).
- Real-time streaming via WebSocket for Dictation mode.
- File upload + transcript for Pre-recorded mode.
- Background recording with VAD for Ambient mode.

**Note**: Large effort — defer until MedCodER (G001) + Web Component SDK (G056) + CN-DRG (G046) are done.

**Evidence**: `cortic_08_stt_dictation.png` + `cortic_09_stt_ambient.png` + `cortic_10_stt_prerecorded.png`

### P3-3: Optional Text Generation standalone page (G005)

- **Severity**: S3 (Minor — intentionally removed in Phase 3-B2)
- **Gap type**: CAPABILITY_GAP
- **Module**: Text Generation
- **Effort**: 1 day if needed
- **Owner**: Frontend

**Problem**: Corti has Text Generation page for clinical document generation. iCoDer removed TextGenerationPage in Phase 3-B2 (collapses into Agent Hub).

**Recommendation**: Keep Agent Hub as umbrella. If users need dedicated page later:
- Add `/ai-studio/text-generation` with agent picker (which text-gen agent to use?)
- Reuse AgentChatPage layout with text-gen specific presets

**Evidence**: `cortic_11_text_generation.png` + App.tsx line 81 redirect

### P3-4: Optional URL pattern with /:tenant_slug prefix (G018)

- **Severity**: S3 (Minor — single-tenant session design works for now)
- **Gap type**: UX_DIFF
- **Module**: Routing
- **Effort**: 2 days
- **Owner**: Backend

**Problem**: Corti URL: `/project/{project_id}/ai-studio/agents/{agent_id}` (project-scoped). iCoDer URL: `/ai-studio/agents/{agent_id}/chat` (flat, no project ID; tenant implied by JWT).

**Recommendation**: Optional — add `/:tenant_slug` prefix for public sharing / multi-tenant URL clarity. Not blocking since JWT-based auth works.

**Evidence**: URL pattern comparison

### P3-5: Project switcher clarity (G019 + G055)

- **Severity**: S3 (Minor — UX confusion)
- **Gap type**: UX_GAP
- **Module**: Top Bar
- **Effort**: 0.5-1 day
- **Owner**: Frontend

**Problem**: Corti sidebar header has clear project switcher (avatar + project name). iCoDer has ?? button top-right (purpose unclear — likely project switcher but unlabelled).

**Recommendation**:
1. Audit ?? button — if it's a project switcher, label with avatar + project name.
2. If it's a theme toggle or other, remove and consolidate into Settings page.
3. Add explicit project switcher in sidebar header (matching Corti pattern).

**Evidence**: `cortic_02 sidebar` vs `icoder_02_home top-right`

### P3-6: Top bar clutter audit (G020)

- **Severity**: S3 (Minor — UX clutter)
- **Gap type**: UX_GAP
- **Module**: Top Bar
- **Effort**: 1 day
- **Owner**: Frontend

**Problem**: iCoDer top header right has 6 controls: 文档 + EN + Test + dark mode + ?? + ?? (2 unlabelled). Corti top breadcrumb bar right has 2 controls: theme + Docs.

**Recommendation**:
1. Audit each control's purpose and usage frequency.
2. Remove duplicates (e.g. if ?? is theme toggle, remove redundant dark mode button).
3. Consolidate language (EN) + theme into single settings dropdown.
4. Move Test button to DevQuickstart page (not user-facing).
5. Keep 文档 (Docs) as single right-side link.

**Evidence**: `icoder_02_home.png` top-right

### P3-7: Embedded Assistant standalone page (G006)

- **Severity**: S3 (Minor — intentionally removed)
- **Gap type**: CAPABILITY_GAP
- **Module**: Embedded Assistant
- **Effort**: 2 days
- **Owner**: DevRel

**Problem**: Corti has Embedded Assistant page with Web Component SDK. iCoDer removed in Phase 3-B2 (collapses into Agent Hub + API Clients).

**Recommendation**: After P2-2 (Web Component SDK) lands, add standalone `/developer-quickstart/embedded` wizard showing embed snippet + sandbox playground. Don't add as AI Studio page (keep under Dev Quickstart).

**Evidence**: `cortic_12_embedded_assistant.png` + App.tsx line 82 redirect

---

## Maintained Advantages (no action — continue investing)

### M1: Chinese clinical templates (G014)

- **Advantage**: 9 Chinese clinical categories (出院小结/入院记录/手术记录/查房记录/交接班记录/疑难病例讨论/术前讨论/术后讨论/死亡病例讨论) vs Corti 6 generic templates.
- **Action**: Continue adding categories quarterly (e.g. 门诊病历 / 电子病历 / 护理记录).
- **Owner**: Product + Clinical

### M2: Developer onboarding (G015)

- **Advantage**: 4 use cases + 4 AI tools (Claude Code / Cursor / Codex / Lovable) + API Playground vs Corti 3 use cases + 1 SDK button.
- **Action**: Add more AI tools (Windsurf / Replit) + streaming examples + interactive playground for all endpoints.
- **Owner**: DevRel

### M3: Agent card metadata (G016)

- **Advantage**: iCoDer shows status / mode / production_ready / date / author / category / version vs Corti name + description + use case.
- **Action**: Consider UX densification for visual hierarchy (currently metadata-heavy).
- **Owner**: Frontend

### M4: ICD-10-CN catalog (G033 + G054)

- **Advantage**: 37,897 codes + 75,968 synonyms + 972-code evidence anchoring KB + 2,090 code-pair differentiation KB.
- **Action**: Add more synonyms + evidence patterns quarterly.
- **Owner**: Backend + Data

### M5: MedCodER 5-stage pipeline (G053, after G001 fix)

- **Advantage**: 5-stage extract/retrieve/merge/rerank/compliance pipeline (NAACL 2025 reference) — higher accuracy than Corti's single-stage.
- **Action**: Fix 60s timeout (G001), add streaming, add more CoT few-shot cases, add calibration improvements.
- **Owner**: Backend Runtime + ML

### M6: RunTrace 9-step timeline (G031)

- **Advantage**: iCoDer RunTracePage has 9-step timeline + DB persistence vs Corti's simpler run trace viewer.
- **Action**: Continue investing in trace detail (MCP tool traces / expert delegation traces / etc.).
- **Owner**: Frontend + Backend

### M7: PHI redaction + MCP auth (G030 + G044)

- **Advantage**: iCoDer has 3-layer PHI redaction + 4 MCP auth types + 7 error codes — matches Corti with stronger guarantees for China compliance.
- **Action**: Maintain parity; add more auth types as needed (e.g. mTLS for hospital-internal).
- **Owner**: Backend Governance

---

## Summary

| Priority | Count | Total effort | Owners |
|----------|-------|--------------|--------|
| P0 | 1 | 3-5 days | Backend Runtime |
| P1 | 3 | 1.5 days + ongoing | Frontend IA + DevRel + Frontend |
| P2 | 4 | 17-22 days | Frontend+Backend + DevRel+Frontend + Backend+Clinical + Frontend+Backend |
| P3 | 7 | 17-22 days | Various |
| Maintained | 7 | Ongoing | Various |

**Top 3 priorities to ship this quarter**:
1. **P0-1 G001**: Fix MedCodER 60s timeout (3-5 days, Backend Runtime)
2. **P1-1 G002**: Fix broken 语音转录 sidebar link (0.5 day, Frontend IA)
3. **P2-1 G007**: Add live cost counter on AgentChatPage (1-2 days, Frontend+Backend)

**Critical path**: G001 must land before any clinical deployment. G001 blocks the core medical coding use case.

---

**Backlog end**.
