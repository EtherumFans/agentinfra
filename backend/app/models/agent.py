# iCoDer - Agent Model (iCoDer Agentic Framework equivalent)
from sqlalchemy import String, Boolean, Integer, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


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
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft | published | archived

    # Metadata
    is_prebuilt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)  # deprecated, use status
    created_by: Mapped[str] = mapped_column(String(64), default="")
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
