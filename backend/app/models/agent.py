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
"""
from sqlalchemy import String, Boolean, Integer, Text, JSON, ForeignKey
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


class Agent(Base, TimestampMixin):
    """Agent is the backend orchestrator entity that composes multiple Experts.

    iCoDer Agentic Framework: An Agent is a first-class backend entity with:
    - Its own system_prompt (overrides individual Expert prompts)
    - A list of associated Experts it can call (1:N relationship)
    - A2A protocol support (Agent Card discovery)
    - Usage tracking and configuration
    """

    __tablename__ = "agents"

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

