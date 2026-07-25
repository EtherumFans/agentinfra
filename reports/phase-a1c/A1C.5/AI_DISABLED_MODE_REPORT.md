# A1C.5 — AI Disabled Mode Report

**Phase**: A1C.5
**Date**: 2026-07-25
**Scope**: PDF §九 "AI 默认关闭" + 6 项 AI 不可用时行为验证。

---

## §1 默认关闭 (Charter §4 + §九 强制)

### 1.1 配置

```python
# backend/app/config.py
ICODER_AI_ENABLED: bool = False  # 默认关闭
ICODER_AI_DISABLED_MESSAGE: str = "AI 服务暂未启用,请联系管理员"
```

`Settings._validate_fail_closed_policy` 在 cloud 模式下:
- ICODER_AI_ENABLED=true 时,**必须**配置 LLM_API_KEY / CredentialVault `llm` service
- ICODER_AI_ENABLED=false 时,LLM 路径直接拒绝 (503)

### 1.2 LLMGateway guard

```python
# icoder_runtime/core/llm_gateway.py (existing pattern)
async def infer_async(...):
    if not settings.ICODER_AI_ENABLED:
        raise AIServiceDisabled(
            code="AI_DISABLED",
            message=settings.ICODER_AI_DISABLED_MESSAGE,
            http_status=503,
        )
    # 正常路径
    ...
```

---

## §2 PDF §九 6 项 AI 不可用时行为

### §2.1 明确提示 (✓ PASS)

| 路径 | 提示方式 | 实现 |
|------|---------|------|
| Agent run endpoint | 503 + `{"error": {"code": "AI_DISABLED", "message": "AI 服务暂未启用,..."}}` | LLMGateway.infer_async guard |
| Frontend MedicalCodingPage | Toast 红色警告 + "AI 服务暂未启用" 文案 + retry 按钮 | frontend/src/pages/MedicalCodingPage.tsx |
| Frontend CDI Page | 同上 | frontend/src/pages/CDIPage.tsx |
| Frontend AgentChatPage | Chat input disabled + banner | frontend/src/pages/AgentChatPage.tsx |
| SDK (TypeScript) | Throws `iCoDerAIDisabledError` | packages/icoder-sdk/src/resources/agents.ts |
| SDK (Python) | Raises `AIServiceDisabled` | packages/icoder-sdk-python (A1B-AE.3) |

### §2.2 不丢失数据 (✓ PASS)

| 资源 | 持久化路径 | AI 失败时行为 |
|------|----------|--------------|
| PatientContext | patient_contexts 表 (A1C.3) | 不受影响 |
| Document | documents 表 (existing) | 不受影响 |
| Encounter | encounters 表 (existing) | 不受影响 |
| Run history | run_history 表 (Phase 7 Gate 4) | 标记 status=failed,error_code=AI_DISABLED |
| Coding review | coding_reviews 表 | 不受影响 |
| CDI case | cdi_cases 表 (Phase 5 Track D) | 不受影响 |

**验证**: AI 失败时,**所有上游**写入路径仍成功。Agent run 是 stateless — 失败不污染 patient_context/document/encounter 数据。

### §2.3 不阻断确定性工作流 (✓ PASS)

iCoDer 非-AI 兜底路径:

| 工作流 | AI 路径 | 非-AI 兜底 |
|-------|---------|-----------|
| 编码候选生成 | HybridCodingAdapter (DeepSeek) | **Code dictionary lookup** (37,897 ICD-10-CN) + BGE-M3 retrieval (FAISS) — Phase 2-F |
| CDI 缺口检测 | note_completeness agent | **ComplianceRuleEngine** + rule-based gap detection (Phase 5 Track C) |
| Compliance 校验 | LLM-assisted rule explanation | **RuleEngine.evaluate()** 纯规则路径 (Phase A1A Gate 4) |
| 文书搜索 | LLM-assisted semantic search | **Code dictionary full-text search** (fallback) |
| DRG/DIP 分组 | LLM-assisted grouping | **CN-DRG/DIP grouping rules** (deterministic Phase 5 A1) |

**验证**: ICODER_AI_ENABLED=false 时,上述 5 个工作流仍返回**确定性**结果 (rule-based / dictionary-based)。

### §2.4 不自动切换到未授权模型 (✓ PASS)

```python
# backend/app/config.py (existing)
LLM_PROVIDER: str = "deepseek"  # 单 provider
LLM_FALLBACK_PROVIDER: str = ""  # 空 = 无 fallback (default)

# 仅在显式配置 LLM_FALLBACK_PROVIDER 时启用 fallback
if settings.LLM_FALLBACK_PROVIDER:
    # 走 fallback 路径
    ...
else:
    # 单 provider — 失败就失败
    raise UpstreamError(...)
```

**关键**: 没有任何代码路径会**自动**从 DeepSeek 切换到 OpenAI / Anthropic / Azure。Fallback 必须显式 enable (Pilot 启动前 review)。

### §2.5 不暴露患者信息 (✓ PASS)

AI 失败响应**仅**包含:
```json
{
  "error": {
    "code": "AI_DISABLED" | "UPSTREAM_TIMEOUT" | "UPSTREAM_ERROR" | ...,
    "message": "通用错误描述 (无 PHI)",
    "trace_id": "00-abc...-def...-01",
    "upstream_provider": "deepseek"
  }
}
```

**绝不**包含:
- patient_id / patient_name
- 病历原文 / document content
- encounter metadata
- physician ID

### §2.6 不伪造 AI 结果 (✓ PASS)

Agent run 失败时:
- run_history.status = `failed` (不写为 `completed`)
- run_history.error_code = `AI_DISABLED` / `UPSTREAM_*`
- run_history.result_payload = NULL (不写假 JSON)
- audit_log.action = `agent_run.failed`
- SSE 事件: `run.failed` (不发 `run.completed`)

**验证**: 任何前端 UI / SDK 调用看到 failed status 都会向用户提示,**不会**展示假诊断 / 假编码建议 / 假 CDI 缺口。

---

## §3 验证矩阵 (16 个 AI 失败 + 1 个 AI 启用 = 17 场景)

| # | 场景 | 行为 | 验证 |
|---|------|------|------|
| 1 | ICODER_AI_ENABLED=false + Agent run | 503 AI_DISABLED | LLMGateway guard |
| 2 | ICODER_AI_ENABLED=false + Medical Coding | 503 + 前端 banner | UI + LLMGateway |
| 3 | ICODER_AI_ENABLED=false + CDI | 503 + 前端 banner | UI + LLMGateway |
| 4 | ICODER_AI_ENABLED=false + 编码字典 search | 200 (deterministic) | ✓ 不阻断 |
| 5 | ICODER_AI_ENABLED=false + DRG/DIP 分组 | 200 (deterministic) | ✓ 不阻断 |
| 6 | ICODER_AI_ENABLED=false + 文书搜索 | 200 (deterministic) | ✓ 不阻断 |
| 7 | ICODER_AI_ENABLED=true + LLM_API_KEY 缺失 | Settings 拒绝启动 (fail-closed) | A1A Gate 1 |
| 8 | ICODER_AI_ENABLED=true + DeepSeek 503 | retry 3 次 → 502 + run_history.failed | LLMGateway retry |
| 9 | ICODER_AI_ENABLED=true + DeepSeek 超时 | 504 + run_history.failed | LLMGateway timeout |
| 10 | Agent run failed | audit_log.action=agent_run.failed | ✓ (Phase 7 Gate 4) |
| 11 | Agent run failed | SSE emit run.failed (not run.completed) | ✓ (Phase 7 Gate 9) |
| 12 | Agent run failed | 不写 run_history.result_payload | ✓ (run_lifecycle.py) |
| 13 | Agent run failed | 前端 toast 显示真实失败原因 | ✓ (MedicalCodingPage.tsx) |
| 14 | Agent run failed | 不暴露 patient_id / document content | ✓ (response schema) |
| 15 | Agent run failed | 持久化 patient_context 仍可读 | ✓ (patient_context.get 不依赖 Agent) |
| 16 | Agent run failed | documents 仍可读 | ✓ (documents 表独立) |
| 17 | ICODER_AI_ENABLED=true + 成功路径 | 200 + run_history.completed | ✓ (golden path) |

---

## §4 Verdict

**AI_DISABLED_MODE_VERIFIED_6_OF_6_PDF_BEHAVIORS**:

| PDF §九 行为 | 状态 |
|-------------|------|
| 明确提示 | ✓ |
| 不丢失数据 | ✓ |
| 不阻断确定性工作流 | ✓ |
| 不自动切换到未授权模型 | ✓ |
| 不暴露患者信息 | ✓ |
| 不伪造 AI 结果 | ✓ |

**Charter §22 forbidden verdicts honoured**: 未输出 AI_DISABLED_FULLY_VERIFIED (后者 = Pilot env 真实 DeepSeek 故意失败注入测试,deferred to Pilot)。本报告验证的是 **设计层 + 代码层** 的 fail-closed 路径,Pilot env 必须补**运行层** 故障注入测试。

## §5 Pilot 必跑项 (3 个)

1. ICODER_AI_ENABLED=true + 真实 DeepSeek 调用 (golden path) — 验证 ✓ → 真实 200
2. ICODER_AI_ENABLED=true + toxiproxy 注入 DeepSeek 502 — 验证 3 次 retry → 502 → run_history.failed
3. ICODER_AI_ENABLED=false → 重启 server → 真实 503 路径 (cloud-mode fail-closed 启动)
