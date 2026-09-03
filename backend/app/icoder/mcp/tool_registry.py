"""Static MCP tool registry — single source of truth for the 5 MedCodER tools.

Each tool is declared as a :class:`ToolDescriptor` with name, description,
JSON Schema for inputs/outputs (derived from Pydantic models in
:meth:`ToolDescriptor.from_pydantic`), and a dotted-path handler reference
that the server resolves at dispatch time.

The :data:`TOOL_REGISTRY` dict is the SSOT — the server boot-time asserts
that ``set(TOOL_REGISTRY) == {t["name"] for t in agent_pack["tools"]}``
(see :func:`app.icoder.mcp.server.assert_tool_registry_matches_agent_pack`).
If you add or remove a tool here, update ``medcoder-coding-review/agent_pack.json``
in the same commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.icoder.mcp.auth import MCPAuthConfig


# ── Input / Output Pydantic schemas (one per tool) ────────────────

class SearchIcdInput(BaseModel):
    """Input for ``search_icd`` — semantic ICD candidate retrieval."""

    emr_text: str = Field(
        ..., min_length=1, max_length=20000,
        description="EMR text (or disease mention) to retrieve candidates for.",
    )
    top_k: int = Field(
        default=5, ge=1, le=50,
        description="Number of candidates to return (1-50, default 5).",
    )


class SearchIcdOutput(BaseModel):
    """Output for ``search_icd``."""

    candidates: list[dict] = Field(
        default_factory=list,
        description="Top-K ICD candidates, each with code/name/score/chapter/source.",
    )
    source: str = Field(
        default="retrieve",
        description="Provenance tag (always 'retrieve' for this tool).",
    )


class VerifyCodeInput(BaseModel):
    """Input for ``verify_code`` — catalog membership + assignability + hierarchy."""

    code: str = Field(
        ..., min_length=1, max_length=20,
        description="ICD-10 code (e.g. 'I50.900' or 'I25') to verify.",
    )


class VerifyCodeOutput(BaseModel):
    """Output for ``verify_code`` (Phase 4-C extended — mirrors Corti verify)."""

    code: str
    in_catalog: bool = Field(description="True iff the code is in icd10cn_code_catalog OR is a known category prefix.")
    assignable: bool = Field(
        default=False,
        description="True iff ``code`` is a leaf code (not a category). A category "
                    "code like 'I25' is in_catalog=True but assignable=False — the "
                    "LLM must pick a more specific subdivision.",
    )
    chapter: str = Field(default="", description="ICD-10 chapter heading (empty if unknown).")
    name: str = Field(default="", description="Canonical Chinese name (empty if unknown).")
    aliases: list[str] = Field(default_factory=list)
    parent_hierarchy: list[str] = Field(
        default_factory=list,
        description="[chapter_no, category_code, code] — top-down hierarchy.",
    )
    excludes1: list[str] = Field(
        default_factory=list,
        description="Excludes1 notes — codes that CANNOT be coded together with this one. "
                    "(Phase 4-C: empty — no Excludes KB yet.)",
    )
    excludes2: list[str] = Field(
        default_factory=list,
        description="Excludes2 notes — codes that SHOULD NOT be coded together. "
                    "(Phase 4-C: empty — no Excludes KB yet.)",
    )
    code_first_notes: list[str] = Field(
        default_factory=list,
        description="'Code first underlying disease' notes. (Phase 4-C: empty.)",
    )
    use_additional_code_notes: list[str] = Field(
        default_factory=list,
        description="'Use additional code' notes. (Phase 4-C: empty.)",
    )
    children_if_non_assignable: list[dict] = Field(
        default_factory=list,
        description="When assignable=False, lists more specific subdivisions (top 20).",
    )


class GetGuidelinesInput(BaseModel):
    """Input for ``get_guidelines`` — chapter + general coding conventions."""

    code: str = Field(
        default="", max_length=20,
        description="Optional ICD-10 code — when provided, returns chapter-specific conventions.",
    )


class GetGuidelinesOutput(BaseModel):
    """Output for ``get_guidelines``."""

    chapter: str = Field(default="", description="Chapter label (e.g. '第9章 循环系统疾病').")
    chapter_conventions: list[str] = Field(
        default_factory=list,
        description="Chapter-specific conventions (1-3 rules).",
    )
    general_rules: list[str] = Field(
        default_factory=list,
        description="General ICD-10-CN coding rules (always returned).",
    )
    source: str = Field(default="internal_kb")


class ExploreCodeInput(BaseModel):
    """Input for ``explore_code`` — parent / siblings / children traversal."""

    code: str = Field(
        ..., min_length=1, max_length=20,
        description="ICD-10 code or category prefix (e.g. 'I25.10' or 'I25') to explore.",
    )


class ExploreCodeOutput(BaseModel):
    """Output for ``explore_code``."""

    code: str
    in_catalog: bool = False
    parent: dict | None = Field(
        default=None,
        description="Parent chapter + category info.",
    )
    siblings: list[dict] = Field(
        default_factory=list,
        description="Codes sharing the same category (top 20).",
    )
    children: list[dict] = Field(
        default_factory=list,
        description="More specific subdivisions (top 20).",
    )


class SearchCodesInput(BaseModel):
    """Input for ``search_codes`` — wraps ``search_icd`` with Corti-style alias."""

    query: str = Field(
        ..., min_length=1, max_length=20000,
        description="EMR text or disease mention to retrieve ICD candidates for.",
    )
    top_k: int = Field(
        default=5, ge=1, le=50,
        description="Number of candidates to return (1-50, default 5).",
    )


class SearchCodesOutput(BaseModel):
    """Output for ``search_codes`` — same shape as ``SearchIcdOutput``."""

    candidates: list[dict] = Field(default_factory=list)
    source: str = Field(default="retrieve")
    degraded: bool = False
    error_code: str = ""
    error_detail: str = ""


class GetDifferentiationHintInput(BaseModel):
    """Input for ``get_differentiation_hint``."""

    disease_text: str = Field(
        ..., min_length=1, max_length=500,
        description="Disease name (Chinese preferred).",
    )
    code_a: str = Field(
        default="", max_length=20,
        description="Optional first ICD code in the comparison pair.",
    )
    code_b: str = Field(
        default="", max_length=20,
        description="Optional second ICD code in the comparison pair.",
    )


class GetDifferentiationHintOutput(BaseModel):
    """Output for ``get_differentiation_hint``."""

    hints: list[str] = Field(
        default_factory=list,
        description="P0/P1 differentiation hints from coding_differentiation_kb.",
    )


class RerankCodesInput(BaseModel):
    """Input for ``rerank_codes`` — RankGPT-style re-rank."""

    disease_text: str = Field(..., min_length=1, max_length=500)
    evidence: str = Field(default="", max_length=5000)
    candidates: list[dict] = Field(
        ..., min_length=1, max_length=50,
        description="Candidate list from Stage 2/3 (each: code/name/score/chapter/source).",
    )


class RerankCodesOutput(BaseModel):
    """Output for ``rerank_codes``."""

    ranked: list[dict] = Field(
        default_factory=list,
        description="Top-K re-ranked codes, each with code/name/confidence/rationale.",
    )


class CalibrateConfidenceInput(BaseModel):
    """Input for ``calibrate_confidence`` — thin wrapper around
    ``confidence_calibrator.calibrate_all``."""

    diagnosis_candidates: list[dict] = Field(default_factory=list)
    procedure_candidates: list[dict] = Field(default_factory=list)
    primary_diagnosis: dict = Field(default_factory=dict)
    evidence_ranking: dict = Field(default_factory=dict)
    disagreement_analysis: dict = Field(default_factory=dict)
    primary_diag_reasoning: dict = Field(default_factory=dict)
    gold_diagnosis_codes: list[str] | None = None
    gold_procedure_codes: list[str] | None = None


class CalibrateConfidenceOutput(BaseModel):
    """Output for ``calibrate_confidence``."""

    coding_confidences: list[dict] = Field(default_factory=list)
    routing_decisions: list[dict] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)


# ── Phase 3-D2 Task 3 — 3 agent-backed MCP tools ──────────────────
# Each handler wraps the corresponding official_agent's run() (SSOT business
# logic) as an MCP tool. They're registered in TOOL_REGISTRY so the MCP
# dispatcher handles scope check + auth + trace + PHI redaction uniformly.
# The 3 simple agents (code-validation / compliance-guardrail /
# note-completeness) route through the dispatcher instead of bypassing it.


class ValidateCodesInput(BaseModel):
    """Input for ``validate_codes`` — Code Validation Agent."""

    coding_set: dict = Field(
        ...,
        description="Coding set to validate (primary_diagnosis / secondary_diagnoses / procedures).",
    )
    encounter_text: str = Field(
        default="", max_length=20000,
        description="Optional EMR text for context-aware rules.",
    )


class ValidateCodesOutput(BaseModel):
    """Output for ``validate_codes`` — matches CodeValidationOutputSchema."""

    review_conclusion: str = Field(default="", description="PASS / WARNING / FAIL")
    issues_found: list[dict] = Field(default_factory=list)
    manual_review_required: bool = False
    rule_set: str = Field(default="medical_coding")
    fired_rules: list[str] = Field(default_factory=list)
    code_assignment_summary: dict = Field(default_factory=dict)
    trace_refs: dict = Field(default_factory=dict)


class EvaluateComplianceInput(BaseModel):
    """Input for ``evaluate_compliance`` — Compliance Guardrail Agent."""

    coding_set: dict = Field(
        ...,
        description="Coding set to evaluate for DRG/DIP-sensitive items + compliance risks.",
    )
    encounter_text: str = Field(
        default="", max_length=20000,
        description="Optional EMR text for context-aware heuristics.",
    )


class EvaluateComplianceOutput(BaseModel):
    """Output for ``evaluate_compliance`` — matches ComplianceGuardrailOutputSchema."""

    review_conclusion: str = Field(default="", description="PASS / WARNING / FAIL")
    issues_found: list[dict] = Field(default_factory=list)
    manual_review_required: bool = False
    drg_suggestion: str = Field(default="")
    reviewed_codes: list[dict] = Field(default_factory=list)
    compliance_checks: dict[str, bool] = Field(default_factory=dict)
    rule_set: str = Field(default="medical_coding")
    fired_rules: list[str] = Field(default_factory=list)
    trace_refs: dict = Field(default_factory=dict)


class CheckDocumentationGapsInput(BaseModel):
    """Input for ``check_documentation_gaps`` — Note Completeness Agent."""

    encounter_text: str = Field(
        ..., min_length=1, max_length=20000,
        description="EMR text to check for documentation completeness.",
    )


class CheckDocumentationGapsOutput(BaseModel):
    """Output for ``check_documentation_gaps`` — matches NoteCompletenessOutputSchema."""

    completeness_score: float = Field(default=0.0)
    missing_sections: list[str] = Field(default_factory=list)
    present_sections: list[str] = Field(default_factory=list)
    supplement_suggestions: list[dict] = Field(default_factory=list)
    coding_drg_dip_impact: dict = Field(default_factory=dict)
    trace_refs: dict = Field(default_factory=dict)


# ── Tool descriptor ──────────────────────────────────────────────


@dataclass
class ToolDescriptor:
    """One MCP tool declaration.

    The ``handler_ref`` is a dotted-path string (``module:func``) that
    :func:`app.icoder.mcp.server.resolve_handler` turns into a callable
    at dispatch time. Lazy resolution keeps the registry importable
    even if a handler's module has heavy dependencies.

    ``auth_config`` (Phase 3-C1) carries per-tool MCP auth configuration
    (none / bearer / inherit / oauth2.0). ``None`` means "no auth
    requirement" — backwards compatible with pre-3-C1 tools. When set,
    the MCP dispatcher resolves it via :func:`app.icoder.mcp.auth_resolver.resolve_mcp_auth`
    before invoking the handler, and injects the resulting
    :class:`AuthHeader` onto ``request.state.auth_header``.

    ``required_scopes`` (Phase 3-D0 Task 1) is the optional list of
    scope strings the resolved auth must satisfy for the dispatcher
    to invoke the handler. The dispatcher compares
    ``set(required_scopes)`` against ``set(auth_header.granted_scopes)``;
    any missing scope → ``MCP_AUTH_FORBIDDEN`` (-32012). When
    ``required_scopes`` is empty (default), scope check is skipped
    (backwards compatible with pre-3-D0 tools). When
    ``required_scopes`` is non-empty but ``auth_config`` is ``None``
    or resolves to ``kind="none"``, the dispatcher returns
    ``MCP_AUTH_FORBIDDEN`` (no auth → no scopes → forbidden).
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler_ref: str
    stage: str = ""
    auth_config: MCPAuthConfig | None = None
    required_scopes: list[str] = field(default_factory=list)

    @staticmethod
    def from_pydantic(
        name: str,
        description: str,
        *,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        handler_ref: str,
        stage: str = "",
        auth_config: MCPAuthConfig | None = None,
        required_scopes: list[str] | None = None,
    ) -> "ToolDescriptor":
        return ToolDescriptor(
            name=name,
            description=description,
            input_schema=input_model.model_json_schema(),
            output_schema=output_model.model_json_schema(),
            handler_ref=handler_ref,
            stage=stage,
            auth_config=auth_config,
            required_scopes=list(required_scopes) if required_scopes else [],
        )


# ── Static registry (SSOT) ───────────────────────────────────────


TOOL_REGISTRY: dict[str, ToolDescriptor] = {
    "search_icd": ToolDescriptor.from_pydantic(
        "search_icd",
        "语义检索 ICD-10 编码候选 (BGE-M3 + FAISS top-K)。输入 EMR 文本或疾病名,返回 top-K 候选编码 (含 score + chapter + source)。",
        input_model=SearchIcdInput,
        output_model=SearchIcdOutput,
        handler_ref="app.icoder.mcp.handlers.search_icd:handle",
        stage="retrieval",
    ),
    "verify_code": ToolDescriptor.from_pydantic(
        "verify_code",
        "验证 ICD-10 编码是否在 icd10cn_code_catalog (37,897 码) 中,并返回 "
        "chapter + 中文名 + 同义词 + assignable (leaf vs category) + "
        "parent_hierarchy + children_if_non_assignable。Corti Code Validation "
        "verify 工具的 1:1 复刻 (Phase 4-C)。",
        input_model=VerifyCodeInput,
        output_model=VerifyCodeOutput,
        handler_ref="app.icoder.mcp.handlers.verify_code:handle",
        stage="compliance",
    ),
    "get_guidelines": ToolDescriptor.from_pydantic(
        "get_guidelines",
        "返回 ICD-10-CN 编码惯例: 章节级惯例 (Chapter I-XX,~7 章) + 10 条通用规则 "
        "(不编码未记录诊断 / 主诊断解释治疗资源消耗 / 最具体编码 / 组合码优先 等)。"
        "可选 code 参数返回该 code 所属章节的特定规则。Corti guidelines 工具复刻 (Phase 4-C)。",
        input_model=GetGuidelinesInput,
        output_model=GetGuidelinesOutput,
        handler_ref="app.icoder.mcp.handlers.get_guidelines:handle",
        stage="compliance",
    ),
    "explore_code": ToolDescriptor.from_pydantic(
        "explore_code",
        "遍历 ICD-10 编码的 parent / siblings / children。当 LLM 遇到 non-assignable "
        "类别码、组合码或需要更具体细分时调用。返回 parent (chapter + category) + "
        "siblings (top 20) + children (top 20)。Corti explore 工具复刻 (Phase 4-C)。",
        input_model=ExploreCodeInput,
        output_model=ExploreCodeOutput,
        handler_ref="app.icoder.mcp.handlers.explore_code:handle",
        stage="compliance",
    ),
    "search_codes": ToolDescriptor.from_pydantic(
        "search_codes",
        "语义检索 ICD-10 编码候选 — 包装 search_icd (BGE-M3 + FAISS top-K)。"
        "input 参数 query (Corti-style alias for emr_text) + top_k (1-50)。"
        "返回 candidates (含 code/name/score/chapter/source)。Corti search 工具复刻 (Phase 4-C)。",
        input_model=SearchCodesInput,
        output_model=SearchCodesOutput,
        handler_ref="app.icoder.mcp.handlers.search_codes:handle",
        stage="retrieval",
    ),
    "get_differentiation_hint": ToolDescriptor.from_pydantic(
        "get_differentiation_hint",
        "查询 coding_differentiation_kb.json,返回该疾病 (或 code pair) 的 P0/P1 区分提示 (≤3 条)。用于 Stage 4 rerank prompt 注入。",
        input_model=GetDifferentiationHintInput,
        output_model=GetDifferentiationHintOutput,
        handler_ref="app.icoder.mcp.handlers.get_differentiation_hint:handle",
        stage="merge",
    ),
    "rerank_codes": ToolDescriptor.from_pydantic(
        "rerank_codes",
        "RankGPT 风格 LLM 重排:对 Stage 2/3 候选集重排为 top-5,输出 per-code final_confidence + rationale。M2 不注入 CoT few-shot (M3)。",
        input_model=RerankCodesInput,
        output_model=RerankCodesOutput,
        handler_ref="app.icoder.mcp.handlers.rerank_codes:handle",
        stage="rerank",
    ),
    "calibrate_confidence": ToolDescriptor.from_pydantic(
        "calibrate_confidence",
        "多源置信度校准 + 自动路由 (auto/review/escalate)。Wrap 现有 confidence_calibrator.calibrate_all 服务原状,360 LOC 服务已有。",
        input_model=CalibrateConfidenceInput,
        output_model=CalibrateConfidenceOutput,
        handler_ref="app.icoder.mcp.handlers.calibrate_confidence:handle",
        stage="calibration",
    ),
    # ── Phase 3-D2 Task 3 — 3 agent-backed MCP tools ─────────────
    # These 3 tools wrap official_agents/{code_validation,
    # compliance_guardrail,note_completeness}/agent.py::run() as MCP
    # tools. They declare required_scopes so the dispatcher enforces
    # auth + scope check uniformly. The 3 simple agents route through
    # the dispatcher instead of bypassing it.
    "validate_codes": ToolDescriptor.from_pydantic(
        "validate_codes",
        "编码校验 Agent — 跑 MedicalCodingRuleSet (R001-R010 + MC-R-M80-001) "
        "验证编码集 (主诊断非空 / 编码格式 / 重复 / 手术 / 置信度+证据 / "
        "主诊断一致性 / 骨质疏松风险)。输入 coding_set (dict) + 可选 "
        "encounter_text;输出 review_conclusion + issues_found + fired_rules。",
        input_model=ValidateCodesInput,
        output_model=ValidateCodesOutput,
        handler_ref="app.icoder.mcp.handlers.validate_codes:handle",
        stage="validation",
        required_scopes=["coding:validate"],
    ),
    "evaluate_compliance": ToolDescriptor.from_pydantic(
        "evaluate_compliance",
        "合规守门 Agent — 评估 DRG/DIP 敏感项 + 合规风险 (CG-001..CG-004)。"
        "输入 coding_set (dict) + 可选 encounter_text;输出 review_conclusion "
        "+ issues_found + compliance_checks + drg_suggestion。",
        input_model=EvaluateComplianceInput,
        output_model=EvaluateComplianceOutput,
        handler_ref="app.icoder.mcp.handlers.evaluate_compliance:handle",
        stage="compliance",
        required_scopes=["compliance:evaluate"],
    ),
    "check_documentation_gaps": ToolDescriptor.from_pydantic(
        "check_documentation_gaps",
        "病历完整性 Agent — 检查 EMR 必备段落 (主诉/现病史/查体/辅助检查/"
        "诊断/手术/治疗计划) 是否齐全。输入 encounter_text;输出 "
        "completeness_score + missing_sections + supplement_suggestions。",
        input_model=CheckDocumentationGapsInput,
        output_model=CheckDocumentationGapsOutput,
        handler_ref="app.icoder.mcp.handlers.check_documentation_gaps:handle",
        stage="documentation",
        required_scopes=["documentation:check"],
    ),
}


def assert_tool_registry_matches_agent_pack(agent_pack_tools: list[dict]) -> None:
    """Boot-time assertion: TOOL_REGISTRY matches the Agent Pack's tools list.

    The Agent Pack ``medcoder-coding-review/agent_pack.json::tools`` is the
    declarative contract published to clients. The Python
    :data:`TOOL_REGISTRY` is the runtime contract. The pack-declared
    tools MUST be a subset of TOOL_REGISTRY — every tool the pack
    advertises must be dispatchable. TOOL_REGISTRY may carry additional
    tools (Phase 3-D2 Task 3 added 3 agent-backed tools for the simple
    agents code-validation / compliance-guardrail / note-completeness),
    so we no longer require exact equality.

    Args:
        agent_pack_tools: the ``tools`` array from the Agent Pack JSON.

    Raises:
        AssertionError: when a pack-declared tool is missing from TOOL_REGISTRY.
    """
    declared = {t["name"] for t in agent_pack_tools if "name" in t}
    actual = set(TOOL_REGISTRY)
    missing = declared - actual
    if missing:
        raise AssertionError(
            f"agent_pack.json::tools declares {sorted(missing)} "
            f"but TOOL_REGISTRY does not contain them; "
            f"TOOL_REGISTRY has {sorted(actual)}. Update either side."
        )


__all__ = [
    "TOOL_REGISTRY",
    "ToolDescriptor",
    "SearchIcdInput",
    "SearchIcdOutput",
    "VerifyCodeInput",
    "VerifyCodeOutput",
    "GetGuidelinesInput",
    "GetGuidelinesOutput",
    "ExploreCodeInput",
    "ExploreCodeOutput",
    "SearchCodesInput",
    "SearchCodesOutput",
    "GetDifferentiationHintInput",
    "GetDifferentiationHintOutput",
    "RerankCodesInput",
    "RerankCodesOutput",
    "CalibrateConfidenceInput",
    "CalibrateConfidenceOutput",
    "ValidateCodesInput",
    "ValidateCodesOutput",
    "EvaluateComplianceInput",
    "EvaluateComplianceOutput",
    "CheckDocumentationGapsInput",
    "CheckDocumentationGapsOutput",
    "assert_tool_registry_matches_agent_pack",
]
