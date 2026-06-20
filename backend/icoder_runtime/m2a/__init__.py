"""iCoDer M2a — Runtime 技术闭环（technical closed loop）。

提供 4 个真实可运行的最小闭环（不依赖占位模拟数据）：

- RunTrace         真实运行追踪记录（UUIDv7 标识 + 工具调用 + 终态）
- RiskRouter       4 档风险路由器（low/medium/high/critical）
- SafetyGate       医学安全门禁（12 指标 + 8 发布门禁规则）
- HumanReview      人工复核写回（带 reason_code + 拒绝 sample）

设计原则：
- sample 数据进入生产 trace 一律 critical/reject（绝不静默通过）
- 占位模拟数据禁止触发写回、规则升级、学习闭环、医保阻断
- LLM 故障时强制人工复核，**不**自动用 mock 兜底
- 所有产物 JSONL 追加写，append-only，便于审计
"""
