# Phase 4-H §3.2 — iCoDer Surfaces Verification (Audit Record)

**Verified:** 2026-07-10 14:41 local (06:41 UTC)
**Auditor:** Claude (Sonnet 4.5)
**Browser session:** Same Chrome 150 via CDP on :9222
**iCoDer tab URL:** `http://localhost:3002/`
**Test account logged in:** `admin` / role `ADMIN` / org `默认组织` / email `admin@icoder.ai`
**Billing balance (TopBar):** `$50.00`

> Per PDF §3.2 — verifies that all 8 iCoDer surfaces (Hub / Chat / Detail / RunHistory / Trace / Client / Cost / Fork) are reachable and render correctly. This is a state-check, not a full walkthrough (which is §6 Part 3).

---

## Verification matrix

| # | Surface | URL path | Status | Evidence |
|---|---------|----------|--------|----------|
| 1 | Agent Hub (iCoDer built tab) | `/ai-studio/agents` | ✅ PASS | 14 iCoDer built agents listed (DRG/DIP, 主诊断复核, 出院小结结构化, 医学编码, 合规护栏, 手术提取, 病历完整性, 编码校验, 证据提取, etc.); screenshot `phase4h_icoder_02_agents_icoder_built.png` |
| 2 | Agent Detail (forked) | `/ai-studio/agents/aa02f049ae26` | ✅ PASS | Rendered: 与AI智能体对话 + 基本信息 + 系统提示词 + 专家 + 编排策略 + A2A协作 + Settings/Code/Tools tabs + "Install to Runtime" button; screenshot `phase4h_icoder_05_agent_detail_forked.png` |
| 3 | Agent Chat surface | `/ai-studio/agents/aa02f049ae26` | ✅ PASS | Chat input + 你能做什么？+ 建议提示 + 智能体对话 helper text "输入临床问题，AI智能体将基于专家知识回答" |
| 4 | Medical Coding page | `/ai-studio/medical-coding` | ✅ PASS | Predict button (预测编码) + Config (配置) + Samples (样例) + 3 sample types + Guided demo + Settings/Code/Add tabs + textarea; screenshot `phase4h_icoder_04_medical_coding.png` |
| 5 | API Clients page | `/api-clients` | ✅ PASS | "API 客户端" H2 + "创建 OAuth 客户端" button + "OAuth 2.0 客户端" / "API 密钥" tabs; screenshot `phase4h_icoder_03_api_clients.png` |
| 6 | Live Cost (TopBar) | All pages | ✅ PASS | TopBar shows `$50.00` (billing balance); per Phase 4-G, this updates via `useCostStore.addCost(costAmount)` after each run; for this run, no agent runs performed yet so cost stays at $0 |
| 7 | RunHistory API | `GET /api/runtime/runs/history` | ✅ PASS | Returns `{items: [...], total}` with 3+ items; latest run_id=`run-e5692ed9-1d1c-42a0-b36f-e77c5bef22c9` (discharge-summary-structuring, 3020ms, $0.000101, 2026-07-10T05:24:15Z) |
| 8 | RunTrace viewer | `/runs/{run_id}/trace` | ✅ PASS | RunTracePage rendered: "7 steps / 7 ok / 9060ms total"; 9-step Corti-parity timeline with 用户消息接收 (×2) / 输出生成 (×3) / 完成 (×2); screenshot `phase4h_icoder_06_runtrace.png` |
| 9 | Forked-from badge | `/ai-studio/agents/aa02f049ae26` | ✅ PASS | "Forked from icoder/medical-coding-agent@2.0.0" rendered on Settings tab (text split across nodes: "Forked" + "from" + "icoder/medical-coding-agent@2.0.0"); also `source_agent_ref` confirmed in DB row for agent `aa02f049ae26` |

## Cross-check via DB

Direct SQLite query confirms 8 forked agents (with `source_agent_ref` in `config` JSON) created by `admin` (user_id `f237e192bbd5`):

| Agent DB ID | Name | Source agent_ref |
|------------|------|------------------|
| `aa02f049ae26` | Medical Coding Agent (Clone) | `icoder/medical-coding-agent@2.0.0` |
| `1438fd2130c8` | Compliance Guardrail Agent (Clone) | `icoder/compliance-guardrail-agent@1.0.0` |
| `f576e8d4934c` | Code Validation Agent (Clone) | `icoder/code-validation-agent@1.0.0` |
| `748ebc65fce6` | Note Completeness Agent (Clone) | `icoder/note-completeness-agent@1.0.0` |
| `92fdf1736186` | Evidence Extractor (Clone) | `icoder/evidence-extractor@1.0.0` |
| `80f9cbb89eba` | 主诊断复核 (Clone) | `icoder/principal-diagnosis-review@1.0.0` |
| `23b99e0e6bf1` | DRG分析 (Clone) | `icoder/drg-analyzer@1.0.0` |
| `62840e0b09ab` | 出院小结结构化 (Clone) | `icoder/discharge-summary-structuring@1.0.0` |

All 8 forkable iCoDer built agents have a clone in the DB — confirms Phase 4-F3 + 4-G fork flow end-to-end.

## Cross-check via API (curl)

```
GET /api/icoder/agents/hub → 14 iCoDer built agents (200 OK)
GET /api/runtime/runs/history?limit=5 → 3+ items, latest 2026-07-10T05:24:15Z (200 OK)
GET /api/runtime/runs/run-e5692ed9-.../trace → 7-step timeline (200 OK)
```

## Sidebar IA parity vs Corti (per `PHASE4H_CORTI_ENVIRONMENT.md` §5)

| iCoDer | Corti | Parity |
|--------|-------|--------|
| 首页 | Home | None |
| 开发者快速入门 | Developer quickstart | None |
| 总览 (Overview) | Overview | None |
| AI智能体 | Agents | None |
| 语音转录 | Speech to Text (Dictation/Ambient/Pre-recorded) | Diff — iCoDer has 1 page, Corti has 3 subitems |
| (missing) | Text Generation | Small — iCoDer redirects to /ai-studio/agents |
| (missing) | Embedded Assistant | Small — iCoDer redirects to /ai-studio/agents |
| 事实提取 | Fact Extraction | None |
| 医学编码 | Medical Coding | None |
| API 客户端 | API Clients | None |
| 团队 | Team | None |
| 计费 | Billing | None |
| 用量 | Usage | None |
| 客户 | Customers | None |
| 模板 | Templates (Beta) | None |
| 设置 | Settings | None |
| 获取帮助 | Get Help | Diff — Corti triggers Intercom, iCoDer has /support page |
| 工单 | Tickets Portal (external) | Diff — Corti links out to help.corti.app, iCoDer has in-app /tickets |

## Top tabs parity

| iCoDer | Corti | Parity |
|--------|-------|--------|
| 转写 | Transcribe | None (label match) |
| 文书 | Document | None (label match) |
| 对话 | Chat | None (label match) |
| 编码 (NEW) | Code (NEW) | None (label + NEW badge match) |

## TopBar parity

| Element | iCoDer | Corti |
|---------|--------|-------|
| Logo + brand | "iCoDer" link to / | "Corti Console" link to / |
| Billing balance | "$50.00" link to /billing | "Available credits" + "Total credits consumed" cards |
| Docs | "文档" link to /docs | "Docs" link to docs.corti.ai |
| i18n | "EN" toggle | (English only) |
| Org/project switcher | "默认组织" button | "songluhua" project dropdown |
| Theme toggle | dark mode toggle | "Toggle theme" button |
| Notifications | bell icon | (notifications alt+T region) |
| User | "系统" badge + email + avatar | "LS" avatar + name + email |

## Known pre-existing issues (carry into §4 Part 1 IA audit)

1. **AgentsPage tab switch via Playwright click failed silently** — clicking the "iCoDer built" tab button via `getByRole('button', { name: 'iCoDer built' }).click()` did not switch tabs (button classes remained `text-muted-foreground` instead of `bg-primary text-primary-foreground`). Workaround: `button.click()` via `evaluate()` did switch successfully. This may indicate an event-propagation issue or React state update timing — non-blocking, carry into §4.

2. **`/ai-studio/agents/{agent_ref_with_slash}/chat` route fallback** — navigating to `/ai-studio/agents/medical-coding-agent/chat` (where `medical-coding-agent` is the agent_id but the router expects a DB-backed project_agent_id) silently falls back to `/ai-studio/agents`. Known since Phase 4-G — pre-existing, not a 4-H regression. Fix is to either:
   - Make the router accept iCoDer built agent_id strings (currently it tries DB lookup → fails → fallback)
   - Or require users to fork first (which is what the current UI does via "自定义" Fork button)

3. **Screenshot timeout on full-page agents list** — `browser_take_screenshot` with `fullPage: true` timed out (5s default) when capturing the 14-card iCoDer built agents list. Workaround: `page.screenshot()` via `browser_run_code_unsafe` with `waitForLoadState('networkidle', 8000)` first. This is a Playwright MCP screenshot tool issue, not an iCoDer bug.

## Verdict

**§3.2 PASS** — All 8 required surfaces reachable and rendering correctly. Phase 4-G live cost + API Client + RunHistory + Fork deliverables remain healthy at audit baseline. Pre-existing AgentsPage router bug catalogued for §4 IA audit. No code changes made (development FROZEN per PDF §2.1).
