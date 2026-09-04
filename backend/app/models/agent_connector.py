"""Persistent Agentic v2 connector resources.

Connector configuration is deliberately secret-free.  Credential rows store
only references to an external secret manager; raw bearer tokens, OAuth client
secrets, and authorization headers are never accepted by this model.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


CONNECTOR_TYPE_VALUES = ("registry", "mcp", "agent", "a2a", "schema")


class AgentConnector(Base, TimestampMixin):
    __tablename__ = "agent_connectors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "agent_id"],
            ["agents.organization_id", "agents.id"],
            name="fk_agent_connectors_agent_scope",
        ),
        ForeignKeyConstraint(
            ["organization_id", "target_agent_id"],
            ["agents.organization_id", "agents.id"],
            name="fk_agent_connectors_target_agent_scope",
        ),
        UniqueConstraint(
            "organization_id", "id", name="uq_agent_connectors_org_id",
        ),
        UniqueConstraint(
            "organization_id", "agent_id", "name",
            name="uq_agent_connector_org_agent_name",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False, index=True,
    )
    config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    target_agent_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True,
    )
    normalized_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    schema_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    schema_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )


class ConnectorCredential(Base, TimestampMixin):
    """Secret-manager metadata; ``secret_ref`` is not itself a secret."""

    __tablename__ = "connector_credentials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "connector_id"],
            ["agent_connectors.organization_id", "agent_connectors.id"],
            name="fk_connector_credentials_connector_scope",
        ),
        UniqueConstraint("connector_id", name="uq_connector_credential_connector"),
    )

    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    connector_id: Mapped[str] = mapped_column(
        String(12), nullable=False, index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(16), nullable=False)
    secret_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="active", server_default="active", nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)


class ConnectorExecutionAudit(Base, TimestampMixin):
    """Minimum-necessary execution and delegated authorization metadata."""

    __tablename__ = "connector_execution_audit"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "connector_id"],
            ["agent_connectors.organization_id", "agent_connectors.id"],
            name="fk_connector_execution_audit_connector_scope",
        ),
    )

    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    connector_id: Mapped[str] = mapped_column(
        String(12), nullable=False, index=True,
    )
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(
        String(24), default="unknown", server_default="unknown", nullable=False,
    )
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    delegated_subject_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True,
    )
    granted_scopes: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False,
    )
    granted_purposes: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False,
    )
    policy_decision: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    http_status_class: Mapped[str | None] = mapped_column(String(8), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_span_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


__all__ = [
    "CONNECTOR_TYPE_VALUES",
    "AgentConnector",
    "ConnectorCredential",
    "ConnectorExecutionAudit",
]
