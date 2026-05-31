# iCoDer - Expert & MCP Server Models
from sqlalchemy import String, Boolean, Integer, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class Expert(Base, TimestampMixin):
    __tablename__ = "experts"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(64), default="Bot")
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    is_prebuilt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    # Registry fields
    capabilities: Mapped[list] = mapped_column(JSON, default=list)  # ["diagnosis_coding", "procedure_coding"]
    input_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # JSON Schema for input
    output_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # JSON Schema for output
    tags: Mapped[list] = mapped_column(JSON, default=list)  # ["ICD-10", "CM", "outpatient"]


class McpServer(Base, TimestampMixin):
    __tablename__ = "mcp_servers"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    expert_id: Mapped[str] = mapped_column(String(12), ForeignKey("experts.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    transport_type: Mapped[str] = mapped_column(String(32), default="streamable_http")
    description: Mapped[str] = mapped_column(Text, default="")
    auth_type: Mapped[str] = mapped_column(String(32), default="none")  # none / bearer / oauth2
    auth_header: Mapped[str | None] = mapped_column(String(512), nullable=True)  # e.g. "Bearer sk-xxx"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
