"""Type definitions for iCoDer Python SDK."""

from __future__ import annotations
from typing import Optional, Any, Generic, Literal, TypeVar, TypedDict, cast
from dataclasses import dataclass, field


class AgentHubRuntimeReadiness(TypedDict):
    structural_status: Literal["ready", "blocked"]
    configuration_status: Literal[
        "not_checked",
        "local_ready",
        "configured_not_live_verified",
        "unavailable",
    ]
    run_action_enabled: bool
    reason: str
    runtime_dependencies: list[str]
    external_llm_required: bool
    live_health_verified: bool
    semantic_validation_status: Literal["verified", "not_verified"]
    production_approval_status: Literal["approved", "not_approved"]


class AgentHubCard(TypedDict):
    agent_id: str
    agent_ref: str
    name: str
    execution_path: str
    execution_target: str
    runtime_readiness: AgentHubRuntimeReadiness
    output_contract: dict[str, Any]


class AgentHubResponse(TypedDict):
    agents: list[AgentHubCard]
    total: int
    source: str
    schema_version: Literal["1.3"]


class AgentHubTenantRuntimeReadiness(TypedDict):
    structural_status: Literal["ready", "blocked"]
    configuration_status: Literal["local_ready", "configured", "unavailable"]
    run_action_enabled: bool
    reason: str
    runtime_dependencies: list[str]
    llm_required: bool
    live_health_verified: bool
    connectivity_status: Literal[
        "not_applicable", "not_run", "verified", "expired", "failed"
    ]
    semantic_validation_status: Literal["verified", "not_verified"]
    production_approval_status: Literal["approved", "not_approved"]


class AgentHubTenantReadinessEvidence(TypedDict):
    scope: Literal["tenant_configuration_and_connectivity"]
    selection_mode: Literal["inherit", "pinned"]
    selection_version: int
    deployment_id: str | None
    provider_id: str | None
    configuration_probe_status: str
    canary_checked_at: str | None
    canary_expires_at: str | None


class AgentHubTenantReadinessItem(TypedDict):
    agent_id: str
    execution_target: str
    runtime_readiness: AgentHubTenantRuntimeReadiness
    evidence: AgentHubTenantReadinessEvidence


class AgentHubTenantReadinessResponse(TypedDict):
    agents: list[AgentHubTenantReadinessItem]
    total: int
    generated_at: str
    schema_version: Literal["1.0"]


class AgentCloneResponse(TypedDict):
    project_agent_id: str
    runtime_agent_id: str
    source_runtime_agent_id: str
    source_agent_ref: str
    chat_url: str
    customize_url: str
    run_url: str
    cloned: bool


class A2ALegacyAgentCard(TypedDict):
    name: str
    description: str
    url: str
    version: str
    provider: str
    capabilities: dict[str, Any]
    skills: list[dict[str, Any]]
    defaultInputModes: list[str]
    defaultOutputModes: list[str]
    securitySchemes: dict[str, Any]


def validate_agent_clone_response(value: Any) -> AgentCloneResponse:
    """Validate the public project/source identity boundary of a Hub clone."""
    if not isinstance(value, dict):
        raise ValueError("Malformed Agent clone response.")
    string_fields = (
        "project_agent_id",
        "runtime_agent_id",
        "source_runtime_agent_id",
        "source_agent_ref",
        "chat_url",
        "customize_url",
        "run_url",
    )
    if any(not isinstance(value.get(field), str) or not value[field]
           for field in string_fields):
        raise ValueError("Agent clone response is missing a required identity or URL.")
    if not isinstance(value.get("cloned"), bool):
        raise ValueError("Agent clone response has an invalid cloned flag.")
    if value["runtime_agent_id"] != value["project_agent_id"]:
        raise ValueError(
            "Agent clone response would bypass the project runtime identity."
        )
    return cast(AgentCloneResponse, value)


def validate_agent_hub_response(value: Any) -> AgentHubResponse:
    """Fail closed on malformed current Hub readiness instead of guessing."""
    if not isinstance(value, dict) or value.get("schema_version") != "1.3":
        raise ValueError(
            "Unsupported or malformed Agent Hub response; schema_version 1.3 is required."
        )
    cards = value.get("agents")
    if not isinstance(cards, list):
        raise ValueError("Agent Hub schema 1.3 response is missing agents.")
    configuration_statuses = {
        "not_checked",
        "local_ready",
        "configured_not_live_verified",
        "unavailable",
    }
    for card in cards:
        readiness = card.get("runtime_readiness") if isinstance(card, dict) else None
        if not isinstance(readiness, dict):
            raise ValueError("Agent Hub schema 1.3 card is missing runtime_readiness.")
        valid = (
            readiness.get("structural_status") in {"ready", "blocked"}
            and readiness.get("configuration_status") in configuration_statuses
            and isinstance(readiness.get("run_action_enabled"), bool)
            and isinstance(readiness.get("reason"), str)
            and isinstance(readiness.get("runtime_dependencies"), list)
            and all(
                isinstance(item, str)
                for item in readiness.get("runtime_dependencies", [])
            )
            and isinstance(readiness.get("external_llm_required"), bool)
            and isinstance(readiness.get("live_health_verified"), bool)
            and readiness.get("semantic_validation_status")
            in {"verified", "not_verified"}
            and readiness.get("production_approval_status")
            in {"approved", "not_approved"}
        )
        if not valid:
            raise ValueError(
                "Agent Hub runtime_readiness failed schema 1.3 validation."
            )
        if readiness["run_action_enabled"] and (
            readiness["structural_status"] != "ready"
            or readiness["configuration_status"] in {"not_checked", "unavailable"}
        ):
            raise ValueError(
                "Agent Hub runtime_readiness enables an unavailable Agent."
            )
        if (
            readiness["configuration_status"] == "local_ready"
            and readiness["external_llm_required"] is not False
        ) or (
            readiness["configuration_status"] == "configured_not_live_verified"
            and readiness["external_llm_required"] is not True
        ):
            raise ValueError(
                "Agent Hub runtime_readiness dependency classification is inconsistent."
            )
    return cast(AgentHubResponse, value)


def validate_agent_hub_tenant_readiness_response(
    value: Any,
) -> AgentHubTenantReadinessResponse:
    """Fail closed on malformed tenant-bound configuration/connectivity proof."""
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "1.0"
        or not isinstance(value.get("agents"), list)
        or not isinstance(value.get("total"), int)
        or isinstance(value.get("total"), bool)
        or value["total"] != len(value["agents"])
        or not isinstance(value.get("generated_at"), str)
    ):
        raise ValueError(
            "Unsupported or malformed tenant Agent Hub readiness response; "
            "schema_version 1.0 is required."
        )
    seen: set[str] = set()
    for item in value["agents"]:
        if not isinstance(item, dict):
            raise ValueError("Tenant Agent Hub readiness contains an invalid Agent item.")
        agent_id = item.get("agent_id")
        readiness = item.get("runtime_readiness")
        evidence = item.get("evidence")
        if (
            not isinstance(agent_id, str)
            or not agent_id
            or agent_id in seen
            or not isinstance(item.get("execution_target"), str)
            or not item["execution_target"]
            or not isinstance(readiness, dict)
            or not isinstance(evidence, dict)
        ):
            raise ValueError(
                "Tenant Agent Hub readiness contains an invalid or duplicate Agent item."
            )
        seen.add(agent_id)
        valid = (
            readiness.get("structural_status") in {"ready", "blocked"}
            and readiness.get("configuration_status")
            in {"local_ready", "configured", "unavailable"}
            and isinstance(readiness.get("run_action_enabled"), bool)
            and isinstance(readiness.get("reason"), str)
            and isinstance(readiness.get("runtime_dependencies"), list)
            and all(
                isinstance(dependency, str)
                for dependency in readiness.get("runtime_dependencies", [])
            )
            and isinstance(readiness.get("llm_required"), bool)
            and isinstance(readiness.get("live_health_verified"), bool)
            and readiness.get("connectivity_status")
            in {"not_applicable", "not_run", "verified", "expired", "failed"}
            and readiness.get("semantic_validation_status")
            in {"verified", "not_verified"}
            and readiness.get("production_approval_status")
            in {"approved", "not_approved"}
            and evidence.get("scope") == "tenant_configuration_and_connectivity"
            and evidence.get("selection_mode") in {"inherit", "pinned"}
            and isinstance(evidence.get("selection_version"), int)
            and not isinstance(evidence.get("selection_version"), bool)
            and evidence["selection_version"] >= 0
            and (
                evidence.get("deployment_id") is None
                or isinstance(evidence.get("deployment_id"), str)
            )
            and (
                evidence.get("provider_id") is None
                or isinstance(evidence.get("provider_id"), str)
            )
            and isinstance(evidence.get("configuration_probe_status"), str)
            and (
                evidence.get("canary_checked_at") is None
                or isinstance(evidence.get("canary_checked_at"), str)
            )
            and (
                evidence.get("canary_expires_at") is None
                or isinstance(evidence.get("canary_expires_at"), str)
            )
        )
        if not valid:
            raise ValueError(
                "Tenant Agent Hub runtime readiness failed schema 1.0 validation."
            )
        if (
            readiness["live_health_verified"]
            and readiness["connectivity_status"] != "verified"
        ):
            raise ValueError(
                "Tenant Agent Hub readiness claims live health without verified connectivity."
            )
        if readiness["run_action_enabled"] and (
            readiness["structural_status"] != "ready"
            or readiness["configuration_status"] == "unavailable"
            or readiness["connectivity_status"] == "failed"
        ):
            raise ValueError(
                "Tenant Agent Hub readiness enables an unavailable Agent."
            )
        if (
            readiness["configuration_status"] == "local_ready"
            and readiness["llm_required"] is not False
        ) or (
            readiness["configuration_status"] == "configured"
            and readiness["llm_required"] is not True
        ):
            raise ValueError(
                "Tenant Agent Hub readiness dependency classification is inconsistent."
            )
    return cast(AgentHubTenantReadinessResponse, value)


@dataclass
class User:
    id: str
    username: str
    email: str
    full_name: str = ""
    role: str = "coder"
    department: str = ""
    is_active: bool = True


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: Optional[User] = None


@dataclass
class FactDiagnosis:
    diagnosis: str
    icd10cm_code: Optional[str] = None
    status: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class FactProcedure:
    procedure: str
    icd9cm3_code: Optional[str] = None
    status: Optional[str] = None
    evidence: Optional[str] = None


@dataclass
class FactExtractionResult:
    chief_complaint: Optional[str] = None
    diagnosis_facts: list[FactDiagnosis] = field(default_factory=list)
    procedure_facts: list[FactProcedure] = field(default_factory=list)
    negated_findings: list[dict] = field(default_factory=list)
    timing_facts: dict = field(default_factory=dict)
    documentation_overview: dict = field(default_factory=dict)


@dataclass
class FactItem:
    group: str
    text: str
    value: str = ""


@dataclass
class FactUsageInfo:
    credits_consumed: float = 0


@dataclass
class FactExtractResponse:
    facts: list[FactItem] = field(default_factory=list)
    output_language: str = "zh-CN"
    usage_info: FactUsageInfo = field(default_factory=FactUsageInfo)


@dataclass
class Expert:
    id: str
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    is_published: bool = False


@dataclass
class AgentTemplate:
    id: str
    name: str
    description: str = ""
    category: str = "general"
    system_prompt: Optional[str] = None
    expert_ids: list[str] = field(default_factory=list)


@dataclass
class UsageSummary:
    total_requests: int = 0
    credits_used: float = 0
    avg_response_time_ms: float = 0
    tokens_used: Optional[int] = None


@dataclass
class iCoDerConfig:
    base_url: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    timeout: int = 120
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    max_retries: int = 2
    retry_initial_delay: float = 0.25
    retry_max_delay: float = 2.0
    token_refresh_skew: float = 30.0


T = TypeVar("T")


@dataclass
class HttpResult(Generic[T]):
    """Response value plus protocol metadata such as 202 Location."""

    data: T
    status_code: int
    location: Optional[str] = None
