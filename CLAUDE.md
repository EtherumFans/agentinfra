# iCoDer — 医疗收入合规 AI Runtime 基础设施

## 产品定位

iCoDer 是面向中国医院场景的**医疗收入合规 AI Runtime 基础设施**。

它不是单一编码工具，而是一个能加载、运行、治理多个合规 Agent 的平台 Runtime。

```
医疗收入合规体系
├── 编码合规 (Medical Coding)      ← 第一个官方样板 Agent, 已完成闭环
├── 分组合规 (DRG/DIP)            ← 规则结构已预留
├── 结算合规 (Insurance Audit)    ← 规则结构已预留
├── 收费合规 (Charge Compliance)  ← 规则结构已预留
├── 病历合规 (Document Evidence)  ← 规则结构已预留
└── 审计合规 (Audit)              ← AuditLog/RunHistory 已完整
```

## 架构层次

```
第四层: Business Workbenches   app/api/*         ~190 endpoints
第三层: Official Agent Packs   official_agents/   Medical Coding (icoder/medical-coding-agent@1.0.0)
第二层: Compliance Services    compliance_services/ RuleEngine + MedicalCodingRuleSet (12 rules)
第一层: Runtime Core           icoder_runtime/   AgentRunner, LLMGateway, Registry, Observability, DataPolicy
```

## Runtime Core 职责

通用 Agent 基础设施，不包含任何医学编码领域知识：
- AgentPackageV1 — .icoder-agent 包格式与校验
- RuntimeAgentRegistry — 持久化 Agent 注册表
- AgentRunner — Agent 执行引擎
- LLMGateway — LLM Provider 路由层
- DataPolicy — 医院私有化数据不出院策略
- RunHistory, AuditLog, FallbackTracker, ShadowDiffService — 可观测性

## Compliance Services 职责

领域独立的合规规则验证框架：
- RuleEngine — 多 rule_set 支持 (medical_coding, drg_dip, insurance_audit, charge_compliance, document_evidence)
- MedicalCodingRuleSet — ICD-10/ICD-9-CM-3 编码规则 (R001-R010 + MC-R-M80-001)
- CodingEngineAdapter — 编码推理适配器抽象

## 关键调用链

```
Agent 开发 → pack → Marketplace publish → install → PlatformRuntime → AgentRunner
  → LLMGateway → DeepSeek V4 → Compliance RuleEngine → RepairLoop → RuntimeRunResult
```

## 运行模式

| 模式 | 环境变量 | 说明 |
|------|---------|------|
| legacy | `ICODER_EXECUTION_MODE=legacy` | 旧 Orchestrator 路径 (DEPRECATED) |
| platform_runtime | `ICODER_EXECUTION_MODE=platform_runtime` | 新 PlatformRuntime 路径 |
| shadow | `ICODER_EXECUTION_MODE=shadow` | 旧路径返回, 新路径后台对比 |

## 启动命令

```bash
# 标准开发启动
export ICODER_CREDENTIAL_LLM=<your-deepseek-api-key>
export ICODER_ALLOW_EXTERNAL_LLM=true
export ICODER_EXECUTION_MODE=platform_runtime
export ICODER_REVIEW_CODING_MODE=platform_runtime  # 不设置则跟随 EXECUTION_MODE
export ICODER_FALLBACK_TO_LEGACY=false              # 开发阶段建议关闭，验证新路径
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端
cd frontend
npm run dev
```

## 金标准评估

```bash
python scripts/e2e_runtime_validation.py --base-url http://localhost:8000
# 30 cases, Precision 0.73, Recall 0.79, F1 0.76
```

## 技术栈

- 后端: FastAPI + SQLAlchemy (async) + SQLite
- LLM: DeepSeek V4 (deepseek-v4-flash) via LLMGateway
- 前端: React + TypeScript + Vite + Tailwind CSS
- 测试: pytest (80 tests)
