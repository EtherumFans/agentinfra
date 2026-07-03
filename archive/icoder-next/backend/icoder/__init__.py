"""iCoDer-next — 医疗收入合规 AI Runtime（端到端薄竖切）。

分层（对齐 E:\\Corti4C\\CLAUDE.md 的架构，重写为干净最小实现）:
- icoder.runtime   — Runtime Core: 通用 Agent 基础设施，无领域知识
- icoder.experts   — 可复用 Expert: coding-expert (4 工具) + 合规门禁
- icoder.agents    — 薄 Agent 定义 (systemPrompt + experts)
- icoder.api       — Business Workbench: FastAPI 端点 + stateless 鉴权
- icoder.report    — 证据回链报告渲染
"""

__version__ = "0.1.0"
