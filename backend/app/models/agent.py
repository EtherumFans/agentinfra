# iCoDer - Agent Model (iCoDer Agentic Framework equivalent)
"""Agent model — A1B-AE.4 extended with canonical_key + agent_type + aliases.

A1B-AE.4 (2026-07-22) lands the Corti public Agent contract fields on
the Agent model so the same record can serve:

1. Internal iCoDer routes (/api/rest/v1/agent_definitions/*).
2. Corti-style Agent Card surface (/api/v1/agents/{id}/card).
3. Corti-Console-style create-then-customize flow (/api/v1/agents/quick).

The new columns are:

- ``canonical_key`` — snake_case stable key matching Corti public
  convention (dash-form for dual-named pairs per A1B-AE.2 §3.4).
  Unique-where-NOT-NULL (iCoDer-original custom Agents may have NULL).
- ``agent_type`` — Corti public §6 3-value enum:
  ``expert | orchestrator | interviewing-expert``.
- ``aliases`` — JSON list of alternate keys/names this Agent answers
  to. Populated when the legacy underscore-form is retained as an
  alias per A1B-AE.2 §3.4 canonical-name rule.

A ``before_insert`` SQLAlchemy event auto-populates ``canonical_key``
from ``name`` (slugified) when the caller doesn't supply one. This
keeps every row queryable by canonical_key without forcing every
caller to compute the slug.
"""
import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


# A1B-AE.4 — Corti public §6 agentType enum (3 values exhaustive per A1B-AE.1 §2.1)
AGENT_TYPE_VALUES = (
    "expert",                # single-Expert Agent (Corti public default)
    "orchestrator",          # multi-Expert orchestration Agent
    "interviewing-expert",   # real-time interview Agent (Corti interviewing stream)
)

# Default agentType for new custom Agents (iCoDer convention)
AGENT_TYPE_DEFAULT = "orchestrator"


def _slugify_agent_name(name: str) -> str:
    """Convert a display name to a Corti-style canonical key.

    Mirrors Migration 023's slug algorithm exactly. Kept in sync.
    Non-ASCII names fall back to a stable md5-derived key.
    """
    import hashlib
    import re
    if not name:
        return ""
    s = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").lower()
    if not s:
        s = "agent-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return s


class Agent(Base, TimestampMixin):
    """Agent is the backend orchestrator entity that composes multiple Experts.

    iCoDer Agentic Framework: An Agent is a first-class backend entity with:
    - Its own system_prompt (overrides individual Expert prompts)
    - A list of associated Experts it can call (1:N relationship)
    - A2A protocol support (Agent Card discovery)
    - Usage tracking and configuration
    """

    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "id", name="uq_agents_org_id",
        ),
    )

    # Stable public Agent keys (for example ``medical-coding-agent``) are
    # valid identifiers and intentionally exceed the legacy 12-char UUID
    # prefix used by most internal entities.
    id: Mapped[str] = mapped_column(
        String(128), primary_key=True, default=lambda: uuid.uuid4().hex[:12],
    )
    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(64), default="Bot")
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)

    # Expert bindings: 1 Agent can use N Experts
    expert_ids: Mapped[list] = mapped_column(JSON, default=list)  # ["abc123", "def456"]
    default_expert_id: Mapped[str] = mapped_column(String(12), default="")

    # A2A Protocol
    a2a_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Configuration
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {"routing_strategy": "llm_plan"|"fixed_order"|"parallel",
    #  "max_retries": 2,
    #  "confidence_threshold": 0.6}

    # Versioning
    version: Mapped[str] = mapped_column(String(20), default="1.0.0", server_default="1.0.0")
    status: Mapped[str] = mapped_column(String(20), default="draft", server_default="draft", index=True)  # draft | published | archived

    # Metadata
    is_prebuilt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)  # deprecated, use status
    created_by: Mapped[str] = mapped_column(String(64), default="")
    usage_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── A1B-AE.4 — Corti public contract fields ─────────────────────
    canonical_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True,
    )
    agent_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AGENT_TYPE_DEFAULT, server_default=AGENT_TYPE_DEFAULT,
    )
    aliases: Mapped[list] = mapped_column(JSON, default=list)


@event.listens_for(Agent, "before_insert")
def _agent_before_insert(mapper, connection, target):
    """Auto-populate canonical_key from name when caller didn't supply one.

    Keeps every Agent row queryable by canonical_key without forcing
    every caller to compute the slug. The Migration 023 backfill rule
    runs once at upgrade time; this listener covers all future inserts.
    """
    if not target.canonical_key and target.name:
        target.canonical_key = _slugify_agent_name(target.name)
    if target.aliases is None:
        target.aliases = []
    if not target.agent_type:
        target.agent_type = AGENT_TYPE_DEFAULT
