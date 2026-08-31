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

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from pydantic import BaseModel, ConfigDict, Field

from icoder_runtime.core.agent_execution_paths import (
    DEDICATED_AGENT_EXECUTION_PATHS,
)


def _official_agent_pack(pack_dir: str) -> dict[str, Any]:
    """Load discovery metadata from the same Pack used by Hub and Run."""
    path = (
        Path(__file__).resolve().parents[4]
        / "official_agents"
        / pack_dir
        / "agent_pack.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))

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


def agent_card_from_pack(pack: dict[str, Any], base_url: str = "") -> AgentCard:
    """Build a discovery card from an executable official Agent Pack."""
    manifest = pack.get("manifest") or {}
    agent_ref = str(pack.get("agent_ref") or "")
    agent_id = agent_ref.rsplit("/", 1)[-1].split("@", 1)[0]
    version = str(manifest.get("version") or "1.0.0")
    dedicated = DEDICATED_AGENT_EXECUTION_PATHS.get(agent_id)
    execution_path = (
        dedicated["execution_path"] if dedicated else "provider_registry"
    )

    execution_target = (
        dedicated["execution_target"]
        if dedicated
        else str(pack.get("backend_provider") or "")
    )
    a2a = pack.get("a2a") or {}
    endpoint = str(a2a.get("endpoint") or "")
    if not endpoint:
        endpoint = f"/api/icoder/agents/{agent_id}/v1/message:send"
    url = f"{base_url.rstrip('/')}{endpoint}" if base_url else endpoint
    skills: list[AgentSkill] = []
    for index, tool in enumerate(pack.get("tools") or []):
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or f"skill-{index + 1}")
        skills.append(AgentSkill(
            id=name,
            name=name,
            description=str(tool.get("description") or "Official iCoDer capability"),
            inputSchema=dict(tool.get("input_schema") or {}),
            outputSchema=dict(tool.get("output_schema") or {}),
            examples=[],
        ))
    if not skills:
        output_contract = pack.get("output_contract") or {}
        skills.append(AgentSkill(
            id="run",
            name="Run agent",
            description=str(manifest.get("description") or "Execute this Agent."),
            inputSchema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            outputSchema={
                "$ref": str(output_contract.get("schema_ref") or "icoder/OutputContract/v1")
            },
            examples=[],
        ))
    return AgentCard(
        name=str(manifest.get("name") or agent_id),
        description=str(manifest.get("description") or ""),
        url=url,
        version=version,
        provider="iCoDer",
        documentationUrl=f"/docs/agents/{agent_id}",
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            stateTransitionHistory=True,
        ),
        skills=skills,
        securitySchemes={
            "oauth2": SecurityScheme(
                type="oauth2",
                description="Use an iCoDer bearer token or API client credential.",
            )
        },
        metadata={
            "icoder": {
                "agent_id": agent_id,
                "agent_ref": agent_ref,
                "backend_provider": pack.get("backend_provider", ""),
                "execution_path": execution_path,
                "execution_target": execution_target,
                "phi_redaction": pack.get("phi_redaction", "required"),
                "maturity": manifest.get("maturity", ""),
                "human_review": manifest.get("human_review", "required"),
                "production_ready": bool(manifest.get("production_ready", False)),
                "output_contract": dict(pack.get("output_contract") or {}),
                "production_writeback_blocked": bool(
                    (pack.get("permissions") or {}).get(
                        "production_writeback_blocked", True
                    )
                ),
            }
        },
    )


def resolve_v1_agent_card_base_url(request_base_url: str) -> str:
    """Use the configured hosted origin in deployments, never a cloud Host header."""

    from app.config import settings

    configured = str(settings.ICODER_HOSTED_URL or "").strip().rstrip("/")
    if configured:
        parsed = urlparse(configured)
        if (
            parsed.scheme in {"http", "https"}
            and parsed.netloc
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        ):
            return configured
        if settings.ICODER_DEPLOYMENT_MODE == "cloud":
            raise ValueError("ICODER_HOSTED_URL is not a safe public origin")
    return str(request_base_url).rstrip("/")


def project_v1_agent_card(
    card: AgentCard,
    *,
    base_url: str,
    agent_id: str,
) -> dict[str, Any]:
    """Project the internal card into the current A2A 1.0 discovery shape."""

    base = resolve_v1_agent_card_base_url(base_url)
    encoded_agent_id = quote(agent_id, safe="")
    agent_base = f"{base}/api/v2/agentic/agents/{encoded_agent_id}"

    def media_types(values: list[str] | None, fallback: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values or fallback:
            candidate = str(value).strip()
            if candidate == "text":
                candidate = "text/plain"
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized or list(fallback)

    default_inputs = media_types(card.defaultInputModes, ["text/plain"])
    default_outputs = media_types(card.defaultOutputModes, ["application/json"])
    skills: list[dict[str, Any]] = []
    for skill in card.skills:
        raw_examples = list(skill.examples or [])
        tags = [
            str(value) for value in (getattr(skill, "tags", None) or ["a2a"])
            if str(value).strip()
        ][:32]
        skills.append({
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "tags": tags or ["a2a"],
            "examples": [
                value if isinstance(value, str) else json.dumps(
                    value, ensure_ascii=False, sort_keys=True,
                )
                for value in raw_examples[:16]
            ],
            "inputModes": media_types(
                getattr(skill, "inputModes", None), default_inputs,
            ),
            "outputModes": media_types(
                getattr(skill, "outputModes", None), default_outputs,
            ),
        })
    documentation_url = str(card.documentation_url or "").strip()
    if documentation_url.startswith("/"):
        documentation_url = f"{base}{documentation_url}"
    projected: dict[str, Any] = {
        "name": card.name,
        "description": card.description,
        "supportedInterfaces": [
            {
                "url": f"{agent_base}/a2a",
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            },
            {
                "url": agent_base,
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
        ],
        "provider": {"url": base, "organization": "iCoDer"},
        "version": card.version,
        "capabilities": {
            "streaming": bool(card.capabilities.streaming),
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
        "securitySchemes": {
            "bearerAuth": {
                "httpAuthSecurityScheme": {
                    "description": "iCoDer OAuth2/JWT bearer token",
                    "scheme": "Bearer",
                    "bearerFormat": "JWT",
                }
            }
        },
        "securityRequirements": [
            {"schemes": {"bearerAuth": {"list": []}}}
        ],
        "defaultInputModes": default_inputs,
        "defaultOutputModes": default_outputs,
        "skills": skills,
    }
    if documentation_url:
        projected["documentationUrl"] = documentation_url
    return projected


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
        name="MedCodER 编码审核智能体",
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
            streaming=True,
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


def medical_coding_agent_card(base_url: str = "") -> AgentCard:
    """Canonical Medical Coding Agent Card (Phase 3-B1, 2026-07-04).

    This is the user-facing Corti-style Medical Coding Agent
    (``icoder/medical-coding-agent@2.0.0``). It declares the Corti 7-step
    workflow + 8-field output contract (``MedicalCodingAgentOutputV2``).
    Internally it delegates to the MedCodER 5-stage pipeline via the
    ``coding-expert`` expert_id (wired to 4 D2 expert packs).

    Phase 3-B1 Section D: this card factory enables A2A discovery to
    return Medical Coding Agent (previously only medcoder-coding-review
    was returned). The run path is A2A message:send → InboundHandler →
    Planner → Delegator → coding-expert (4 D2 packs) → Aggregator →
    v1→v2 projection → 8-field response.

    Runnable launch candidate: production_ready=false, human_review=required.
    """
    pack = _official_agent_pack("medical_coding")
    contract = pack.get("output_contract") or {}
    schema_ref = str(
        contract.get("schema_ref") or "icoder/MedicalCodingAgentOutputV2/v1"
    )
    url = (
        f"{base_url}/api/icoder/agents/medical-coding-agent/v1/message:send"
        if base_url
        else "/api/icoder/agents/medical-coding-agent/v1/message:send"
    )
    return AgentCard(
        name="医学编码智能体",
        description=(
            "iCoDer 官方医学编码 Agent (controlled rollout)。基于病历证据生成 "
            "ICD-10-CN 诊断编码与 ICD-9-CM-3 手术操作编码建议, 输出 Corti-style "
            "8-field 结构化结果 (encounter_summary / documentation_analysis / "
            "code_assignment / documentation_gaps / uncodable_items / "
            "validation_summary / human_review / trace_refs)。AI-assisted coding "
            "— 不替代编码员, 不自动写回, 不 upcoding, 不推断未记录的诊断/手术。"
            "Runnable launch candidate: production_ready=false, human_review=required。"
        ),
        url=url,
        version="2.0.0",
        provider="iCoDer",
        documentationUrl="/docs/agents/medical-coding-agent",
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            stateTransitionHistory=True,
            extensions=[],
        ),
        skills=[
            AgentSkill(
                id="corti_7_step_workflow",
                name="Corti 7-step Medical Coding Workflow",
                description=(
                    "Synthesize Encounter → Extract Evidence → Search Candidates → "
                    "Assign Codes → Validate Coding → Identify Documentation Gaps → "
                    "Generate Review Summary. Outputs 8-field MedicalCodingAgentOutputV2."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "context_id": {"type": "string"},
                    },
                    "required": ["text"],
                },
                outputSchema={"$ref": schema_ref},
                examples=[],
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
                "agent_ref": "icoder/medical-coding-agent@2.0.0",
                "rule_sets": ["medical_coding"],
                "experts": ["coding-expert"],
                "mcp_tools": [
                    "search_icd",
                    "verify_code",
                    "get_differentiation_hint",
                    "rerank_codes",
                    "calibrate_confidence",
                ],
                "internal_engine": {
                    "name": "MedCodER 5-stage pipeline",
                    "agent_ref": "icoder/medcoder-coding-review-agent@1.0.0",
                    "stages": [
                        "extraction",
                        "retrieval",
                        "merge",
                        "rerank",
                        "calibration",
                    ],
                },
                "non_goals": [
                    "不替代编码员 — 所有编码建议需经编码员人工确认",
                    "不 upcoding — 不优先选择高补偿编码",
                    "不推断未记录的诊断 / 手术 (evidence-first)",
                    "不写回 EMR / HIS / 医保结算系统",
                    "不声称 fully automated coding",
                    "不绕过 PHI redaction",
                    "不输出 F1 / 模型效果指标给最终用户",
                ],
                "production_writeback_blocked": True,
                "phi_redaction": "required",
                "context_required": True,
                "recorder_required": True,
                "metrics_required": True,
                "no_upcoding": True,
                "no_inference": True,
                "evidence_required": True,
                "output_contract": {
                    "schema_ref": schema_ref,
                    "required_fields": [
                        "encounter_summary",
                        "documentation_analysis",
                        "code_assignment",
                        "documentation_gaps",
                        "uncodable_items",
                        "validation_summary",
                        "human_review",
                        "trace_refs",
                    ],
                    "human_review_required_when": [
                        "manual_review_required == true",
                        "issues_found non-empty",
                        "primary_diagnosis.code missing",
                        "documentation_gaps non-empty",
                        "uncodable_items non-empty",
                        "review_conclusion == FAIL",
                    ],
                },
                "maturity": "runnable",
                "production_ready": False,
                "human_review": "required",
                "execution_path": "dedicated.medical_coding_dispatcher",
                "execution_target": "icoder.medical-coding-runtime.v2",
                "runtime_version": "2.0.0",
            }
        },
    )


# ---------------------------------------------------------------------------
# Phase 3-D1 Task 5 — 3 simple runnable agents (code-validation /
# compliance-guardrail / note-completeness). These bypass the orchestrator
# and call the agent's run() function directly. See app/main.py
# _SimpleAgentDispatchHandler.
# ---------------------------------------------------------------------------


def code_validation_agent_card(base_url: str = "") -> AgentCard:
    """Code Validation Agent Card — governed catalog + optional LLM review."""
    pack = _official_agent_pack("code-validation")
    contract = pack["output_contract"]
    manifest = pack.get("manifest") or {}
    url = (
        f"{base_url}/api/icoder/agents/code-validation-agent/v1/message:send"
        if base_url
        else "/api/icoder/agents/code-validation-agent/v1/message:send"
    )
    return AgentCard(
        name="编码校验智能体",
        description=str(manifest.get("description") or "治理目录编码校验智能体"),
        url=url,
        version=str(manifest.get("version") or "1.0.0"),
        provider="iCoDer",
        documentationUrl="/docs/agents/code-validation-agent",
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            stateTransitionHistory=True,
            extensions=[],
        ),
        skills=[
            AgentSkill(
                id="validate_coding_set",
                name="Validate Coding Set",
                description=(
                    "Validate exact membership and assignability against hash-pinned "
                    "local ICD-10-CN / ICD-9-CM-3 development catalogs. Optional "
                    "LLM/tool review may add human-review-only cross-code observations."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "coding_set": {"type": "object"},
                        "encounter_text": {"type": "string"},
                    },
                },
                outputSchema={"$ref": contract["schema_ref"]},
                examples=[],
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
                "agent_ref": pack["agent_ref"],
                "execution_path": "dedicated.governed_code_validation",
                "execution_target": "icoder.governed-code-validation.v1",
                "catalog_assets": [
                    "cn.icd10cn.catalog",
                    "cn.icd9cm3.catalog",
                ],
                "experts": [
                    "governed-local-catalog",
                    "optional-llm-with-tools",
                ],
                "mcp_tools": [
                    "verify_code",
                    "get_guidelines",
                    "explore_code",
                    "search_codes",
                ],
                "non_goals": list(pack.get("non_goals") or []),
                "production_writeback_blocked": True,
                "phi_redaction": "required",
                "maturity": manifest.get("maturity", ""),
                "production_ready": bool(manifest.get("production_ready", False)),
                "human_review": manifest.get("human_review", "required"),
                "output_contract": dict(contract),
                "runtime_version": "2.0.0",
            }
        },
    )


def compliance_guardrail_agent_card(base_url: str = "") -> AgentCard:
    """Compliance Guardrail Agent Card — RuleEngine + guardrail heuristics."""
    pack = _official_agent_pack("compliance-guardrail")
    contract = pack["output_contract"]
    manifest = pack.get("manifest") or {}
    url = (
        f"{base_url}/api/icoder/agents/compliance-guardrail-agent/v1/message:send"
        if base_url
        else "/api/icoder/agents/compliance-guardrail-agent/v1/message:send"
    )
    return AgentCard(
        name="合规护栏智能体",
        description=(
            "iCoDer 合规护栏 Agent — 在提交医保结算清单前，按 MedicalCodingRuleSet + "
            "合规护栏启发式 (主诊断非空 / no upcoding / 手术-诊断一致 / DRG 就绪) 评估编码集。"
            "纯确定性，无 LLM。"
        ),
        url=url,
        version=str(manifest.get("version") or "1.0.0"),
        provider="iCoDer",
        documentationUrl="/docs/agents/compliance-guardrail-agent",
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            stateTransitionHistory=True,
            extensions=[],
        ),
        skills=[
            AgentSkill(
                id="evaluate_compliance",
                name="Evaluate Compliance",
                description=(
                    "Run MedicalCodingRuleSet + compliance guardrail heuristics "
                    "(CG-001 primary dx present / CG-002 no upcoding / "
                    "CG-003 procedure-dx consistency / CG-004 DRG readiness). "
                    "Returns review_conclusion + issues_found + drg_suggestion + "
                    "compliance_checks."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "coding_set": {"type": "object"},
                        "encounter_text": {"type": "string"},
                    },
                },
                outputSchema={"$ref": contract["schema_ref"]},
                examples=[],
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
                "agent_ref": pack["agent_ref"],
                "rule_sets": ["medical_coding"],
                "experts": ["rule-engine"],
                "mcp_tools": ["evaluate_compliance"],
                "non_goals": [
                    "不调用 LLM",
                    "不修改编码集 — 只评估",
                    "不写回医保结算",
                    "不分配 DRG 分组 — 仅输出 drg_suggestion",
                ],
                "production_writeback_blocked": True,
                "no_upcoding": True,
                "phi_redaction": "required",
                "maturity": manifest.get("maturity", ""),
                "production_ready": bool(manifest.get("production_ready", False)),
                "human_review": manifest.get("human_review", "required"),
                "output_contract": dict(contract),
                "runtime_version": "2.0.0",
            }
        },
    )


def note_completeness_agent_card(base_url: str = "") -> AgentCard:
    """Note Completeness Agent Card — regex-based section detector."""
    pack = _official_agent_pack("note-completeness")
    contract = pack["output_contract"]
    manifest = pack.get("manifest") or {}
    url = (
        f"{base_url}/api/icoder/agents/note-completeness-agent/v1/message:send"
        if base_url
        else "/api/icoder/agents/note-completeness-agent/v1/message:send"
    )
    return AgentCard(
        name="病历完整性智能体",
        description=(
            "iCoDer 病历完整性 Agent — 按《病历书写基本规范》检查入院记录的必填章节 "
            "(主诉/现病史/既往史/体格检查/辅助检查/诊断/治疗经过 + 手术记录 for surgical cases)。"
            "输出缺失章节列表 + completeness_score。纯确定性 regex 检测，无 LLM。"
        ),
        url=url,
        version=str(manifest.get("version") or "1.0.0"),
        provider="iCoDer",
        documentationUrl="/docs/agents/note-completeness-agent",
        capabilities=AgentCapabilities(
            streaming=True,
            pushNotifications=False,
            stateTransitionHistory=True,
            extensions=[],
        ),
        skills=[
            AgentSkill(
                id="check_documentation_gaps",
                name="Check Documentation Gaps",
                description=(
                    "Detect missing required sections in an EMR note per "
                    "《病历书写基本规范》. Returns documentation_gaps + "
                    "completeness_score + missing_sections + review_conclusion."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"emr_text": {"type": "string"}},
                    "required": ["emr_text"],
                },
                outputSchema={"$ref": contract["schema_ref"]},
                examples=[],
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
                "agent_ref": pack["agent_ref"],
                "rule_sets": ["documentation_completeness"],
                "experts": ["section-detector"],
                "mcp_tools": ["check_documentation_gaps"],
                "non_goals": [
                    "不调用 LLM — 纯 regex 检测",
                    "不修改病历 — 只评估",
                    "不写回 EMR",
                    "不评估编码正确性",
                ],
                "production_writeback_blocked": True,
                "phi_redaction": "required",
                "maturity": manifest.get("maturity", ""),
                "production_ready": bool(manifest.get("production_ready", False)),
                "human_review": manifest.get("human_review", "required"),
                "output_contract": dict(contract),
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
    "agent_card_from_pack",
    "project_v1_agent_card",
    "resolve_v1_agent_card_base_url",
    "medcoder_coding_review_card",
    "medical_coding_agent_card",
    "code_validation_agent_card",
    "compliance_guardrail_agent_card",
    "note_completeness_agent_card",
]
