"""OpenAI function-calling schemas for expert tools.

The executor hands these to the model alongside the agent's system prompt; the model
decides which tools to call. Tool ``name`` matches the expert method name exactly, so the
executor dispatches via ``getattr(expert, name)(**arguments)``.

This mirrors Corti's coding-expert tool surface (Search / Verify / Guidelines / Explore).
``submit_findings`` is an iCoDer-specific terminal tool: Corti returns prose Markdown, but
the slice needs machine-readable entities to drive evidence highlighting. Char offsets are
NEVER taken from the model — the executor anchors each ``evidence_quote`` server-side.
"""
from __future__ import annotations


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# coding-expert: the same four tools as Corti's coding-expert, over ICD-10-CN / ICD-9-CM-3.
_CODING_EXPERT_TOOLS: list[dict] = [
    _fn(
        "search",
        "检索 ICD-10-CN / ICD-9-CM-3 索引，按临床术语返回候选编码（同义词感知）。"
        "必须先 search 再 verify，绝不凭记忆直接给码。",
        {"term": {"type": "string", "description": "要检索的临床术语（诊断或手术操作名）"}},
        ["term"],
    ),
    _fn(
        "verify",
        "核验单个编码：返回 display / 体系 / code_type(diagnosis|procedure) / 高风险标记 / "
        "指导性注释（Includes / Excludes / Code First / Use Additional）。",
        {"code": {"type": "string", "description": "要核验的编码，如 I50.900"}},
        ["code"],
    ),
    _fn(
        "guidelines",
        "返回该编码的官方编码指南（每个拟用编码都应查阅）。",
        {"code": {"type": "string", "description": "要查指南的编码"}},
        ["code"],
    ),
    _fn(
        "explore",
        "返回该编码的层级邻居：父编码 / 兄弟编码 / 子编码，用于确认编码到位（specificity）。",
        {"code": {"type": "string", "description": "要展开层级的编码"}},
        ["code"],
    ),
    _fn(
        "alternatives",
        "返回该编码的易错鉴别项（P0/P1 决策对）：与之易混的编码及鉴别要点。用于高风险/易错编码的"
        "辨析——iCoDer 在国标编码之外额外维护的鉴别知识库（Corti 无此工具）。",
        {"code": {"type": "string", "description": "要查易错鉴别项的编码，如 M80.900"}},
        ["code"],
    ),
]

_TOOLS_BY_EXPERT: dict[str, list[dict]] = {
    "coding-expert": _CODING_EXPERT_TOOLS,
}


# Terminal tool: calling it submits the structured result and ends the loop.
SUBMIT_FINDINGS_TOOL: dict = _fn(
    "submit_findings",
    "提交最终抽取结果并结束本次任务。entities 为已确认的临床事实数组；每项的 evidence_quote "
    "必须从去标识病历原文中逐字摘录、与原文完全一致（用于服务端证据回链定位）。",
    {
        "entities": {
            "type": "array",
            "description": "抽取到的临床事实列表",
            "items": {
                "type": "object",
                "properties": {
                    "term": {
                        "type": "string",
                        "description": "规范化的临床术语（诊断或手术操作）",
                    },
                    "evidence_quote": {
                        "type": "string",
                        "description": "从去标识病历原文中逐字摘录、完全一致的支持证据片段",
                    },
                },
                "required": ["term", "evidence_quote"],
            },
        }
    },
    ["entities"],
)

SUBMIT_FINDINGS = "submit_findings"


def build_expert_tools(expert) -> list[dict]:
    """OpenAI function schemas for one expert's tools (empty if the expert has none registered)."""
    return list(_TOOLS_BY_EXPERT.get(expert.id, []))
