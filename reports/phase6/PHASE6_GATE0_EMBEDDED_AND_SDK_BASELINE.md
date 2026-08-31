# Phase 6 Gate 0 — Embedded Assistant & Developer Integration Baseline Audit

**Date**: 2026-07-13
**Tier**: `GATE0_BASELINE_AUDIT_COMPLETE`
**Auditor**: Phase 6 Gate 0 audit (iCoDer repo + prior Corti audit evidence chain)
**Method**: 仓库静态审计 + 复用 Phase 4-H §11 + Phase 5 A4/A5 现有 Corti 真实走查证据
**Principle**: §4.1 先审计后开发,§4.3 不允许假发布

---

## 1. Executive summary

iCoDer 已交付 Phase 5 A4/A5 的 Corti-compatible `<icoder-embedded>` Web Component
v2.0.0(7/7 Playwright PASS + browser walkthrough 验证)。`packages/icoder-sdk/`
v1.0.0-beta.1 提供 10 个 resource 类型。Runtime / RunHistory / RunTrace / Live
Cost / Usage 全部生产路径就绪。**Phase 6 不是从零开始,是收口。**

Phase 6 真实工作量集中在:
1. **Backend `/api/embedded/*` 升级** — 当前服务 1.0 attribute-based 旧版,需切到 2.0 `<icoder-embedded>` dist
2. **`/api/clients/*` 501 stub → 实装** — Phase 1 cloud-flip 留的占位,Phase 6 Gate 8 必须真做 CRUD + Scope + Rotation + Test Connection
3. **Usage 多维度筛选扩展** — 当前仅 days + apiClient,需扩展到 org/agent/user/provider/success/review/cost/latency
4. **3 个独立 Demo** — Medical Coding / CDI / DRG-DIP 嵌入式场景(当前仅有单 agent smoke)
5. **重复 Web Component 实现整合** — `packages/icoder-embedded/`(canonical)+ `packages/icoder-web/` + `packages/web-components/` + `web-components/`(root)4 套并存,需明确弃用策略
6. **server 端 `account.creditsConsumed` event** — 当前只在 web component 客户端 emit,后端没发布到任何 event stream

**Parity 不需要的工作**:Corti API surface(method-based auth/configureSession/configure/show + embedded-event envelope)iCoDer 已 1:1 对齐。

---

## 2. iCoDer 现有资产审计(8 个领域)

### 2.1 Web Component `<icoder-embedded>` — **PARITY**

| 字段 | 值 |
|---|---|
| Canonical path | `packages/icoder-embedded/src/icoder-assistant.ts` |
| Built dist | `packages/icoder-embedded/dist/icoder-assistant.{js,d.ts}` + `index.{js,d.ts}` |
| Version | 2.0.0 (Phase 5 A4, 2026-07-10) |
| Public API | `auth()` / `configureSession()` / `configure()` / `show()` + iCoDer ADVANTAGE: `setPatientContext()` / `ask()` |
| Events | unified `embedded-event` envelope `{name, payload}` — `ready` / `run.completed` / `account.creditsConsumed` / `error.triggered` / `message.received` |
| Backend endpoint | `POST /api/v1/agents/{agentId}/run` (Phase 4-F2 unified) |
| Test coverage | 7/7 Playwright PASS (`frontend/tests/e2e/phase5_a4_embedded.spec.ts`) |
| Browser walkthrough | PASS — `screenshots/phase5_a4_method_chain_initialized.png` |
| Migration | 1.0 → 2.0 documented (`MIGRATION-2.0.md`),1.0 tag kept as deprecated alias |
| npm publish | **PACKAGE_BUILD_VERIFIED / REGISTRY_PUBLISH_DEFERRED** — `npm pack --dry-run` 8 文件 / 11.7kB 通过;实际 publish 需要用户手动 `npm login` + 创建 `@icoder` npm org |

**Duplicates** (需明确弃用策略):
- `packages/icoder-web/` v1.0.0-beta.1 — `icoder-assistant.ts` + `icoder-stt.ts` (1.0 attribute-based)
- `packages/web-components/` — `icoder-assistant.js` + `icoder-dictation.js` (raw JS)
- `web-components/src/` (root) — `icoder-assistant.ts` + `icoder-speech-to-text.ts`

**Backend serve endpoint**:
- `backend/app/api/embedded.py` — **STALE** — 服务 1.0 attribute-based API,引用 `packages/icoder-embedded/src/icoder-assistant.ts`(源码而非 dist)。preview HTML 用 1.0 attribute API。需 Phase 6 Gate 1 升级。

### 2.2 JavaScript SDK `@icoder/sdk` — **PARTIAL**

| 字段 | 值 |
|---|---|
| Path | `packages/icoder-sdk/src/` |
| Version | 1.0.0-beta.1 |
| Resources | 10 类:`facts` / `agents` + `experts` / `reviews` / `speechToText` / `textGen` / `billing` + `usage` / `oauth` / `runtime` / `marketplace` / `compliance` |
| Build | `tsc` → `dist/index.{js,mjs,d.ts}` |
| Dependencies | axios ^1.7.0 |
| Corti 对齐 | Corti `@corti/embedded-web` 是 Web Component 包(Corti 没有"通用 SDK"概念,只有 Embedded SDK + .NET SDK + Python SDK 三种语言)。iCoDer SDK 是更广的 REST 客户端 |
| Gap | 缺 `runs` / `run_history` / `run_trace` resource;缺 SSE streaming client;缺 A2A v0.3 client(虽然 `runtime` resource 接近) |

### 2.3 API Client management — **PARTIAL**

| 路径 | 状态 |
|---|---|
| `backend/app/api/oauth.py` | **REAL** — Client Credentials + Authorization Code + PKCE,5-min token TTL,realm-based URL(/api/oauth/realms/{realm}/token),scope intersection enforcement |
| `backend/app/api/keys.py` | **REAL** — API Keys CRUD |
| `backend/app/api/platform_api_clients.py` | **501 STUB** — Phase 1 cloud-flip 占位;list/create/scopes/revoke 全返 501 |
| `frontend/src/pages/APIClientsPage.tsx` | **REAL** — OAuth Clients + API Keys 双 tab,CRUD UI 完整,secret 一次性显示 |
| `frontend/src/services/api.ts` | `oauthApi` + `keysApi` 服务真实端点 |

**Gap (Gate 8 需补)**:
- Allowed Origins
- Secret Rotation(当前只能 delete + recreate)
- Disable / Enable 软开关(当前只能 delete)
- Test Connection 按钮
- Last Used 时间戳
- Request Count + Cost per client(当前 Usage 仅按 days,不按 client 维度聚合)
- Agent Scope(细到 agent_id 级别)
- Organization Scope(多租户场景)

### 2.4 Runtime / Agent Run — **PARITY**

| 端点 | 用途 | Phase |
|---|---|---|
| `POST /api/v1/agents/{id}/run` | 统一 Agent Run (corti_like_fast) | Phase 4-F2 |
| `POST /api/v1/coding-compliance/run` | 7-stage 医保编码合规主线 | Phase 5 Track C |
| `POST /api/v1/cdi/*` | CDI Core Entry Agent (6 endpoints) | Phase 5 Track D |
| `POST /api/v1/coding/predict` | G001 refactor — Corti-like Fast Coding | 2026-07-09 |
| `POST /api/icoder/agents/{id}/v1/message:send` | A2A v0.3 wrapper | Phase 4-F2 |
| `GET /api/runtime/runs/{run_id}/trace` | RunTrace 持久化查询 | Phase 3-D2 |

### 2.5 RunHistory — **PARITY**

- alembic `010_run_history.py` 创建 `run_history` 表
- 列: `id` / `organization_id` / `user_id` / `agent_id` / `run_id` (unique+indexed) / `trace_id` / `runtime_mode` / `latency_ms` / `cost_usd` (实际 CNY,列名历史遗留) / `input_text` / `output_summary` / `error` / `error_reason` / timestamps
- Frontend: AgentChatPage 用 run_history hydrate history dropdown

### 2.6 RunTrace — **PARITY**

- alembic `009_run_trace_events.py` 创建 `run_trace_events` 表
- 列: `id` / `run_id` / `organization_id` / `project_id` / `user_id` / `actor_id` / `agent_id` / `step` / `status` / `duration_ms` / `ts` / `safe_metadata_json` (write-time redacted) / timestamps
- Frontend: `RunTracePage.tsx` 渲染
- Inline + persisted 双轨:trace_events 在 agent_run response inline,run_trace_events 表持久化

### 2.7 Live Cost / Cost Ledger — **PARITY**

- per-run cost 字段在 `agent_run` response (`cost.amount` + `cost.currency = "CNY"`)
- Live cost TopBar (Phase 4-G)
- Usage `/summary` 聚合 `run_history.cost_usd`(Phase 5 A3)
- 30-day daily breakdown chart(Phase 5 A6)

### 2.8 Usage Dashboard — **PARTIAL**

- `frontend/src/pages/UsagePage.tsx` — 真实数据,period segmented control (7/30/90 days),3 metric cards,30-day daily chart,activity history list
- 后端 `/api/usage/summary` + `/api/usage/history` — 真实数据 from `audit_log` + `run_history`
- **Gap**: 仅按 days 维度筛选。Gate 8 需扩展为按 Organization / API Client / Embedded App / Agent / User / Runtime Provider / Success/Failure / Review Required / Cost bucket / Token bucket / Latency bucket 多维度

### 2.9 Auth — **PARITY (with iCoDer topology divergence)**

- Single JWT (HS256) for local dev mode
- OAuth2 Client Credentials (5-min TTL) + Authorization Code + PKCE for cloud mode
- Tenant-Name header enforcement middleware
- Frontend `authApi` + `oauthApi`
- **Divergence**: Corti 用 Supabase JWT + Keycloak JWT 双 token,iCoDer 用单 JWT — 设计选择,非 regression

### 2.10 Demos — **PARTIAL**

- `packages/icoder-embedded/examples/index.html` — 单页交互式 smoke(auth/configureSession/configure/show 全链路 + 1.0 兼容性测试)
- `packages/icoder-embedded/examples/phase5_b2_cp{1,4,6,7}_smoke.html` — 4 个 Track B-2 per-agent smoke(Medical Coding / Note Completeness / Evidence Extractor / Principal Diagnosis Review)
- **Gap (Gate 7 需补)**: 独立 CDI Demo + DRG/DIP Demo + 端到端 Review Required 状态机 Demo

---

## 3. Corti 真实走查证据链(复用 + 标 UNKNOWN)

### 3.1 已有 Corti 真实证据(无需重测)

来源:
- `outputs/phase4h/api_samples/corti_embedded_web_component.md` — verbatim Corti Console Code tab HTML sample
- `reports/phase4h/CORTI_THIRD_PARTY_INTEGRATION_AUDIT.md` — §11.1/§11.2/§11.3/§11.4 4 sub-section audit
- `docs/corti_parity/phase5_a4_web_component/corti_reference_sample.html` — Corti Console snapshot
- Phase 4-H §11 audit date: 2026-07-10 (3 days before Phase 6 Gate 0)

**Corti Embedded API surface(verbatim)**:
```html
<corti-embedded id="corti-assistant" baseURL="https://assistant.eu.corti.app"></corti-embedded>
<script type="module">
  import '@corti/embedded-web';
  const assistant = document.getElementById('corti-assistant');
  assistant.addEventListener('ready', async () => {
    await assistant.auth({access_token, refresh_token, token_type:'bearer', mode:'stateless'});
    await assistant.configureSession({defaultLanguage:'en', defaultMode:'in-person', defaultOutputLanguage:'en', defaultTemplateKey:'corti-patient-summary-legacy'});
    await assistant.configure({features:{aiChat,documentFeedback,interactionTitle,navigation,syncDocumentAction,templateEditor,virtualMode}, locale:{dictationLanguage:'en', interfaceLanguage:'auto'}});
    await assistant.show();
  });
  assistant.addEventListener('embedded-event', e => {
    const {name, payload} = e.detail;
    // account.creditsConsumed / error.triggered / ...
  });
</script>
```

**iCoDer 2.0 vs Corti 1:1 对齐验证**(基于 Phase 5 A4 REPORT):
| API | Corti | iCoDer 2.0 | 状态 |
|---|---|---|---|
| `auth({access_token, refresh_token, token_type, mode})` | ✓ | ✓ | PARITY |
| `configureSession({defaultTemplateKey, defaultLanguage, defaultMode, defaultOutputLanguage})` | ✓ | ✓ | PARITY |
| `configureSession({patientId, name, encounterId})` | ✗ | ✓ | **ICODER_ADVANTAGE** |
| `configure({features, locale})` | ✓ | ✓ | PARITY |
| `show()` | ✓ | ✓ | PARITY |
| `setPatientContext()` | ✗ | ✓ | **ICODER_ADVANTAGE** |
| `ask()` | ✗ | ✓ | **ICODER_ADVANTAGE** |
| unified `embedded-event` `{name, payload}` | ✓ | ✓ | PARITY |
| event `ready` | ✓ | ✓ | PARITY |
| event `account.creditsConsumed` `{amount, currency, run_id}` | ✓ | ✓ | PARITY |
| event `error.triggered` `{message}` | ✓ | ✓ | PARITY |
| event `run.completed` (iCoDer-specific) | ✗ | ✓ | **ICODER_ADVANTAGE** |
| event `message.received` (iCoDer-specific) | ✗ | ✓ | **ICODER_ADVANTAGE** |
| 1.0 兼容层 | n/a | ✓ (deprecated alias) | iCoDer-only need |

### 3.2 Corti UNKNOWN(Phase 6 Gate 0 标记,需要 fresh 浏览器走查)

下列项目 Phase 4-H §11 当时无法验证,Phase 6 需要新走查:

| 项目 | 为何 UNKNOWN | Phase 6 验证方法 |
|---|---|---|
| `@corti/embedded-web` npm 实际包内容 | 当时未 `npm install` 真包,只看 Console Code tab sample | Phase 6 用 `npm view @corti/embedded-web` + `npm pack` 真包 |
| Token 过期前端行为 | 5-min refresh cycle 在 Console 内不可见 | Phase 6 真机长跑 30 min,观察 `embedded-event` 是否 emit token 过期事件 |
| Session 切换(多 Agent) | Console 只 demo 单 agent | Phase 6 在测试页里 `configureSession({defaultTemplateKey: A})` → run → `configureSession({defaultTemplateKey: B})` → 验证聊天记录是否隔离 |
| Patient context 切换清缓存 | Corti API 没有 patient context,无法测 | UNKNOWN — Corti 不支持 |
| `account.creditsConsumed` payload 完整字段 | sample 只 console.log 不展开 | Phase 6 真发一条 chat 消息,console.log JSON.stringify(payload) |
| Error 事件载荷完整字段 | sample 只 console.log 不展开 | Phase 6 触发 401(token 错)+ 500(server 错) |
| 多 Agent 切换 locale/theme | Appearance/Locale tab 截图静态 | Phase 6 真切换观察是否实时生效 |
| Background Run / Async Job | Console UI 无入口 | UNKNOWN — Corti Console 不暴露 |
| Server-side Webhook | Console 无 Webhooks 页 | UNKNOWN — Corti Console 不暴露 |

### 3.3 Corti 已确认 NOT 支持(iCoDer 无需追平)

- ❌ iframe 嵌入(用 Web Component + Shadow DOM)
- ❌ React 组件(用 Web Component via ref)
- ❌ 服务端 Webhook
- ❌ Background Run / Async Job
- ❌ Callback URL
- ❌ 服务端 Event Subscription(只有客户端 `embedded-event`)
- ❌ Writeback(Corti 是 pull-only)

---

## 4. Gap matrix (Corti capability × iCoDer current × parity × action × priority)

| # | Corti capability | iCoDer current | Parity | Required action | Priority |
|---|---|---|---|---|---|
| 1 | `<corti-embedded>` Web Component | `<icoder-embedded>` v2.0.0 | **PARITY** | 无 | — |
| 2 | `@corti/embedded-web` npm package | `@icoder/embedded` PACKAGE_BUILD_VERIFIED | **CLOSE** | 用户手动 `npm publish`(无法自动化) | P2 |
| 3 | `auth() / configureSession() / configure() / show()` | 已实现 | **PARITY** | 无 | — |
| 4 | `configureSession({defaultTemplateKey})` | 已实现 | **PARITY** | 无 | — |
| 5 | `configureSession({patientId/name/encounterId})` | 已实现 | **ICODER_ADVANTAGE** | 无 | — |
| 6 | unified `embedded-event` envelope | 已实现 | **PARITY** | 无 | — |
| 7 | `account.creditsConsumed` client-side event | 已实现(client-side) | **PARITY** | Gate 5 加 server-side event | P1 |
| 8 | `error.triggered` event | 已实现 | **PARITY** | 无 | — |
| 9 | OAuth2 Client Credentials | `/api/oauth/*` REAL | **PARITY** | 无 | — |
| 10 | API Client CRUD UI | `APIClientsPage` REAL | **PARITY** | 无 | — |
| 11 | API Client Scopes management | create 时设 scopes | **PARTIAL** | Gate 8 加 scope editing / rotation | P1 |
| 12 | API Client Allowed Origins | ✗ | **MISSING** | Gate 8 新增 | P1 |
| 13 | API Client Rotation | ✗ (只能 delete + recreate) | **MISSING** | Gate 8 新增 | P1 |
| 14 | API Client Disable/Enable 软开关 | ✗ | **MISSING** | Gate 8 新增 | P2 |
| 15 | API Client Test Connection | ✗ | **MISSING** | Gate 8 新增 | P2 |
| 16 | API Client Last Used / Request Count | ✗ | **MISSING** | Gate 8 新增 | P2 |
| 17 | RunHistory | alembic 010 | **PARITY** | 无 | — |
| 18 | RunTrace | alembic 009 + `/api/runtime/runs/{id}/trace` | **PARITY** | 无 | — |
| 19 | Live Cost metering | TopBar + per-run cost | **PARITY** | 无 | — |
| 20 | Usage summary | `/api/usage/summary` REAL | **PARITY** | 无 | — |
| 21 | Usage 多维度筛选 | days + apiClient | **PARTIAL** | Gate 8 扩展 org/agent/user/provider/success/review/cost/token/latency | P1 |
| 22 | `backend/app/api/embedded.py` 服务 2.0 dist | 服务 1.0 src | **STALE** | Gate 1 升级服务 2.0 dist | P0 |
| 23 | JavaScript SDK (REST client) | `@icoder/sdk` v1.0.0-beta.1 | **PARTIAL** | Gate 4 加 runs/run_history/run_trace + SSE client | P1 |
| 24 | 3 个独立 Demo (Medical Coding / CDI / DRG-DIP) | 4 个单 agent smoke | **PARTIAL** | Gate 7 新增 3 个端到端 Demo | P1 |
| 25 | Patient context 安全模型(切换清缓存) | web component 内部状态 | **PARTIAL** | Gate 2 显式 contextId 隔离 + 不持久化 PHI | P1 |
| 26 | Event Contract idempotency / eventId / meta | envelope 是 `{name, payload}`,无 meta | **PARTIAL** | Gate 3 加 `meta: {version, eventId, timestamp, sessionId, contextId}` | P1 |
| 27 | Timeout / Retry / Cancel | fetch 无超时 | **MISSING** | Gate 3 加 AbortController + 重试 | P2 |
| 28 | 重复 Web Component 实现整合 | 4 套并存 | **PARTIAL** | Gate 1 弃用 3 套,canonical 留 `packages/icoder-embedded/` | P0 |
| 29 | Server-side Webhook | Corti 也不支持 | **N/A** | 不做 | — |
| 30 | Writeback | Corti 是 pull-only,且 iCoDer 红线"不自动写回" | **N/A** | 不做 | — |

**Parity 统计** (30 项):
- PARITY: 13 (43%)
- ICODER_ADVANTAGE: 2 (7%)
- CLOSE: 1 (3%)
- PARTIAL: 8 (27%)
- MISSING: 5 (17%)
- STALE: 1 (3%)
- N/A: 2 (7%) — Corti 也不支持

---

## 5. Phase 6 真实工作量评估(按 Gate 分)

### Gate 1 — 统一 Embedded Contract — **小**
- 修 `backend/app/api/embedded.py` 服务 2.0 dist(~30 min)
- 在 4 套重复 web component 实现里加 README "DEPRECATED use packages/icoder-embedded/"(~30 min)
- 不需要重写 web component(Phase 5 A4 已完成)
- **预估**: ~1h

### Gate 2 — Patient/Encounter Context 安全 — **中**
- 在 `<icoder-embedded>` 加 contextId UUID v4 生成逻辑
- 切换 patient 时清内部 _patientContext + _messages
- 显式不持久化到 localStorage
- 加单元测试覆盖 context isolation
- **预估**: ~2-3h

### Gate 3 — 统一 Embedded Event Contract — **中**
- 扩 envelope `EmbeddedEvent` 加 `meta: {version:'1.0', eventId, timestamp, sessionId, contextId}`
- 加事件类型 `run.started` / `run.stage_completed` / `run.review_required` / `run.failed` / `tool.invoked` / `tool.result` / `usage.updated` / `session.expired`
- 加 AbortController + 30s/60s/120s 可配超时 + 1 次自动重试
- 加幂等性(eventId dedup)
- **预估**: ~3-4h

### Gate 4 — SDK + API Client 产品化 — **中**
- `packages/icoder-sdk/` 加 `runs` / `runHistory` / `runTrace` resource
- 加 SSE client helper
- 加 A2A v0.3 client(可能复用 `runtime` resource)
- 不重写 SDK 主体
- **预估**: ~3-4h

### Gate 5 — RunHistory/Trace/Cost 集成 — **小**
- 已有 RunHistory/RunTrace/Live Cost 全部生产路径
- 只需在 `<icoder-embedded>` UI 加 "View Run Trace" 链接 + server emit `account.creditsConsumed` 到 trace event stream
- **预估**: ~1-2h

### Gate 7 — 3 个 Embedded Demo — **大**
- Medical Coding Embedded Demo(已有 cp1 smoke,扩展为完整 demo + Review Required 状态机 + RunTrace 链接)
- CDI Embedded Demo(新)
- DRG/DIP Embedded Demo(新)
- 每个 demo 独立 HTML + 合成病例 + Playwright trace + 截图
- **预估**: ~6-8h(每个 demo 2-3h)

### Gate 8 — API Client + Usage 产品化 — **大**
- 实装 `platform_api_clients.py` 501 stub:全 CRUD + Scopes + Allowed Origins + Rotation + Disable/Enable + Test Connection + Last Used + Request Count
- 新 alembic migration(扩展 oauth_clients 表)
- 扩展 `/api/usage/summary` + `/api/usage/history` 加多维度筛选
- 前端 APIClientsPage + UsagePage 加新字段 UI
- **预估**: ~6-8h

### Final report — **小**
- 汇总 9 个 Gate 完成情况 + Corti parity 结果 + 剩余 blocker + 最终裁决
- **预估**: ~1h

**Phase 6 总预估**: ~24-30h,~700K-900K tokens(对比 Phase 5 Track H 累计 ~28.5h / 1.83M tokens)

---

## 6. 不允许的输出(§3)

Phase 6 任何 Gate 都不得输出:
- `PRODUCTION_READY`
- `HOSPITAL_DEPLOYMENT_READY`
- `PUBLIC_NPM_PUBLISHED`(除非真发 npm)
- `CORTI_FULL_PARITY`(因为仍有 8 PARTIAL + 5 MISSING)

允许的最终裁决:
- `PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION`(全部 P0+P1 关闭后)
- `PARTIAL_BLOCKED_BY_<明确原因>`

---

## 7. Phase 6 红线(§19 简化的 6 条)

1. ❌ 用一个 Demo 冒充三个场景
2. ❌ 用 Mock Runtime 通过真实 Demo 验收
3. ❌ 静态代码示例代替真实运行
4. ❌ 声称 npm 已发布但实际未发布
5. ❌ 机械复制 Corti 而删除 iCoDer 中国本地化(ICD-10-CN / DRG-DIP / CNY / 中文)
6. ❌ 为通过验收硬编码病例输出

---

## 8. Carry-forward

### P0(必须关闭才能 PASS_READY_FOR_PARTNER_INTEGRATION_VALIDATION)
1. `backend/app/api/embedded.py` 升级到 2.0 dist
2. 重复 web component 实现明确弃用策略
3. 完整 Gate 1-8 实施

### P1(应关闭,不阻塞最终 PASS 但影响 parity 完整度)
4. API Client Rotation + Allowed Origins
5. Usage 多维度筛选
6. 3 个独立 Embedded Demo
7. server-side `account.creditsConsumed` event
8. SDK 加 runs/runHistory/runTrace resource
9. Patient Context 安全模型显式化
10. Event envelope meta 字段 + idempotency

### P2(可推迟到 Phase 7)
11. Test Connection / Last Used / Request Count
12. Timeout / Retry / Cancel(可在 SDK 层补)
13. npm 实际 publish(需用户手动 npm login)

### Corti fresh browser walkthrough(可在 Gate 7 期间穿插)
14. `npm view @corti/embedded-web` 真包内容
15. 30-min 长跑观察 token 过期前端行为
16. 多 Agent 切换 + locale/theme 实时切换
17. `account.creditsConsumed` + `error.triggered` 完整 payload 真发一条消息抓取

---

## 9. Verdict

`GATE0_BASELINE_AUDIT_COMPLETE`.

Phase 6 不是从零开始,是**收口与产品化**。Phase 5 A4/A5 已交付 Corti-compatible
Web Component 2.0,Phase 4-F2/G + Phase 5 Track A 已交付 Runtime/RunHistory/
RunTrace/Live Cost/Usage 生产路径。Phase 6 真实工作量集中在
backend `embedded.py` 升级、`platform_api_clients.py` 实装、Usage 多维度
筛选、3 个独立 Demo、SDK 资源扩展、重复实现整合。

预估 24-30h / 700K-900K tokens 完成 9 个 Gate(本会话已用 ~30K tokens
完成 Gate 0 审计)。

**推荐执行顺序**(基于 ROI):
1. Gate 1 (P0, ~1h) — 立即解锁 backend embedded endpoint
2. Gate 5 (P0, ~1-2h) — RunHistory/Trace 集成快收口
3. Gate 2 (P1, ~2-3h) — Context 安全模型
4. Gate 3 (P1, ~3-4h) — Event Contract meta + idempotency
5. Gate 4 (P1, ~3-4h) — SDK 扩展
6. Gate 7 (P1, ~6-8h) — 3 个 Demo
7. Gate 8 (P1, ~6-8h) — API Client + Usage 产品化
8. Final report (~1h)
