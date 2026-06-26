"""A2A v0.3 Agent Card schema (SPEC §8).

The Agent Card is the discovery document an agent publishes to make
itself known to other agents and clients. iCoDer exposes it via
``GET /api/icoder/agents/{agent_id}/card`` and bundles a list into
``GET /.well-known/agent.json``.

Per Q-A8 we do NOT use the A2A ``extensions`` field — all iCoDer-
specific data lives under the ``metadata.icoder`` namespace.

Per Q-A6 the ``securitySchemes`` block declares the schemes but does
NOT validate them in Phase 1 (any Authorization header is accepted).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Substructures
# ---------------------------------------------------------------------------


class AgentCapabilities(BaseModel):
    """A2A v0.3 Agent Capabilities (SPEC §8.2)."""

    model_config = ConfigDict(extra="allow")

    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = True
    extensions: list[dict[str, Any]] = Field(default_factory=list)


class AgentSkill(BaseModel):
    """A2A v0.3 Agent Skill (SPEC §8.2).

    Skills are concrete capabilities with input/output JSON schemas.
    More specific than ``capabilities`` — a skill declares its
    contract.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict, alias="inputSchema")
    output_schema: dict[str, Any] = Field(default_factory=dict, alias="outputSchema")
    examples: list[dict[str, Any]] = Field(default_factory=list)

    # Pydantic v2: allow population by either alias or python name
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class SecurityScheme(BaseModel):
    """A2A v0.3 Security Scheme (SPEC §8.2).

    Phase 1 declares the scheme (so clients know what to send) but
    does NOT enforce it. Phase 4 plugs in the validator.
    """

    model_config = ConfigDict(extra="allow")

    type: str
    description: str = ""


# ---------------------------------------------------------------------------
# AgentCard
# ---------------------------------------------------------------------------


class AgentCard(BaseModel):
    """A2A v0.3 Agent Card (SPEC §8.1).

    Required: ``name``, ``description``, ``url``, ``version``,
    ``provider``, ``capabilities``, ``skills``, ``defaultInputModes``,
    ``defaultOutputModes``, ``securitySchemes``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str
    description: str
    url: str

    version: str = "1.0.0"
    provider: str = "iCoDer"
    documentation_url: str = Field(default="", alias="documentationUrl")

    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: list[AgentSkill] = Field(default_factory=list)
    defaultInputModes: list[str] = Field(default_factory=lambda: ["text"])
    defaultOutputModes: list[str] = Field(
        default_factory=lambda: ["application/json"]
    )
    securitySchemes: dict[str, SecurityScheme] = Field(default_factory=dict)

    # iCoDer extensions live under metadata.icoder per Q-A8.
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Discovery list wrapper
# ---------------------------------------------------------------------------


class AgentListResponse(BaseModel):
    """Wrapper for ``GET /.well-known/agent.json`` and ``GET /api/icoder/agents``.

    ``/.well-known/agent.json`` returns this shape per A2A v0.3 spec.
    """

    model_config = ConfigDict(extra="allow")

    agents: list[AgentCard]


# ---------------------------------------------------------------------------
# Phase 1 fixture
# ---------------------------------------------------------------------------
#
# Phase D3 (2026-06-26): the 14-stage ``homepage-coding-review`` cosmetic
# fixture was removed. The canonical Phase 2 standard Agent Card is
# ``medcoder_coding_review_card()`` below — it declares the 5 MedCodER
# stages + 5 MCP tools + 6 non_goals. The legacy 14-stage pipeline is
# preserved only inside the API layer's ``_execute_pipeline_14_stages``
# path for back-compat with the M3-0 report HTML.


def medcoder_coding_review_card(base_url: str = "") -> AgentCard:
    """Canonical MedCodER Coding Review Agent Card (SPEC §8.3).

    Replaces the 14-stage cosmetic ``homepage-coding-review`` agent with a
    standard 5-piece Agent Card:

      - ``system_prompt``: MedCodER 5 阶段行为契约 (AI-assisted 不是 fully automated)
      - ``experts``:    coding-expert (单 Expert, 5 stage 由其编排)
      - ``tools``:      5 MCP tools (search_icd / verify_code /
                        get_differentiation_hint / rerank_codes /
                        calibrate_confidence)
      - ``non_goals``:  6 条硬约束 (不写回 / 不声称自动化 / 不绕过 PHI 等)
      - ``output_contract``: MedicalCodingOutputSchema/v1, extracted_diagnoses 必填

    Per Q-A8 all iCoDer-specific fields live under ``metadata.icoder``.
    Per Q-A6 ``securitySchemes`` declares but does not enforce.
    """
    url = (
        f"{base_url}/api/icoder/agents/medcoder-coding-review/v1/message:send"
        if base_url
        else "/api/icoder/agents/medcoder-coding-review/v1/message:send"
    )
    return AgentCard(
        name="MedCodER Coding Review Agent",
        description=(
            "iCoDer Runtime 标准编码审核 Agent。基于 MedCodER 5 阶段管线 (NAACL 2025) "
            "从中文病历抽取诊断 + 证据, 经 BGE-M3 + FAISS 检索 ICD 候选, "
            "RankGPT 重排, 输出 per-disease ExtractedDiagnosis + 人工复核提示。"
            "AI-assisted coding, 非 fully automated, 低置信度编码必须人工确认。"
        ),
        url=url,
        version="1.0.0",
        provider="iCoDer",
        documentationUrl="/docs/agents/medcoder-coding-review",
        capabilities=AgentCapabilities(
            streaming=False,
            pushNotifications=False,
            stateTransitionHistory=True,
            extensions=[],
        ),
        skills=[
            AgentSkill(
                id="search_icd",
                name="ICD-10-CN / ICD-9-CM-3 检索",
                description=(
                    "Stage 2 — BGE-M3 + FAISS 检索 top-20 候选编码, "
                    "含 similarity_score + chapter metadata。"
                ),
                inputSchema={"type": "object", "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "default": 20}}, "required": ["query"]},
                outputSchema={"type": "array", "items": {"$ref": "icoder/CandidateCode/v1"}},
                examples=[
                    {
                        "input": {"query": "椎体压缩性骨折", "top_k": 5},
                        "output": [{"code": "M48.4", "description": "椎体疲劳性骨折"}],
                    }
                ],
            ),
            AgentSkill(
                id="verify_code",
                name="ICD 编码合规校验",
                description=(
                    "Stage 5 — catalog membership + similarity >= 0.5 + chapter "
                    "metadata 校验, 违规返回 rule_flags 列表 (MR-001/002/003)。"
                ),
                inputSchema={"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
                outputSchema={"$ref": "icoder/CodeVerificationResult/v1"},
                examples=[],
            ),
            AgentSkill(
                id="rerank_codes",
                name="RankGPT-style 重排序",
                description=(
                    "Stage 4 — 给定 disease_text + evidence + candidates (<=30), "
                    "输出 top-5 排序 + per-disease final_confidence。"
                ),
                inputSchema={"type": "object", "properties": {"disease_text": {"type": "string"}, "candidates": {"type": "array"}}, "required": ["disease_text", "candidates"]},
                outputSchema={"$ref": "icoder/RerankResult/v1"},
                examples=[],
            ),
            AgentSkill(
                id="get_differentiation_hint",
                name="编码区分提示 (P0/P1 hints)",
                description=(
                    "Stage 3 merge — 读 coding_differentiation_kb.json (2,090 P0/P1 "
                    "code-pair 决策), 注入 Stage 4 rerank prompt。"
                ),
                inputSchema={"type": "object", "properties": {"candidate_codes": {"type": "array", "items": {"type": "string"}}}, "required": ["candidate_codes"]},
                outputSchema={"type": "array", "items": {"$ref": "icoder/DifferentiationHint/v1"}},
                examples=[],
            ),
            AgentSkill(
                id="calibrate_confidence",
                name="per-disease 置信度校准",
                description=(
                    "Stage 5 校准 — 输入 ExtractedDiagnosis.final_confidence, "
                    "输出 manual_review_required + risk_tier (auto/review/escalate)。"
                ),
                inputSchema={"type": "object", "properties": {"diagnosis": {"type": "object"}}, "required": ["diagnosis"]},
                outputSchema={"$ref": "icoder/CalibrationResult/v1"},
                examples=[],
            ),
            AgentSkill(
                id="medcoder_5_stage_pipeline",
                name="MedCodER 5 阶段管线 (orchestration)",
                description=(
                    "编排 Stage 1-5: extraction -> retrieval -> merge -> rerank -> "
                    "calibration。输出 MedicalCodingOutputSchema 含 extracted_diagnoses。"
                ),
                inputSchema={"type": "object", "properties": {"text": {"type": "string"}, "context_id": {"type": "string"}}, "required": ["text"]},
                outputSchema={"$ref": "icoder/MedicalCodingOutputSchema/v1"},
                examples=[
                    {
                        "input": {"text": "老年患者, 骨质疏松, 椎体压缩性骨折, 行椎体成形术。"},
                        "output": {"primary_diagnosis": {"code": "M80.0"}, "extracted_diagnoses": [], "manual_review_required": True},
                    }
                ],
            ),
        ],
        defaultInputModes=["text"],
        defaultOutputModes=["application/json"],
        securitySchemes={
            "bearer": SecurityScheme(
                type="apiKey",
                description="Phase 4 才校验, Phase 2 接受任意 bearer",
            )
        },
        metadata={
            "icoder": {
                "agent_ref": "icoder/medcoder-coding-review-agent@1.0.0",
                "rule_sets": [
                    "medical_coding",
                    "drg_dip",
                    "audit",
                ],
                "experts": ["coding-expert"],
                "mcp_tools": [
                    "search_icd",
                    "verify_code",
                    "get_differentiation_hint",
                    "rerank_codes",
                    "calibrate_confidence",
                ],
                "pipeline": {
                    "name": "medcoder-5-stage",
                    "stages": ["extraction", "retrieval", "merge", "rerank", "calibration"],
                    "replaces": "homepage-coding-review 14-stage cosmetic (deprecated)",
                },
                "non_goals": [
                    "不直接做最终诊断决策",
                    "不写回 EMR / HIS / 医保",
                    "不评估模型效果",
                    "不声称 fully automated coding",
                    "不绕过 PHI redaction",
                    "不并行运行 14-stage cosmetic trace",
                ],
                "production_writeback_blocked": True,
                "phi_redaction": "required",
                "context_required": True,
                "recorder_required": True,
                "metrics_required": True,
                "output_contract": {
                    "schema_ref": "icoder/MedicalCodingOutputSchema/v1",
                    "extracted_diagnoses_required": True,
                    "human_review_required_when": [
                        "manual_review_required == true",
                        "issues_found non-empty",
                        "primary_diagnosis.code missing",
                        "extracted_diagnoses empty",
                    ],
                },
                "runtime_version": "2.0.0",
            }
        },
    )


__all__ = [
    "AgentCapabilities",
    "AgentCard",
    "AgentListResponse",
    "AgentSkill",
    "SecurityScheme",
    "medcoder_coding_review_card",
]