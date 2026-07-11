"""Agent Display Status Mapper (Phase 5 Track D P0 Gate 1).

Single source of truth for projecting internal engineering fields
(``maturity``, ``production_ready``, ``human_review``, ``runtime_mode``,
``persistence_ready``, etc.) into user-visible display status.

User-visible statuses (PDF §B3):

    preview         可体验，但尚未完成生产质量验证
    available       功能可稳定运行
    controlled_use  可进入真实业务流程，但关键动作需审批
    coming_soon     当前不可运行
    deprecated      不再推荐使用，通常应从 Hub 隐藏

Internal fields are preserved in the API response so engineering
dashboards continue to work, but user-facing UI must render only the
``display_status`` + ``display_badges`` + ``usage_boundaries`` produced
by this module.

Reference: ``reports/phase5_track_d_p0/CDI_P0_AND_AGENT_LABEL_BASELINE.md``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


DisplayStatus = Literal[
    "preview",
    "available",
    "controlled_use",
    "coming_soon",
    "deprecated",
]


BadgeType = Literal[
    "preview",
    "available",
    "controlled_use",
    "coming_soon",
    "deprecated",
    "approval_required",
    "anomaly_confirmation_required",
    "clinical_decision_confirmation_required",
    "internal_only",
]


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------


@dataclass
class DisplayBadge:
    type: BadgeType
    label_zh: str
    label_en: str


@dataclass
class AgentDisplayStatus:
    """Result of projecting an agent's internal state to user-visible status."""

    display_status: DisplayStatus
    display_badges: list[DisplayBadge] = field(default_factory=list)
    usage_boundaries: list[str] = field(default_factory=list)
    # Internal fields preserved for engineering views (NOT rendered on
    # user cards). PDF §B2: 内部治理字段不能删除.
    internal: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "display_status": self.display_status,
            "display_badges": [
                {
                    "type": b.type,
                    "label_zh": b.label_zh,
                    "label_en": b.label_en,
                }
                for b in self.display_badges
            ],
            "usage_boundaries": self.usage_boundaries,
            "internal": self.internal,
        }


# ---------------------------------------------------------------------------
# Input shape — what the mapper needs from the agent pack
# ---------------------------------------------------------------------------


@dataclass
class AgentStateInput:
    """Internal state inputs collected from the agent_pack.json + runtime health.

    Fields are optional with sensible defaults so callers can pass partial
    data; the mapper is conservative (defaults to "coming_soon" or
    "preview" rather than "available").
    """

    maturity: str = ""  # prototype|beta|validated|production|deprecated|metadata-only|stub|mvp|runnable
    production_ready: bool = False
    quality_validated: bool = False
    runtime_mode: str = ""  # stub|mock|real|degraded|unavailable
    persistence_ready: bool = False
    integration_ready: bool = False
    human_review_policy: str = ""  # none|optional|required
    availability: str = ""  # hidden|coming_soon|preview|available|controlled_use
    deprecated: bool = False
    hidden_from_hub: bool = False
    runnable: bool = False  # has real run endpoint
    has_backend_provider: bool = False  # backend_provider wired
    agent_type: str = ""  # certified|expert-stub|internal_engine
    # Category hint for action-level rules (e.g. "medical-coding" vs "cDI")
    category: str = ""


# ---------------------------------------------------------------------------
# Label catalog (single source for zh/en strings)
# ---------------------------------------------------------------------------


_LABELS: dict[BadgeType, tuple[str, str]] = {
    "preview": ("预览版", "Preview"),
    "available": ("可用", "Available"),
    "controlled_use": ("受控使用", "Controlled use"),
    "coming_soon": ("即将推出", "Coming soon"),
    "deprecated": ("已停用", "Deprecated"),
    "approval_required": ("发送前需审批", "Approval required before send"),
    "anomaly_confirmation_required": ("异常项需确认", "Anomalies require confirmation"),
    "clinical_decision_confirmation_required": (
        "用于临床决策时需确认",
        "Confirmation required for clinical decisions",
    ),
    "internal_only": ("仅用于内部审核", "Internal review only"),
}


def _badge(t: BadgeType) -> DisplayBadge:
    zh, en = _LABELS[t]
    return DisplayBadge(type=t, label_zh=zh, label_en=en)


# ---------------------------------------------------------------------------
# Category-specific action-level policies (PDF §B4)
# ---------------------------------------------------------------------------


# Per-category secondary badge (in addition to display_status badge).
# This replaces the old "Human review required" blanket tag with
# action-level guidance tied to what the agent actually does.
_CATEGORY_POLICY: dict[str, BadgeType] = {
    "cdi": "approval_required",
    "clinical-documentation": "approval_required",
    "clinical-documentation-improvement": "approval_required",
    "medical-coding": "approval_required",  # writeback gating
    "code-validation": "anomaly_confirmation_required",
    "compliance": "approval_required",
    "evidence-extraction": "clinical_decision_confirmation_required",
    "note-completeness": "anomaly_confirmation_required",
    "drg": "approval_required",
    "drg-dip": "approval_required",
    "charge-compliance": "approval_required",
    "insurance-audit": "approval_required",
}


def _category_secondary_badge(category: str) -> DisplayBadge | None:
    """Return the action-level badge for an agent category, or None."""

    bt = _CATEGORY_POLICY.get(category)
    if bt is None:
        return None
    return _badge(bt)


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------


def derive_agent_display_status(
    state: AgentStateInput,
) -> AgentDisplayStatus:
    """Derive the user-visible display status from internal state.

    PDF §B5 invariants:
      - runtime_mode=stub/mock → never "available"
      - production_ready=false → never "available"
      - quality_validated=false → never hide the validation state
      - persistence_ready=false workflow agent → never "controlled_use"
      - deprecated → "deprecated" + hidden from hub
      - Coming-soom rule: no runnable path + no real provider → "coming_soon"
    """

    internal = {
        "maturity": state.maturity,
        "production_ready": state.production_ready,
        "quality_validated": state.quality_validated,
        "runtime_mode": state.runtime_mode,
        "persistence_ready": state.persistence_ready,
        "integration_ready": state.integration_ready,
        "human_review_policy": state.human_review_policy,
        "availability": state.availability,
        "deprecated": state.deprecated,
        "hidden_from_hub": state.hidden_from_hub,
        "runnable": state.runnable,
        "has_backend_provider": state.has_backend_provider,
    }

    # 1. Deprecated always wins
    if state.deprecated or state.maturity == "deprecated":
        return AgentDisplayStatus(
            display_status="deprecated",
            display_badges=[_badge("deprecated")],
            usage_boundaries=[
                "已停用，不再推荐使用",
                "Deprecated; use the replacement agent instead.",
            ],
            internal=internal,
        )

    # 2. Stub packs (expert-stub agent_type) — never user-visible as available
    if state.agent_type == "expert-stub" or state.maturity == "stub":
        return AgentDisplayStatus(
            display_status="coming_soon",
            display_badges=[_badge("coming_soon")],
            usage_boundaries=[
                "尚未提供运行能力",
                "Runtime not yet implemented.",
            ],
            internal=internal,
        )

    # 3. internal_engine (e.g. medcoder-coding-review) — internal-only
    if state.agent_type == "internal_engine" or state.maturity == "internal":
        return AgentDisplayStatus(
            display_status="deprecated",
            display_badges=[_badge("internal_only")],
            usage_boundaries=[
                "仅用于内部审核，不对外暴露",
                "Internal-only; not exposed to end users.",
            ],
            internal=internal,
        )

    # 4. Not runnable + no backend provider → coming_soon
    if not state.runnable and not state.has_backend_provider:
        return AgentDisplayStatus(
            display_status="coming_soon",
            display_badges=[_badge("coming_soon")],
            usage_boundaries=[
                "尚未提供运行能力",
                "Runtime not yet implemented.",
            ],
            internal=internal,
        )

    # 5. Runnable but runtime_mode is stub/mock/unavailable → coming_soon
    rm = (state.runtime_mode or "").lower()
    if rm in {"stub", "mock", "unavailable"}:
        return AgentDisplayStatus(
            display_status="coming_soon",
            display_badges=[_badge("coming_soon")],
            usage_boundaries=[
                "尚未提供真实运行能力",
                f"Runtime mode '{rm or 'unknown'}' is not real.",
            ],
            internal=internal,
        )

    # 6. production_ready=false OR quality_validated=false → preview
    #    (PDF §B6: CDI stays preview until medical quality validation done)
    if not state.production_ready or not state.quality_validated:
        badges: list[DisplayBadge] = [_badge("preview")]
        secondary = _category_secondary_badge(state.category)
        if secondary is not None:
            badges.append(secondary)
        boundaries: list[str] = [
            "尚未完成生产质量验证",
            "Not yet validated for production use.",
        ]
        # Category-specific extra boundary text
        if state.category in {"cdi", "clinical-documentation", "clinical-documentation-improvement"}:
            boundaries.extend([
                "不会自动修改病历",
                "Does not auto-modify clinical charts.",
            ])
        # Cap at 2 badges per PDF §B3 ("每张卡片最多显示两个主要 Badge")
        badges = badges[:2]
        return AgentDisplayStatus(
            display_status="preview",
            display_badges=badges,
            usage_boundaries=boundaries,
            internal=internal,
        )

    # 7. production_ready=true + quality_validated=true + persistence_ready=true
    #    → controlled_use if integration_ready=false, else available
    if not state.persistence_ready:
        # Workflow agent without persistence → still preview
        return AgentDisplayStatus(
            display_status="preview",
            display_badges=[_badge("preview")],
            usage_boundaries=[
                "持久化尚未完成，无法恢复状态",
                "Persistence incomplete; state cannot be restored.",
            ],
            internal=internal,
        )

    if not state.integration_ready:
        return AgentDisplayStatus(
            display_status="controlled_use",
            display_badges=[_badge("controlled_use"), _badge("approval_required")],
            usage_boundaries=[
                "可进入真实业务流程，但关键动作需审批",
                "Usable in real workflows; key actions require approval.",
            ],
            internal=internal,
        )

    # 8. Fully validated + integrated → available
    return AgentDisplayStatus(
        display_status="available",
        display_badges=[_badge("available")],
        usage_boundaries=[
            "功能可稳定运行",
            "Function runs stably.",
        ],
        internal=internal,
    )


# ---------------------------------------------------------------------------
# Convenience: project a raw agent_pack.json + runtime hint
# ---------------------------------------------------------------------------


def project_pack_to_display_status(
    pack: dict,
    *,
    runtime_mode_hint: str = "",
    persistence_ready_hint: bool = False,
    integration_ready_hint: bool = False,
    quality_validated_hint: bool = False,
) -> AgentDisplayStatus:
    """Project a raw agent_pack.json dict to a display status.

    ``runtime_mode_hint`` lets callers pass runtime health info from a
    separate source (e.g. a runtime registry). If omitted, we infer
    from the pack itself.
    """

    manifest = pack.get("manifest") or {}
    maturity = manifest.get("maturity", "")
    category = manifest.get("category", "")
    human_review = manifest.get("human_review", "")
    availability = manifest.get("availability", "")
    has_backend_provider = "backend_provider" in pack
    runnable = bool(pack.get("a2a", {}).get("endpoint")) or has_backend_provider
    agent_type = pack.get("agent_type", "")
    deprecated = bool(pack.get("deprecated", False))
    hidden = bool(manifest.get("hidden_from_hub", False))

    # Runtime mode inference
    runtime_mode = runtime_mode_hint
    if not runtime_mode:
        if maturity in {"stub", "metadata-only"}:
            runtime_mode = "stub"
        elif has_backend_provider or runnable:
            runtime_mode = "real"
        else:
            runtime_mode = "unavailable"

    state = AgentStateInput(
        maturity=maturity,
        production_ready=bool(manifest.get("production_ready", False)),
        quality_validated=quality_validated_hint,
        runtime_mode=runtime_mode,
        persistence_ready=persistence_ready_hint,
        integration_ready=integration_ready_hint,
        human_review_policy=human_review,
        availability=availability,
        deprecated=deprecated,
        hidden_from_hub=hidden,
        runnable=runnable,
        has_backend_provider=has_backend_provider,
        agent_type=agent_type,
        category=category,
    )
    return derive_agent_display_status(state)


__all__ = [
    "DisplayStatus",
    "BadgeType",
    "DisplayBadge",
    "AgentDisplayStatus",
    "AgentStateInput",
    "derive_agent_display_status",
    "project_pack_to_display_status",
]
