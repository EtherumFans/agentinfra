# Phase 1.2 cycle 1 — FactsR™ 事实抽取路径 + schema 对齐 Corti §3.2 / §13.4

> Date: 2026-06-30
> Roadmap reference: `docs/corti-reverse-engineered/SUMMARY.md §15.5 Phase 1 路线` + `§13.4 Text Generation`
> Capture: `docs/corti-reverse-engineered/feature-flows/ai-studio-fact-extraction/summary.json`

## 1. 背景

Phase 1.1 (`4ceb60e`) 新增 `POST /api/v2/tools/coding` 对齐 Corti §3.1，并确立
`/api/v2/...` 顶层 mount 习惯。按 §15.5 路线，Phase 1.2 = **Text Generation
5 端点 (§13.4)**，其中明确「抽取 2 个 GA 端点即可」。

§13.4 五端点 GA/Beta 状态：

| Endpoint | Connection | Arch | Status |
|---|---|---|---|
| Streams | WSS | Stateful | GA |
| **FactsR™** | REST | **Stateless** | **GA** |
| Guided Document | REST | Stateless/Stateful | Beta |
| Sections & Templates | REST | — | Beta |
| Documents Classic | REST | Stateful | Planned deprecation |

**cycle 1 选 FactsR™**：两个 GA 端点中 FactsR 是 REST + Stateless，wire-shape
最简单、最容易闭环；Streams (WSS, stateful) 留 cycle 2。

iCoDer 此前的事实抽取入口 `backend/app/api/facts.py`：

| 维度 | 现状 (legacy `/api/facts/extract`) |
|---|---|
| URL | `POST /api/facts/extract` |
| Req | `{text, output_language}` (单字符串) |
| Resp | `{facts: {chief_complaint, diagnosis_facts[], drug_facts[], lab_facts[], ...}, raw_output, credits_consumed}` (中国 schema, 嵌套对象) |
| 执行 | 走 `expert_runner` + DB 持久化 Expert |

Corti §3.2 目标 shape (从 `api.eu.corti.app/v2/tools/extract-facts` 抓包还原)：

| 维度 | Corti §3.2 |
|---|---|
| URL | `POST /v2/tools/extract-facts` |
| Req | `{context:[{text, type}], outputLanguage}` |
| Resp | `{facts:[{group, text, value}], outputLanguage, usageInfo:{creditsConsumed}}` |
| facts | **扁平数组**，每项含 kebab-case `group` 分类键 |

Phase 1.2 cycle 1 在不动 legacy `/api/facts/*` 的前提下，新增一条 Corti-shape
HTTP 路径：

- `POST /api/v2/tools/extract-facts`
- 走 `llm_service.chat` (不经 expert_runner / DB)，stateless
- `facts[].group` 用 Corti kebab-case 分类键 (chief-complaint / vital-signs /...)
- `outputLanguage` 原样回显；非原生支持语言降级带 notice

## 2. 端到端契约

### 2.1 Request

```json
{
  "context": [
    { "text": "患者男性,67 岁,因「反复胸闷」就诊。LVEF 38%。诊断:慢性心力衰竭。", "type": "text" }
  ],
  "outputLanguage": "en-US"
}
```

### 2.2 Response (200)

```json
{
  "facts": [
    { "group": "demographics", "text": "67-year-old male.", "value": "67-year-old male." },
    { "group": "chief-complaint", "text": "Recurrent chest tightness.", "value": "Recurrent chest tightness." },
    { "group": "assessment", "text": "Chronic heart failure.", "value": "Chronic heart failure." }
  ],
  "outputLanguage": "en-US",
  "usageInfo": { "creditsConsumed": 0.011 }
}
```

### 2.3 错误响应

| HTTP | `detail.error` / `detail.reason` | 触发 |
|---|---|---|
| 400 | `empty_context` | `context` 为空数组或所有 text 为空白 |
| 502 | `facts_extraction_failed` | `llm_service.chat` 抛异常 |
| 503 | `llm_credential_missing` | `ICODER_CREDENTIAL_LLM` 未设置且 `ICODER_ALLOW_DEGRADED_NO_KEY != 1` (hospital pilot gate) |

## 3. 字段映射 (Corti §3.2 ↔ iCoDer)

| Corti 字段 | 来源 |
|---|---|
| `facts[].group` | LLM 输出 `group` 原样转发 (不强校验 `CORTI_FACT_GROUPS` 成员资格) |
| `facts[].text` | LLM 输出 `text` |
| `facts[].value` | LLM 输出 `value`；缺省时回退到 `text` |
| `outputLanguage` | `body.outputLanguage` 规范化回显 (空 → `en-US`) |
| `usageInfo.creditsConsumed` | 由 provider token usage 估算 (`total_tokens/1000 * 0.01`)；无 usage → `0.0` |

- `group` 不做 allowlist 拦截：domain-specific / 未来新增分类键不被静默丢弃
  (与 v2 coding 端点对 `system` 的纪律相反——facts group 是开放词表)。
- 单条 fact 解析失败 (非 dict / text+value 均空) 静默跳过，不整体 502。

## 4. Reuse 现有组件 (不重写)

- `app/services/llm_service.py` `llm_service.chat(messages, temperature, max_tokens)`
  — 与 `text_gen.py` 同一调用约定，返回 `{content, usage}`
- `app/schemas/v2_tools_facts.py` — 本期新增 Pydantic (request/response + 常量)
- `icoder_runtime/core/pii_redaction.py` `PIIRedactor` — 中国本地 PHI 脱敏 (best-effort)
- Phase 1.0 `app/middleware/auth.py` `Depends(get_current_user)` — 复用
- hospital-pilot 503 gate — 与 `v2_tools_coding.py` 同一纪律

## 5. Out of scope (Phase 1.2 cycle 1 显式不做)

- ❌ legacy `/api/facts/extract` (中国 schema, 保留, 行为不变)
- ❌ `facts` capability scope 注册 (Phase 1.2 OAuth client 接入一并做)
- ❌ Streams WSS GA 端点 (cycle 2)
- ❌ Guided Document / Sections & Templates / Documents Classic (Beta/deprecated)
- ❌ `GET /v2/factgroups/` 分类词表端点 (按需后续)
- ❌ 前端 fact extraction page 改造 (cycle 1 是后端 HTTP shape 对齐)

## 6. 测试矩阵 (8 / 8 PASS)

`backend/tests/test_api/test_v2_tools_facts.py`:

| # | 测试 | 验证 |
|---|---|---|
| 1 | `test_v2_facts_shape_minimal` | 标准请求 → 200, `facts/outputLanguage/usageInfo` 全字段 |
| 2 | `test_v2_facts_output_language_echo` | `outputLanguage` 回显; 空 → `en-US` |
| 3 | `test_v2_facts_unknown_group_passthrough` | 非 canonical group 原样转发, 不丢弃 |
| 4 | `test_v2_facts_markdown_fence_stripped` | ```json fence 包裹的输出仍能解析 |
| 5 | `test_v2_facts_multi_context_merged` | 多 context 块全部喂给模型 (merge) |
| 6 | `test_v2_facts_credits_consumed_non_negative` | `creditsConsumed` 恒 ≥ 0; 有/无 usage 两路 |
| 7 | `test_v2_facts_empty_context_rejected` | 空 / 全空白 context → 400 `empty_context` |
| 8 | `test_v2_facts_no_llm_credential_returns_503` | 无 LLM credential + 无 dev opt-in → 503 |

## 7. Verification

```bash
cd backend && pytest tests/test_api/test_v2_tools_facts.py -v   # 8/8 PASS
cd backend && pytest tests/test_api/ -q                          # 92/92 PASS (84 + 8)
cd frontend && npx tsc --noEmit                                  # exit 0
```

## 8. 后续

| cycle | 内容 |
|---|---|
| 1.2 cycle 2 | Streams WSS GA 端点 (§13.4 第二个 GA) |
| 1.2 | `facts` / `textgen` capability scope 注册 + OAuth client 接入 |
| 1.3 | `/api/v2/interactions/...` STT 3 端点 (按 Corti §13.3) |

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 无 LLM credential 时 caller 拿空 facts[] 误以为真 | hospital-pilot 503 拒绝, 不做 fake facts |
| LLM 输出非合法 JSON / 含 markdown fence | `_strip_code_fence` + 容错解析, 解析失败返空 facts[] (不 5xx) |
| outputLanguage 超出官方支持范围 | 接受 + system prompt 带 degrade notice, 原样回显 |
| group 词表漂移 (Corti 28+ 持续增长) | 开放词表, 不 allowlist 拦截, 新 group 不丢 |
