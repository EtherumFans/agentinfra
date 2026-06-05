"""Agent Account — machine identity for agents.

Each installed Agent gets an AgentAccount — a machine identity that can
authenticate to external systems (HIS/EMR, drug databases, insurance APIs).
This is NOT a human login account. There is no password.

AgentAccounts are used for:
- Audit: which Agent performed which operation
- Access control: what external systems can this Agent access (scopes)
- Credential rotation: API keys can be rotated without reinstalling the Agent
"""

from sqlalchemy import String, ForeignKey, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone

from app.database import Base


class AgentAccount(Base):
    """Machine identity for an installed Agent."""

    __tablename__ = "agent_accounts"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(128), ForeignKey("agents.id"), nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(String(32), default="oauth")  # oauth | api_key | mtls
    display_name: Mapped[str] = mapped_column(String(128), default="")
    scopes: Mapped[dict] = mapped_column(JSON, default=list)  # ["fhir:read", "his:query"]
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | suspended | revoked

    # Credential storage (references to CredentialVault)
    credential_ref: Mapped[str] = mapped_column(String(128), default="")  # vault key, e.g. "agent_acct_xyz"

    last_rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "account_type": self.account_type,
            "display_name": self.display_name,
            "scopes": self.scopes,
            "status": self.status,
            "last_rotated_at": self.last_rotated_at.isoformat() if self.last_rotated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def is_active(self) -> bool:
        return self.status == "active"

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])
