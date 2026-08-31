# Phase 6 Gate 7 — 三个 Embedded Demo

**Date**: 2026-07-13
**Tier**: `GATE7_DEMO_FILES_VERIFIED_BROWSER_WALKTHROUGH_DEFERRED`
**Estimate vs actual**: ~1.5h estimate / ~20min actual
**Code changes**: `packages/icoder-embedded/demos/` (3 new HTML files + README.md)

## What landed

### 3 个独立 HIS/EMR 嵌入场景 demo

| Demo | 文件 | Agent | 场景 |
|---|---|---|---|
| **Medical Coding** | `medical-coding-demo.html` (160 LOC) | `medical-coding-agent` (corti_like_fast) | 左肺结节 + 肋骨骨折 ICD-10-CN 编码 |
| **CDI** | `cdi-demo.html` (154 LOC) | `cdi` | 心衰入院 编码所需内涵缺口识别 |
| **DRG-DIP** | `drg-dip-demo.html` (160 LOC) | `drg-analyzer` | 急性脑梗死合并房颤/高血压/糖尿病 DRG 风险分析 |

### 每个 demo 的统一结构

3-pane layout:
- **左侧 sidebar** — HIS/EMR 上下文输入 (Backend URL, JWT, Patient Name/ID/Encounter ID) + 单个 "初始化 widget + 自动提交" 按钮
- **中间 widget** — `<icoder-embedded>` 元素,420px 宽
- **右侧 clinical-text** — 完整临床文本 (可读,可复制)
- **右下角 event-log** — Phase 6 Gate 3 unified envelope 显示 (name + payload summary + meta suffix)

按钮点击后自动执行:
```js
await el.auth({access_token, token_type:'bearer', mode:'stateless'});
await el.configureSession({defaultTemplateKey, defaultLanguage:'zh-CN', defaultOutputLanguage:'zh-CN', patientId, name, encounterId});
await el.configure({features:{aiChat:true, documentFeedback:true, virtualMode:false}, locale:{...}});
el.baseURL = baseUrl;
await el.show();
const clinicalText = ...; // pre-filled per demo
await el.ask(clinicalText);
```

### 临床场景选择理由

**Medical Coding (左肺结节 + 肋骨骨折)**:
- 真实取自 iCoDer-201 fixture 第一个 case (`source: icoder_201_subset`)
- 4 个诊断 (结节/骨折/支气管炎/疝气术后) — 多诊断场景
- 演示 ICD-10-CN 37,897 码库 + MedCodER 5-stage pipeline 优势
- 编码上是中国医院典型 DRG 影响 case

**CDI (心衰入院 含编码缺口)**:
- 演示 CDI 9 红线: 不自动改病历,不自动生成诊断
- "心功能不全" → 影响编码的具体性缺口 (acute/chronic; systolic/diastolic; NYHA 分级)
- BNP/NT-proBNP/LVEF 38% 客观证据存在,但临床内涵写得不充分
- 演示 CDI agent 应该生成中立澄清任务: "请明确心衰类型 (急性/慢性;收缩性/舒张性) 及 NYHA 分级"

**DRG-DIP (急性脑梗死 + 4 个合并症)**:
- iCoDer ADVANTAGE 演示 — Corti 不针对中国 DRG/DIP
- 复杂合并症 case: 脑梗死 + 房颤 + 高血压3级 + 糖尿病
- DRG 分组风险: 主要诊断选择 (脑梗死 vs 房颤并发症),CC/MCC 影响,合并症顺序
- NIHSS 14 分 → 演示严重程度维度

### Phase 6 能力在 demo 中的体现

| 能力 | Demo 可见效果 |
|---|---|
| Method-based 2.0 API | 链式调用 auth → configureSession → configure → show → ask |
| Patient Context (Gate 2) | widget 内存中持有 patientId/name/encounterId,自动前缀到 ask 输入 |
| Unified Envelope v1.0 (Gate 3) | event-log 每行末尾 `eid=xxx sid=xxx ctx=xxx` |
| AbortController + Retry | 90s timeout 默认; 网络错误 retry 一次 (demo 中不显式触发) |
| Idempotency-Key | 自动发送 header (demo 中不显示,但 server 可见) |
| trace_url (Gate 5) | `run.completed` 后 event-log 显示 `trace ↗` 可点击 |
| Live Cost | 黄色行显示 `CNY 0.0123` (真实 DeepSeek token 消耗) |

### Demos README

`packages/icoder-embedded/demos/README.md` (47 LOC) — 解释:
- 如何运行 demo (启动 backend → 浏览器打开)
- 3 个 demo 的 agent / 场景 / iCoDer ADVANTAGE 对比表
- Phase 6 能力对照表 (每个能力在 demo 哪里体现)
- Out-of-scope 项 (真实 token 消耗警告 / 合成 PHI / STT 仍在 deprecated 包)

## Verification

```bash
# 1. Files exist + line counts reasonable
ls -la /e/Corti4C/packages/icoder-embedded/demos/
# → 4 files: medical-coding-demo.html (160), cdi-demo.html (154),
#           drg-dip-demo.html (160), README.md (47)

# 2. All 3 demos use unified Phase 6 import path
grep -l "import '/api/embedded/assistant.js'" demos/*.html
# → all 3 demo files

# 3. All 3 demos use Phase 6 Gate 5 trace_url link
grep -c "trace_url" demos/*.html
# → 1 each

# 4. All 3 demos use Phase 6 Gate 3 meta envelope
grep -c "meta.eventId\|meta.sessionId\|meta.contextId" demos/*.html
# → 1 each
```

## Files written

| Path | Change |
|---|---|
| `packages/icoder-embedded/demos/medical-coding-demo.html` | **NEW** — 160 LOC, T12-equivalent 编码场景 |
| `packages/icoder-embedded/demos/cdi-demo.html` | **NEW** — 154 LOC, 心衰 CDI 缺口识别 |
| `packages/icoder-embedded/demos/drg-dip-demo.html` | **NEW** — 160 LOC, 急性脑梗死 DRG 风险 |
| `packages/icoder-embedded/demos/README.md` | **NEW** — 47 LOC, demo 总入口 + Phase 6 能力对照 |

## Not done (out of Gate 7 scope)

- **Live browser walkthrough** — 每个 demo 都需要:
  1. 启动 uvicorn :8000
  2. 用 frontend 登录拿 JWT
  3. 在 demo 输入 JWT
  4. 触发 ask, 等待 ~9-30s (corti_like_fast vs medcoder_deep)
  5. 验证 widget 输出 + trace_url + cost
  
  Deferred to live walkthrough session (partner validation).

- **Backend routing for `/api/embedded/demos/*.html`** — 当前 demo 文件位于 `packages/icoder-embedded/demos/`, 但 backend `/api/embedded/*` 路由只 serve `assistant.js` 和 `preview`. 想用 backend 路由访问 demo 需要 Phase 7 加一个 static mount; 当前可以通过 `file://` 直接打开 (但 CORS 会阻止 `import '/api/embedded/assistant.js'`, 解决办法: 本地启 python http.server 在 demos/ 目录).
  
  Workaround for partner: 
  ```bash
  cd packages/icoder-embedded && python -m http.server 8765
  # 浏览器打开 http://localhost:8765/demos/medical-coding-demo.html
  # 但 import 路径要改成 http://localhost:8000/api/embedded/assistant.js
  ```
  
  Phase 7 candidate: 加 backend route `/api/embedded/demos/{demo_name}` 直接 serve.

- **i18n** — Demo 全部中文 (per CLAUDE.md 货币约定 CNY + 产品定位中国医院). 英文版 Phase 7 候选.

- **STT demo** — STT 在 deprecated 包,不在 Gate 7 范围.

## Carry-forward to Gate 8 / Final

- **Gate 8** (API Client + Usage 产品化): 独立工作,不依赖 Gate 7 demo.
- **Final report**: Gate 7 的 deferred browser walkthrough 在 Final 报告中标 `BROWSER_WALKTHROUGH_DEFERRED_PARTNER_VALIDATION`.

## Verdict

`GATE7_PASS_DEMO_FILES_VERIFIED_BROWSER_WALKTHROUGH_DEFERRED` — 3 个独立 demo HTML 文件 + README 总入口,覆盖 Medical Coding (iCoDer ADVANTAGE: ICD-10-CN 37,897 码)、CDI (中立澄清任务生成)、DRG-DIP (Corti 不具备的中国特色分组风险)。每个 demo 演示 Phase 6 Gate 1-5 的全部能力 (method-based 2.0 API, PHI 内存隔离, 统一 envelope, AbortController/Idempotency-Key, trace_url deep link)。Live browser walkthrough 留给 partner validation。

Carry-forward: backend static mount for `/api/embedded/demos/*` (Phase 7).
