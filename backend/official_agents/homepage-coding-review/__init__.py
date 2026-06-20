"""iCoDer 病案首页编码审核 Agent (Homepage Coding Review Agent) — 第一个官方样板 Agent.

Agent ref: icoder/homepage-coding-review-agent@1.0.0
Category: official_reference_agent
Subcategory: homepage-coding-review
Build target: M3-0 / M3-1

**严格定位 (M3-0 红线)**:
- iCoDer 是医学编码 Agent 开发和运行基础设施
- 本 Agent 是 iCoDer 上的第一个官方样板 Agent (Reference / Starter Agent)
- 用于验证和展示 iCoDer 的 Runtime / Agent 编排 / 证据回链 / 风险路由 / 医学安全门禁 / 人工复核 / 审计报告 / API / 嵌入组件能力
- 不可被视为 iCoDer 全部产品定位

**复用的能力 (不重复造轮子)**:
- icoder/medical-coding-agent@1.0.0 — 核心 ICD-10 诊断 + ICD-9-CM-3 手术码生成
- HybridCodingAdapter (mode=hybrid) — Stage 1+2+3 候选生成
- M2aRecorder.inference + ctx.stage — Run Trace 接入
- RiskRouter + MedicalSafetyGate — 风险路由 + 安全门禁
- Compliance RuleEngine (medical_coding rule_set) — R001-R010 规则

**新增的能力 (M3-0 落地)**:
- 14 阶段细粒度工具调用编排
- 高风险易错编码点专项审查 (5 重点码 + 62 全集)
- pipeline validation 模式 (默认) + 模型评估模式 (M3+)
- 标准 API: /api/icoder/coding-review/{run,human-review,report}
- 嵌入式组件: IcoderReviewPanel / IcoderEvidenceViewer / IcoderTraceViewer
- HTML 审核报告生成 (18 节, 含 disclaimer)

**不变量**:
- 不得伪造医学结果 (无 prediction file / B0 baseline / 人工证据 → unavailable)
- pipeline validation 模式 disclaimer 必显
- sample / validation 数据 production_allowed=false
- 主诊断修改必须人工确认
- 高风险易错编码点必须 human_review_required=true
"""

from __future__ import annotations

from pathlib import Path

AGENT_REF = "icoder/homepage-coding-review-agent@1.0.0"
AGENT_CATEGORY = "official_reference_agent"
AGENT_SUBCATEGORY = "homepage-coding-review"
AGENT_DIR = Path(__file__).resolve().parent
AGENT_PACK_JSON = AGENT_DIR / "agent_pack.json"

# 14 阶段工具调用 (与 system_prompt 对齐, RunTrace timeline 按此顺序展示)
PIPELINE_STAGES = [
    "document_normalizer",
    "evidence_fact_extractor",
    "coding_eligibility_classifier",
    "candidate_generator",
    "ontology_service",
    "high_risk_coding_point_checker",
    "kg_auditor",
    "code_reconciler",
    "risk_router",
    "medical_safety_gate",
    "human_review",
    "report_generator",
    "run_trace_emitter",
    "audit_logger",
]

# 5 重点高风险易错编码点 (M2b-2 §6 硬性)
PRIORITY_HIGH_RISK_CODES = [
    "I66.901",  # 脑梗死
    "J98.414",  # 肺不张
    "M80.900",  # 骨质疏松
    "45.1600x001",  # 胃镜活检
    "Z51.102",  # 化疗
]

# 5 合法 human_decision 值 (与 M2b-2 import 脚本一致)
ALLOWED_HUMAN_DECISIONS = {
    "support_direct", "support_indirect", "insufficient", "reject", "past_history",
}

# 5 合法 human-review action 值 (M3 新增, 区别于 human_decision)
ALLOWED_HUMAN_ACTIONS = {
    "accept",       # 接受 AI 建议
    "reject",       # 驳回 AI 建议
    "modify",       # 修改编码 (主诊断修改必须人工确认)
    "insufficient_evidence",  # 标记证据不足
    "escalate",     # 提交上级复核
}

PIPELINE_VALIDATION_DISCLAIMER = (
    "本报告由 病案首页编码审核 Agent (Homepage Coding Review Agent, "
    "icoder/homepage-coding-review-agent@1.0.0) 在 pipeline validation 模式 (M3-0 默认) 下生成. "
    "此模式下 prediction = gold_evidence, 仅用于验证 iCoDer Runtime 14 阶段技术链路端到端通, "
    "不代表模型效果, 不可用于生产写回或医保上传. "
    "如需真实模型 P/R/F1, 需在 M3 后续阶段提供 external prediction-file 并切换至 model_evaluation 模式."
)


def load_agent_pack() -> dict:
    """读 agent_pack.json 内容。"""
    import json
    with open(AGENT_PACK_JSON, encoding="utf-8") as f:
        return json.load(f)


__all__ = [
    "AGENT_REF",
    "AGENT_CATEGORY",
    "AGENT_SUBCATEGORY",
    "AGENT_DIR",
    "AGENT_PACK_JSON",
    "PIPELINE_STAGES",
    "PRIORITY_HIGH_RISK_CODES",
    "ALLOWED_HUMAN_DECISIONS",
    "ALLOWED_HUMAN_ACTIONS",
    "PIPELINE_VALIDATION_DISCLAIMER",
    "load_agent_pack",
]
