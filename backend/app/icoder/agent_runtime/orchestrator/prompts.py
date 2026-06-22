"""Orchestrator system prompt + Plan schema (SPEC §6.1, §6.2).

The Orchestrator does not own business logic — it dispatches. The system
prompt encodes the role boundary and the hard production_writeback_blocked
red line. The Plan schema describes the structured JSON the Planner LLM
must return.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from icoder_runtime.types import AgentDefinition


# ---------------------------------------------------------------------------
# Orchestrator system prompt (SPEC §6.1, verbatim)
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM_PROMPT: str = """# Role
你是 iCoDer Agent Runtime 的中央协调器 (Orchestrator)。你的唯一职责是**调度**, 不做具体业务。
- 不编码、不分组、不审计、不算费
- 不直接回答用户的临床问题
- 不调用任何工具 (工具由 Expert 调用, 你不接触)

# 任务
根据用户输入 + Agent 声明的 Experts, 产出一个**调度 Plan** (JSON), 说明:
1. 需要委托哪些 Expert (按优先级)
2. 每个 Expert 接收什么子输入
3. Expert 之间的依赖关系 (可选, Phase 1 不实现)

# 输入
- 用户输入: 已 PHI 脱敏 (姓名/身份证/电话/地址 等已替换为 <REDACTED:XXX>)
- Agent 定义: {agent_id, name, available_experts[], rule_sets[], non_goals, output_contract}

# 严格约束 (硬红线)
1. **PHI 已脱敏**: 你的所有输入都已脱敏, 你看到 <REDACTED:NAME> 等占位符时, **不要试图还原或回显**
2. **production_writeback_blocked = true**: 你**不**调用任何写回 EMR/HIS 的动作, 这条红线恒定
3. **不做具体活**: 你只输出 Plan JSON, 不输出业务结论
4. **Expert 委托边界**: 业务能力 = Experts 的能力, 你不替代
5. **结构化输出**: 必须严格按 Plan schema 输出 JSON, 不输出 markdown / 自然语言

# Plan schema
{
  "experts": [
    {
      "expert_id": "coding-expert",
      "priority": 1,
      "critical": true,
      "subtask_input": "提取病历中的疾病诊断并按 ICD-10-CN 编码",
      "tool_constraints": ["icd_search", "code_verify"]
    }
  ],
  "reason": "病历包含疾病诊断, 需要先做编码审核"
}

# 决策原则
- 单一目标 = 单一 Expert (如: \"纯编码审核\" → 调 coding-expert)
- 复合目标 = 多 Expert (如: \"编码 + DRG 分组\" → 调 coding-expert + drg-expert)
- 拒绝越界: 用户问\"这个病历严重吗\" → 拒绝, 让 Expert 回答
"""


# ---------------------------------------------------------------------------
# Hard constraints — present in prompt, must NOT be silently removed.
# Spec §6.1 #2 (production_writeback_blocked) + §4.3 (Q1).
# ---------------------------------------------------------------------------

PRODUCTION_WRITEBACK_BLOCKED: str = "production_writeback_blocked = true"

PHI_REDACTION_NOTICE: str = "PHI 已脱敏"

NON_GOALS_NOTICE: str = "不做具体活"


def assert_prompt_invariants(prompt: str = ORCHESTRATOR_SYSTEM_PROMPT) -> None:
    """Sanity check — the spec invariants MUST appear in the prompt.

    Use in tests and at startup. ``ValueError`` if anything is missing.
    """
    for needle in (
        PRODUCTION_WRITEBACK_BLOCKED,
        PHI_REDACTION_NOTICE,
        NON_GOALS_NOTICE,
        "Plan schema",
    ):
        if needle not in prompt:
            raise ValueError(f"Orchestrator system prompt missing required text: {needle!r}")


# ---------------------------------------------------------------------------
# Plan schema description (sent as part of user message for grounding)
# ---------------------------------------------------------------------------

PLAN_SCHEMA_DESCRIPTION: str = """Return JSON only, matching this schema:

{
  "experts": [
    {
      "expert_id": "<string, must be one of the agent's available_experts>",
      "priority": <int, 1 = highest; lower number = higher priority>,
      "critical": <bool, true = fail the run if this expert fails>,
      "subtask_input": "<string, the sub-task for this expert>",
      "tool_constraints": ["<tool_id>", ...]
    }
  ],
  "reason": "<short string, why this plan>"
}

Constraints:
- experts[] must be non-empty
- priority must be a positive integer; ties broken by order in agent.expert_ids
- critical=true for experts whose failure should fail the whole run
- subtask_input is opaque; it is passed verbatim to the expert
"""


def build_planner_user_message(
    *,
    redacted_input: str,
    agent_id: str,
    agent_name: str,
    available_experts: list[str],
    non_goals: str = "",
    output_contract: str = "",
) -> str:
    """Compose the Planner LLM user message (SPEC §6.2).

    The Planner receives:
    - redacted input (PHI-safe)
    - a compact summary of the Agent definition
    - the Plan schema for grounding
    """
    parts: list[str] = []
    parts.append(f"# Agent\nid: {agent_id}\nname: {agent_name}")
    if available_experts:
        parts.append("available_experts:\n" + "\n".join(f"  - {e}" for e in available_experts))
    if non_goals:
        parts.append(f"non_goals: {non_goals}")
    if output_contract:
        parts.append(f"output_contract: {output_contract}")

    parts.append("\n# User input (PHI redacted)\n" + redacted_input)
    parts.append("\n# " + PLAN_SCHEMA_DESCRIPTION.replace("\n", "\n# "))
    return "\n".join(parts)


def build_planner_user_message_from_agent(
    *,
    redacted_input: str,
    agent: "AgentDefinition",
) -> str:
    """Convenience overload — pull fields from AgentDefinition directly."""
    return build_planner_user_message(
        redacted_input=redacted_input,
        agent_id=getattr(agent, "id", "") or agent.name,
        agent_name=agent.name,
        available_experts=list(agent.expert_ids or []),
        non_goals=", ".join(getattr(agent, "config", {}).get("non_goals", []) or []),
        output_contract=str(getattr(agent, "config", {}).get("output_contract", "")),
    )


__all__ = [
    "ORCHESTRATOR_SYSTEM_PROMPT",
    "PRODUCTION_WRITEBACK_BLOCKED",
    "PHI_REDACTION_NOTICE",
    "NON_GOALS_NOTICE",
    "PLAN_SCHEMA_DESCRIPTION",
    "assert_prompt_invariants",
    "build_planner_user_message",
    "build_planner_user_message_from_agent",
]