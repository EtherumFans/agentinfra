"""Agent Pack normalized schema (P1.1).

The single normalized view of an Agent Pack, regardless of which version
of the pack format it was authored in (v1.1 or v1.2).

This module deliberately does NOT raise on format mismatch — it produces
a ``PackLoadResult`` that records errors / warnings but always returns a
normalized object. Callers decide whether ``status == "invalid"`` is fatal.

Two production rules enforced here:
1. **No fake data**: a pack with status ``metadata_only`` is reported as such
   in the registry; the API surfaces it as metadata, not as an executable.
2. **No experimental marked production-ready**: ``production_ready`` is True
   only for ``certified`` packs with full experts + tools wired. ``reference``
   packs (MedCodER family) and ``expert-stub`` packs are ``production_ready``
   False by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


# ── Constants ──

SUPPORTED_FORMAT_VERSIONS: tuple[str, ...] = ("1.1", "1.2")

LEGAL_AGENT_TYPES_V11: tuple[str, ...] = ("certified", "community")
LEGAL_AGENT_TYPES_V12: tuple[str, ...] = (
    "certified",
    "community",
    "reference",         # canonical reference impl (e.g. medcoder-coding-review pre-Phase-3-A)
    "expert-stub",       # atomic expert skeleton (Stage N of a pipeline)
    "internal_engine",   # Phase 3-A: backs a Corti-style product Agent (medcoder-coding-review → Medical Coding Agent)
)
LEGAL_AGENT_TYPES: tuple[str, ...] = tuple(
    sorted(set(LEGAL_AGENT_TYPES_V11) | set(LEGAL_AGENT_TYPES_V12))
)

# Status semantics surfaced to API/UI:
#
# executable     — fully wired, runtime can dispatch this agent
# metadata_only  — on disk but lacks experts/executors (Phase D2 stubs, sample packs)
# invalid        — validation failed; cannot be loaded
# disabled       — explicitly disabled by config/env (out of scope here)
class PackStatus(str, Enum):
    EXECUTABLE = "executable"
    METADATA_ONLY = "metadata_only"
    INVALID = "invalid"


# ── Tool normalization ──


@dataclass
class NormalizedTool:
    """One tool entry, normalized across v1.1 (id/tier/executor_file) and
    v1.2 (ref / stage / type)."""

    raw: dict[str, Any]       # original entry
    id: str                   # tool identifier (always present)
    name: str                 # display name (defaults to id)
    kind: str                 # "legacy" (str ID) | "v1_1" | "v1_2_mcp" | "v1_2_guard" | "v1_2_function"
    ref: str | None = None    # for v1.2: app.icoder.mcp.server:... or guard:fn
    stage: str | None = None  # for v1.2: retrieval / merge / rerank / calibration / pre/post
    tier: int | None = None   # for v1.1: 1 or 2
    executor_file: str | None = None  # for v1.1 community packs
    description: str = ""
    input_schema: dict | None = None   # for v1.2 MCP
    output_schema: dict | None = None  # for v1.2 MCP

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Expert normalization ──


@dataclass
class NormalizedExpert:
    """One expert entry. v1.2 has richer fields; v1.1 has flat id/name."""

    raw: dict[str, Any]
    id: str
    name: str
    role: str = ""
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    model: str = ""
    non_goals: list[str] = field(default_factory=list)
    output_contract: dict | None = None
    timeout_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Pack permissions / output contract / model normalization ──


@dataclass
class NormalizedPack:
    """The single normalized view of any Agent Pack.

    Constructed exclusively via :func:`agent_pack_loader.load_pack`.
    """

    # ── Identity ──
    raw: dict[str, Any]
    source_path: str | None  # filesystem path of pack file, if loaded from disk

    agent_ref: str                    # e.g. "icoder/cdi-review@1.0.0"
    format_version: str
    agent_type: str

    # ── Manifest ──
    name: str
    version: str
    description: str = ""
    category: str = "general"
    icon: str = "Bot"
    tags: list[str] = field(default_factory=list)

    # ── Behavioral fields ──
    system_prompt: str = ""
    publisher_name: str = ""
    publisher_email: str = ""

    experts: list[NormalizedExpert] = field(default_factory=list)
    tools: list[NormalizedTool] = field(default_factory=list)
    code: dict[str, str] = field(default_factory=dict)

    # ── Runtime metadata ──
    model: dict[str, Any] = field(default_factory=dict)
    pipeline: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)
    requirements: dict[str, Any] = field(default_factory=dict)
    llm_capabilities: dict[str, Any] = field(default_factory=dict)
    integrity: dict[str, Any] = field(default_factory=dict)

    # ── v1.2-only fields ──
    non_goals: list[str] = field(default_factory=list)
    output_contract: dict[str, Any] = field(default_factory=dict)
    phi_redaction: str | None = None   # "required" | "optional" | None
    context_required: bool = False
    recorder_required: bool = False
    metrics_required: bool = False
    human_review_required_when: list[str] = field(default_factory=list)
    a2a: dict[str, Any] = field(default_factory=dict)

    # ── Classification (set by loader, not from raw) ──
    status: PackStatus = PackStatus.INVALID
    production_ready: bool = False
    experimental: bool = False
    enabled_by_default: bool = True
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)

    # ── Helpers ──

    @property
    def expert_count(self) -> int:
        return len(self.experts)

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    @property
    def display_name(self) -> str:
        """Best human label: Chinese manifest.name if present, else agent_ref."""
        return self.name or self.agent_ref

    @property
    def tier(self) -> int:
        """Replicated from AgentPackageV1.security_tier semantics so we don't
        have to instantiate both representations. v1.2 packs without
        ``code/`` and without network-requiring tools land at tier 0/1.
        """
        if self.code:
            return 2
        if self.tools:
            network_kw = ("his", "emr", "api", "network", "http", "医保接口")
            write_kw = ("write", "modify", "update", "delete", "insert", "写")
            for t in self.tools:
                desc = (t.description or "").lower()
                stage = (t.stage or "").lower()
                haystack = f"{desc} {stage}"
                if any(kw in haystack for kw in network_kw):
                    return 3
                if any(kw in haystack for kw in write_kw):
                    return 4
            return 1
        return 0

    def to_summary(self) -> dict[str, Any]:
        """API-friendly summary (no raw, no full experts/tools)."""
        return {
            "agent_ref": self.agent_ref,
            "agent_id": _agent_id_from_ref(self.agent_ref),
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "tags": self.tags,
            "agent_type": self.agent_type,
            "format_version": self.format_version,
            "expert_count": self.expert_count,
            "tool_count": self.tool_count,
            "status": self.status.value,
            "production_ready": self.production_ready,
            "experimental": self.experimental,
            "enabled_by_default": self.enabled_by_default,
            "tier": self.tier,
            "min_runtime_version": self.requirements.get("min_runtime_version", ""),
            "phi_redaction": self.phi_redaction,
            "context_required": self.context_required,
            "recorder_required": self.recorder_required,
            "validation_errors": list(self.validation_errors),
            "validation_warnings": list(self.validation_warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        """Full normalized view (drops raw)."""
        d = asdict(self)
        d["status"] = self.status.value
        d.pop("raw", None)
        return d


def _agent_id_from_ref(agent_ref: str) -> str:
    """``icoder/cdi-review@1.0.0`` → ``cdi-review-1.0.0``."""
    if not agent_ref:
        return ""
    ref = agent_ref.split("@", 1)[0]
    if "/" in ref:
        ref = ref.split("/", 1)[1]
    return ref.replace("/", "-")