"""iCoDer Coding Review Agent — canonical constants (SSOT).

Phase D3 (2026-06-26) — replaces the deprecated
``official_agents.homepage_coding_review`` shim. The 14-stage cosmetic
homepage pipeline is gone; the canonical MedCodER 5-stage pipeline owns
this surface.

Used by:

  - ``app/api/icoder_coding_review.py`` — REST handlers
  - ``icoder_runtime/reports/coding_review_report.py`` — HTML report
  - ``tests/test_api/test_icoder_coding_review_no_key.py`` — credential gate
  - ``tests/e2e_product/test_*.py`` — end-to-end validation

Phase A (2026-06-25) had inlined these constants in
``app/api/icoder_coding_review.py``; Phase D3 promotes them to a shared
module so multiple call sites can import without touching the
deprecated shim package.

These constants describe the **Medical Coding Agent**, not the iCoDer
platform as a whole. They are not user-facing product config — they
are agent-pack-level invariants that must remain stable across
``agent_pack.json`` updates.
"""

from __future__ import annotations

# ── Agent identity ──────────────────────────────────────────────────────
# Canonical agent_ref for the Medical Coding Review Agent. Replaces the
# legacy ``icoder/homepage-coding-review-agent@1.0.0`` reference. The
# MedCodER 5-stage pipeline is what the runtime dispatches; the agent
# ref surfaces in audit logs, M2a trace store, and Agent Card metadata.
AGENT_REF: str = "icoder/medcoder-coding-review-agent@1.0.0"

# Agent category used for the registry / marketplace. Was
# ``official_reference_agent`` under the legacy 14-stage homepage
# pipeline; MedCodER is a ``medical-coding`` category agent.
AGENT_CATEGORY: str = "medical-coding"

# MedCodER 5 阶段管线 — replaces the legacy 14-stage cosmetic ordering.
# Used by report sections, run_trace timeline, and pipeline_validation
# disclaimer wording. The 14-stage list is preserved only inside the
# ``tests/test_api/test_coding_review_real_trace.py`` legacy fixture for
# migration of historical reports.
PIPELINE_STAGES: list[str] = [
    "extraction",
    "retrieval",
    "merge",
    "rerank",
    "calibration",
]

# ── High-risk codes (M2b-2 §6 硬性) ─────────────────────────────────────
# 5 重点高风险易错编码点 — clinical constants, **not** pipeline-shaped.
# These codes were the same under the 14-stage homepage pipeline and
# remain the same under the MedCodER 5-stage pipeline. Do NOT reorder
# or rewrite — hospital coders memorize this set.
PRIORITY_HIGH_RISK_CODES: set[str] = {
    "I66.901",          # 脑梗死
    "J98.414",          # 肺不张
    "M80.900",          # 骨质疏松
    "45.1600x001",      # 胃镜活检
    "Z51.102",          # 化疗
}

# ── Human-review decision + action enums ────────────────────────────────
# Mirrors the 5 human_decision values used by the M2b-2 import script.
# These are the values a reviewer can leave in a CodingReviewRun row's
# ``human_review_records`` field.
ALLOWED_HUMAN_DECISIONS: set[str] = {
    "support_direct",       # 证据直接支持
    "support_indirect",     # 证据间接支持
    "insufficient",         # 证据不足
    "reject",               # 驳回
    "past_history",         # 既往史
}

# 5 human-review action values (M3 new). Distinct from
# ``ALLOWED_HUMAN_DECISIONS``: actions are what the reviewer *did* to
# the AI suggestion; decisions are the justification narrative.
ALLOWED_HUMAN_ACTIONS: set[str] = {
    "accept",                   # 接受 AI 建议
    "reject",                   # 驳回 AI 建议
    "modify",                   # 修改编码
    "insufficient_evidence",    # 标记证据不足
    "escalate",                 # 提交上级复核
}

# ── Pipeline validation disclaimer (M3-0 §18 硬性) ─────────────────────
# Banner text shown in HTML reports when ``mode == "link_validation"``.
# MedCodER wording: drop the 14-stage reference, name the MedCodER
# agent explicitly. The disclaimer must NOT make model-effect claims
# (no F1 / accuracy / precision) and must forbid production writeback
# or insurance upload.
PIPELINE_VALIDATION_DISCLAIMER: str = (
    "本报告由 MedCodER Coding Review Agent "
    "(icoder/medcoder-coding-review-agent@1.0.0) 在 pipeline validation 模式 "
    "(M3-0 默认) 下生成. 此模式下 prediction = gold_evidence, 仅用于验证 "
    "iCoDer Runtime 5 阶段技术链路端到端通, 不代表模型效果, 不可用于生产写回 "
    "或医保上传. 如需真实模型 P/R/F1, 需在 M3 后续阶段提供 external "
    "prediction-file 并切换至 model_evaluation 模式."
)


__all__ = [
    "AGENT_REF",
    "AGENT_CATEGORY",
    "PIPELINE_STAGES",
    "PRIORITY_HIGH_RISK_CODES",
    "ALLOWED_HUMAN_DECISIONS",
    "ALLOWED_HUMAN_ACTIONS",
    "PIPELINE_VALIDATION_DISCLAIMER",
]
