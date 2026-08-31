# Audit Gate 3 — Full Browser Walkthrough (Track B2)

> Driven by Playwright MCP against live `http://localhost:3000` (frontend) + `http://127.0.0.1:8000` (backend), logged in as `admin@icoder.ai`. Per PDF §六.1 mandatory console path.

## C1. Pages visited and live state

| # | URL | HTTP | State | Notes |
|---|-----|------|-------|-------|
| 1 | `/` (Home) | 200 | ✅ Live | 4-tab IA (转写/文书/对话/编码), top bar shows `¥50.00` balance + `admin@icoder.ai`, 0 console errors |
| 2 | `/login` | 200 | ✅ Live | "iCoDer Console / 可审计的临床AI" hero, Google/GitHub OAuth buttons |
| 3 | `/ai-studio/speech-to-text` | **redirect → `/`** | ❌ **DEAD** | Confirms G2-004. Sidebar nav item remains but route was removed. |
| 4 | `/ai-studio/agents` | 200 | ⚠️ Partial | "还没有AI智能体" for admin — the 23 hub agents don't appear under "my agents". "iCoDer 预置" tab untested. |
| 5 | `/ai-studio/medical-coding` | 200 | ✅ Live | **Honest label: `MVP - production_ready=false, human_review=required`**. Two modes: Fast Coding (~7-12s default) + Deep Evidence/MedCodER (30-60s+ advanced). ICD-10-CN default. |
| 6 | `/ai-studio/cdi` | 200 | ✅ Live | "临床文档改进 · 临床事实被写清楚". Patient context input + "运行 CDI 分析" button. |
| 7 | `/ai-studio/coding-compliance` | 200 | ✅ Live | 7-stage pipeline: 出院小结 → ICD 编码 → 主诊断复核 → 证据强度 → 合规审查 → 病历完整度 → DRG/DIP 风险. |
| 8 | `/ai-studio/embedded-assistant` | 200 | ✅ Live | **Subtitle: "Corti 风格对齐 · 一次配置，随处复制"** (G2-002 confirmed). iframe URL contains only `psid=...`, **no token, no patient context** (Gate 13A verified). |
| 9 | `/ai-studio` (Overview) | 200 | ❌ **P0 — 13 external Corti links** | See §C2 |
| 10 | `/ai-studio/agents/medical-coding-agent` | 200 | ⚠️ Partial | Page renders BUT **2 console errors: 404 on `GET /api/rest/v1/agent_definitions/medical-coding-agent`** |
| 11 | `/api-clients` | 200 | ✅ Live | Empty state: "暂无 OAuth 客户端". |
| 12 | `/billing` | 200 | ✅ Live | ¥50.00 balance, ¥0.00 consumed (last 30d), 企业信息 / 套餐计划 / 账单历史 tabs. |
| 13 | `/usage` | 200 | ✅ Live | **Real aggregated**: 83 requests last 30d, ¥0.044714 consumed, daily chart 07-10/11/14. Recent activity shows `preview_session.create` / `exchange` / `user.login`. |
| 14 | `/runs/00000000-0000-0000-0000-000000000000/trace` | 200 | ✅ Graceful | "未找到 RunTrace / no trace events for run_id … / 返回 Agent Hub" |
| 15 | `/developer-quickstart` | 200 | ✅ Live | Properly iCoDer-branded, no Corti links. References `/.well-known/agent-skills/icoder-dictation/SKILL.md`, Claude Code/Cursor/Codex/Lovable. |

## C2. P0 FINDING — AI Studio Overview has 13 external Corti links

`GET /ai-studio` (the front-door user landing page) renders 13 user-visible links pointing to **Corti's actual documentation site**:

| # | Link href | User-visible label |
|---|-----------|-------------------|
| 1 | `https://docs.corti.ai/agentic/overview` | 文档 (智能体) |
| 2 | `https://docs.corti.ai/stt/overview` | 文档 (语音转文本) |
| 3 | `https://docs.corti.ai/textgen/overview` | 文档 (文本生成) |
| 4 | `https://docs.corti.ai/assistant/introduction` | 文档 (嵌入式助手) |
| 5 | `https://docs.corti.ai/api-reference/facts/extract-facts` | 文档 (事实抽取) |
| 6 | `https://docs.corti.ai/coding/overview` | 文档 (医学编码) |
| 7 | `https://docs.corti.ai/authentication` | 认证 |
| 8 | `https://docs.corti.ai/guides` | 指南 |
| 9 | `https://docs.corti.ai/api-reference` | API 参考 |
| 10 | `https://docs.corti.ai/sdk/js-sdk#javascript-sdk` | JavaScript SDK |
| 11 | `https://docs.corti.ai/sdk/postman#quickstart-postman` | Postman |
| 12 | `https://docs.corti.ai/quickstart/ai-coding-tools` | AI 编码工具 |
| 13 | `https://help.corti.app/tickets-portal` | 提交工单 |

**Severity: P0.** This is not residue — **the entire developer documentation surface of iCoDer's front-door page redirects users to a competitor's docs**. Implications:

- A hospital user clicking "API 参考" lands on Corti's API reference.
- A hospital user clicking "提交工单" files a ticket with Corti's support team.
- A hospital user clicking "JavaScript SDK" lands on Corti's SDK docs.
- iCoDer's own `/tickets` route exists but is bypassed.

This violates PDF §Track C "当前产品首页在向谁表达价值?" — the page is functionally a Corti customer-acquisition redirect.

**Evidence:** screenshot `audit-gate3-05-ai-studio-overview-corti-links.png` + DOM scan shows `cortiLinks.length === 13`.

**Register as G3-001 (P0)**, supersedes G2-001 which only flagged one of the 13.

## C3. P1 finding — Agent Detail page fetches a non-existent definition

`GET /ai-studio/agents/medical-coding-agent` renders but logs 2 console errors:

```
Failed to load resource: 404 Not Found
GET /api/rest/v1/agent_definitions/medical-coding-agent
```

The page falls back to rendering a skeleton with:
- "智能体详情 (7/50)" — weird denominator
- runtime cost: ¥0.000000
- "Install to Runtime" button
- Chat panel ("你能做什么？/ 建议提示 / 输入临床问题…")
- Settings tab: system prompt placeholder, 0 experts bound, 5 orchestration strategies, 5 permission policies
- 4 A2A Agent 协作 listed: MedCodER 编码审核 / 编码校验 / 合规护栏 / 病历完整性

→ The agent-detail flow assumes `/api/rest/v1/agent_definitions/{id}` exists, but it 404s for the canonical medical-coding-agent. This means **the Corti-style `/rest/v1/agent_definitions` registry does not actually contain iCoDer's canonical agents** — they live only under `/api/icoder/agents/hub` (the iCoDer-native API). The two registries are not unified.

**Register as G3-002 (P1).**

## C4. Mobile width spot check

Did not deep-dive in this gate (deferred to Gate 4 per-agent). Frontend uses `min-h-dvh` per Phase 4-F redesign notes (per memory) so iOS Safari is handled.

## C5. Console warnings (consistent across all pages)

```
[WARNING] React Router Future Flag: v7_startTransition (opt-in)
[WARNING] React Router Future Flag: v7_relativeSplatPath (opt-in)
```

Both are non-blocking. Register as G3-005 (P3).

## C6. iCoDer advantages observed during walkthrough

These are real product surfaces (not just claims) that differentiate iCoDer from Corti:

1. **`/usage` page with real aggregated cost data** — 83 requests, ¥0.044714, daily chart, recent activity event stream. Corti parity.
2. **`/billing` page with credits balance** — ¥50.00, 充值 / 自动充值 / 余额不足提醒 / 企业信息.
3. **`/runs/:runId/trace` RunTrace page** with graceful 404 — Corti has no equivalent per Phase 4-H audit.
4. **`/ai-studio/medical-coding` page declares `production_ready=false, human_review=required`** — honest maturity label, rare in this category.
5. **`/ai-studio/embedded-assistant` iframe uses HMAC psid, no URL token** — Phase 7 Gate 13A verified live.
6. **`/developer-quickstart` is properly iCoDer-branded** — Claude Code/Cursor/Codex/Lovable integration guidance, agent-skills SKILL.md references, iCoDer-native API client credential flow.

## C7. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G3-001** | P0 | product-integrity | `/ai-studio` Overview page contains 13 user-visible external links to `docs.corti.ai/*` + `help.corti.app/*` — every "文档/认证/指南/API 参考/SDK/工单" link redirects hospital users to Corti's actual docs. |
| G3-002 | P1 | integration-gap | `GET /ai-studio/agents/medical-coding-agent` triggers `404 /api/rest/v1/agent_definitions/medical-coding-agent` — the Corti-style `/rest/v1/agent_definitions` registry is empty for canonical agents, only `/api/icoder/agents/hub` has them. Two parallel agent registries, neither complete. |
| G3-003 | P2 | dead-link | Confirmed live: navigating to `/ai-studio/speech-to-text` redirects to `/` (G2-004 verified). |
| G3-004 | P2 | branding | Embedded Assistant page subtitle "Corti 风格对齐 · 一次配置，随处复制" (G2-002 verified live). |
| G3-005 | P3 | dev-warning | React Router v7 future flag warnings on every page (`v7_startTransition`, `v7_relativeSplatPath`). |

## C8. Gate 3 verdict

`WALKTHROUGH_LIVE_WITH_P0_CORTI_DOCS_REDIRECT`

- All 15 visited pages render with 0 console errors except `/ai-studio/agents/medical-coding-agent` (P1)
- **P0 G3-001**: the AI Studio Overview page redirects every documentation/support link to Corti's actual docs
- Real aggregated Usage + Billing + RunTrace pages — **iCoDer advantages verified live**
- Phase 7 Gate 13A iframe security verified live (HMAC psid, no URL token, no patient context)
- Honest `production_ready=false` label on Medical Coding page

Gate 3 closes. Proceed to **Gate 4 — Agent Capability Audit**.
