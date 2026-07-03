> **DEPRECATED (Phase 2-F / 2026-07-02 — TD-099)**: 本文档为旧版架构描述, 已被新版替代.
> 当前主线参考: [docs/architecture/CURRENT_ARCHITECTURE.md](architecture/CURRENT_ARCHITECTURE.md) + [docs/phase2/MAINLINE_VS_LEGACY.md](phase2/MAINLINE_VS_LEGACY.md)
> P1.3 Corti Parity Audit 已通过 (2026-07-02); MedCodER 降级为 Pre-built Agent #18, 非产品本体.
> 保留仅作历史参考 — 勿据此文档做架构决策.

# iCoDer 架构文档 (DEPRECATED)

## 四层架构
1. Runtime Core — AgentRunner(含Pre/PostExecutionGuard), LLMGateway, Registry, DataPolicy, SafetySpiralDetector
2. Compliance Services — RuleEngine(R001-R012), 5 RuleSets(预留DRG/DIP/医保/收费/病历)
3. Official Agent Packs — 15个.icoder-agent包: MedicalCoding + 4-Agent Pipeline + 10专项
4. Business Workbenches — 179端点, 25路由模块

## 安全架构
PreExecutionGuard → AgentRunner.run() → PostExecutionGuard → SafetySpiralDetector
