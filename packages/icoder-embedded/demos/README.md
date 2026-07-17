# iCoDer Embedded — 3 个嵌入演示 (Phase 6 Gate 7)

每个 demo 是一个独立的 HTML 文件,通过 `/api/embedded/assistant.js` 加载
`<icoder-embedded>` web component,展示 HIS/EMR 嵌入场景下的端到端流程:
auth → configureSession → configure → show → ask → 显示结果 + trace_url.

## 如何运行

```bash
# 1. 启动 backend (terminal 1)
cd backend && python -m uvicorn app.main:app --port 8000

# 2. 在另一个 terminal 浏览 demo
# 浏览器打开任意 demo URL (需要先用 frontend 登录拿到 JWT)
```

## 3 个 Demo

| Demo | URL | Agent | 场景 | iCoDer ADVANTAGE |
|---|---|---|---|---|
| **Medical Coding** | `/api/embedded/demos/medical-coding-demo.html` (需 backend routing) 或 file:// 直开 | `medical-coding-agent` (corti_like_fast) | 左肺结节 + 肋骨骨折 ICD-10-CN 编码 | 中国 ICD-10-CN 37,897 码 + MedCodER 5-stage pipeline |
| **CDI** | `/api/embedded/demos/cdi-demo.html` | `cdi` | 心衰入院 编码所需内涵缺口识别 | 中立澄清任务生成 (9 红线: 不自动改病历) |
| **DRG-DIP** | `/api/embedded/demos/drg-dip-demo.html` | `drg-analyzer` | 急性脑梗死合并房颤/高血压/糖尿病 DRG 风险分析 | DRG/DIP 分组风险结构 (Corti 不针对中国 DRG) |

## Demo 演示的 Phase 6 能力

| 能力 | 阶段 | 在 demo 中的体现 |
|---|---|---|
| Method-based 2.0 API | Phase 5 A4 + Phase 6 Gate 1 | `auth() → configureSession() → configure() → show()` 链式调用 |
| Patient Context (PHI) | Phase 6 Gate 2 | `configureSession({patientId, name, encounterId})` 设置上下文, widget 内存中 |
| Unified Event Envelope v1.0 | Phase 6 Gate 3 | Event log 每行末尾显示 `eid=xxx sid=xxx ctx=xxx` meta |
| AbortController + Retry + Idempotency-Key | Phase 6 Gate 3 | 90s timeout 默认,网络错误自动 retry 一次,`Idempotency-Key` header |
| `trace_url` Deep Link | Phase 6 Gate 5 | `run.completed` 事件后显示 `trace ↗` 可点击跳转 |
| Live Cost (`account.creditsConsumed`) | Phase 4-G + Phase 5 A | Event log 黄色行显示 `CNY 0.0123` |
| SDK API surface (验证用) | Phase 6 Gate 4 | Demo 直接调 widget; SDK 暴露 `icoder.runs.runText()` 给 TypeScript 集成方 |

## 不演示的 (out of Gate 7 scope)

- **真实 DeepSeek token 消耗** — Demo 用真实 backend,会真实消耗 token (~¥0.01-0.05/run). 用 partner test token 时注意。
- **真实患者 PHI** — 3 个临床文本都是合成数据,非真实患者。
- **`trace_url` viewer auth** — 当前 trace viewer 需 iCoDer 登录 session. 跨域 iframe 嵌入需要短生命周期 JWT-in-query-string (Phase 7 候选)。
- **STT (语音转文字)** — STT 仍在 deprecated `packages/icoder-web/` (见该包 DEPRECATED.md). Phase 7 候选迁入 `packages/icoder-embedded/` 为独立 `<icoder-stt>` 元素。
