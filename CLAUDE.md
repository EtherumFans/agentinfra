# iCoDer — 医疗收入合规 AI Runtime 基础设施

## 产品定位

iCoDer 是面向中国医院场景的**医疗收入合规 AI 平台**。

它部署在医院内网服务器上（Docker），医生通过浏览器访问，HIS/EMR 通过 API 集成。
不是装在医生电脑上的桌面软件。

Runtime 是 iCoDer Server 的内核执行引擎（不是独立的便携 Runtime）。

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

## 部署模型

| 环境 | 方式 | 说明 |
|------|------|------|
| 开发环境 | `python -m uvicorn` + `npm run dev` | 本地前后端分离 |
| 医院生产 | `docker compose up -d` | 一键部署 (PostgreSQL + Redis + Nginx) |
| ISV 开发 | CLI: `icoder pack`, `icoder test` | Agent 打包和本地测试 |

**Runtime 不再是独立的 pip 包安装到医生电脑。** Runtime 是 iCoDer Server 的内核。

## 启动命令

```bash
# 开发环境
docker compose up -d   # 推荐: PostgreSQL + Redis + Nginx
# 或
cd backend && python -m uvicorn app.main:app --port 8000  # 轻量开发

# 环境变量
export ICODER_EXECUTION_MODE=platform_runtime
export ICODER_ALLOW_EXTERNAL_LLM=true
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
