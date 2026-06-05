# iCoDer Runtime 迁移指南

## 概述

iCoDer 正在将 Agent 执行从旧的硬编码流水线（`app/services/agent_runner`、`app/agents/orchestrator`）
迁移到新的统一 Runtime（`icoder_runtime` + `LLMGateway` + `PlatformRuntime`）。

## 执行路径对照

| 生产 API | 旧路径（legacy） | 新路径（platform_runtime） | 当前默认 |
|----------|-----------------|--------------------------|---------|
| `POST /api/agents/{id}/run` | `app.services.agent_runner.AgentRunner` | `PlatformRuntime.run_agent()` via RuntimeAgentRegistry | legacy |
| `POST /api/reviews` | `app.agents.orchestrator.AgentOrchestrator.run_pipeline()` | `ReviewCodingService.review()` → `PlatformRuntime.run_agent()` | legacy |
| `POST /api/marketplace/.../install` | N/A（新增） | `PlatformRuntime.install_agent()` → `RuntimeAgentRegistry` | N/A |
| LLM 调用 | `app.services.llm_service.LLMService`（直接 AsyncOpenAI） | `LLMGateway.generate()` → Provider 路由 | legacy |

## Feature Flag 控制

通过环境变量控制：

```bash
# Agent 执行模式
ICODER_EXECUTION_MODE=legacy|platform_runtime|shadow

# Reviews/Encounters 执行模式
ICODER_REVIEW_CODING_MODE=legacy|platform_runtime|shadow

# 新模式失败时是否回退旧路径
ICODER_FALLBACK_TO_LEGACY=true|false

# Agent Registry 存储目录
ICODER_REGISTRY_DIR=.icoder
```

三种模式：

- `legacy`：使用旧路径（当前默认）
- `platform_runtime`：使用新 PlatformRuntime
- `shadow`：旧路径返回结果，新路径后台异步执行并记录差异日志

## 旧模块弃用状态

| 模块 | 状态 | 计划移除版本 |
|------|------|-------------|
| `app/services/agent_runner.py` | DEPRECATED | v2.1 |
| `app/services/llm_service.py` | DEPRECATED（LLM 调用部分） | v2.1 |
| `app/agents/orchestrator.py` | DEPRECATED | v2.2 |
| `app/services/runtime.py`（DeterministicRuntime） | 保留（安全框架，与新旧无关） | N/A |
| `app/services/review_coding_service.py` | 新路径，ACTIVE | N/A |

## 迁移时间线

**Phase 1（当前）：**
- 所有 API 默认 legacy 模式
- 可通过 `ICODER_EXECUTION_MODE=platform_runtime` 手动启用新路径
- `ICODER_EXECUTION_MODE=shadow` 做并行对比验证

**Phase 2（v2.0）：**
- 默认切换到 `shadow` 模式
- 收集新路径的差异日志并修复

**Phase 3（v2.1）：**
- 默认切换到 `platform_runtime` 模式
- 移除 `app/services/agent_runner.py` 和 `app/services/llm_service.py` 的 LLM 调用部分

**Phase 4（v2.2）：**
- 默认 `platform_runtime` 模式
- 移除 `app/agents/orchestrator.py`，替换为 `ReviewCodingService`
- 移除 `fallback_to_legacy` 选项

## 新旧路径差异

### 旧路径

```
POST /api/reviews
  → agent_orchestrator.run_pipeline()
    → EvidenceExtractionExpert → llm_service.chat()
    → ICDDiagnosisExpert → llm_service.chat()
    → ProcedureCodingExpert → llm_service.chat()
    → ... 固定9步流水线
    → return structured result
```

### 新路径

```
POST /api/reviews（review_coding_mode=platform_runtime）
  → ReviewCodingService.review()
    → PlatformRuntime.run_agent("medical-coding-reviewer")
      → AgentRunner.run()
        → LLMGateway.generate()
          → MedicalCodingLLMProvider（或 DeepSeekProvider）
            → return structured result
```

## 验证新路径

```bash
# 启动主平台（shadow 模式）
ICODER_EXECUTION_MODE=shadow ICODER_REVIEW_CODING_MODE=shadow \
  python -m uvicorn app.main:app --port 8000

# 安装 agent 到 Runtime
curl -X POST http://localhost:8000/api/marketplace/packages/compliance-guardrail-agent-1.0.0/install \
  -H "Authorization: Bearer <token>"

# 查看已安装
curl http://localhost:8000/api/marketplace/installed \
  -H "Authorization: Bearer <token>"

# 以新模式运行（通过 /api/agents/{id}/run）
ICODER_EXECUTION_MODE=platform_runtime \
  curl -X POST http://localhost:8000/api/agents/compliance-guardrail-agent-1.0.0/run \
    -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"input": "患者女性，65岁，胸痛3小时"}'
```
