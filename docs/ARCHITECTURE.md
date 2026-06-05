# iCoDer 架构文档

## 四层架构
1. Runtime Core — AgentRunner(含Pre/PostExecutionGuard), LLMGateway, Registry, DataPolicy, SafetySpiralDetector
2. Compliance Services — RuleEngine(R001-R012), 5 RuleSets(预留DRG/DIP/医保/收费/病历)
3. Official Agent Packs — 15个.icoder-agent包: MedicalCoding + 4-Agent Pipeline + 10专项
4. Business Workbenches — 179端点, 25路由模块

## 安全架构
PreExecutionGuard → AgentRunner.run() → PostExecutionGuard → SafetySpiralDetector
