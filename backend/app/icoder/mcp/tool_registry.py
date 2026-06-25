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
    """Input for ``verify_code`` — catalog membership + chapter metadata."""

    code: str = Field(
        ..., min_length=1, max_length=20,
        description="ICD-10 code (e.g. 'I50.900') to verify.",
    )


class VerifyCodeOutput(BaseModel):
    """Output for ``verify_code``."""

    code: str
    in_catalog: bool = Field(description="True iff the code is in icd10cn_code_catalog.")
    chapter: str = Field(default="", description="ICD-10 chapter heading (empty if unknown).")
    name: str = Field(default="", description="Canonical Chinese name (empty if unknown).")
    aliases: list[str] = Field(default_factory=list)


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


# ── Tool descriptor ──────────────────────────────────────────────


@dataclass
class ToolDescriptor:
    """One MCP tool declaration.

    The ``handler_ref`` is a dotted-path string (``module:func``) that
    :func:`app.icoder.mcp.server.resolve_handler` turns into a callable
    at dispatch time. Lazy resolution keeps the registry importable
    even if a handler's module has heavy dependencies.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler_ref: str
    stage: str = ""

    @staticmethod
    def from_pydantic(
        name: str,
        description: str,
        *,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        handler_ref: str,
        stage: str = "",
    ) -> "ToolDescriptor":
        return ToolDescriptor(
            name=name,
            description=description,
            input_schema=input_model.model_json_schema(),
            output_schema=output_model.model_json_schema(),
            handler_ref=handler_ref,
            stage=stage,
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
        "验证 ICD-10 编码是否在 icd10cn_code_catalog (37,897 码) 中,并返回 chapter + 中文名 + 同义词。",
        input_model=VerifyCodeInput,
        output_model=VerifyCodeOutput,
        handler_ref="app.icoder.mcp.handlers.verify_code:handle",
        stage="compliance",
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
}


def assert_tool_registry_matches_agent_pack(agent_pack_tools: list[dict]) -> None:
    """Boot-time assertion: TOOL_REGISTRY matches the Agent Pack's tools list.

    The Agent Pack ``medcoder-coding-review/agent_pack.json::tools`` is the
    declarative contract published to clients. The Python
    :data:`TOOL_REGISTRY` is the runtime contract. They MUST agree on tool
    names — any mismatch fails fast at server boot, before serving traffic.

    Args:
        agent_pack_tools: the ``tools`` array from the Agent Pack JSON.

    Raises:
        AssertionError: when the two name sets differ.
    """
    declared = {t["name"] for t in agent_pack_tools if "name" in t}
    actual = set(TOOL_REGISTRY)
    if declared != actual:
        raise AssertionError(
            f"MCP TOOL_REGISTRY ({sorted(actual)}) != agent_pack.json::tools "
            f"({sorted(declared)}); update either side to match."
        )


__all__ = [
    "TOOL_REGISTRY",
    "ToolDescriptor",
    "SearchIcdInput",
    "SearchIcdOutput",
    "VerifyCodeInput",
    "VerifyCodeOutput",
    "GetDifferentiationHintInput",
    "GetDifferentiationHintOutput",
    "RerankCodesInput",
    "RerankCodesOutput",
    "CalibrateConfidenceInput",
    "CalibrateConfidenceOutput",
    "assert_tool_registry_matches_agent_pack",
]