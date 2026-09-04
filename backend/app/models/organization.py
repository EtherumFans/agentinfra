# iCoDer - Organization (Multi-Tenant) Models
import enum
from sqlalchemy import String, Enum, Boolean, JSON, ForeignKey, UniqueConstraint, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class OrgRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


ORG_ROLE_ENUM = Enum(
    OrgRole,
    values_callable=lambda enum_type: [role.value for role in enum_type],
)


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(20), default="free")  # free / pro / enterprise
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class OrganizationMember(Base, TimestampMixin):
    __tablename__ = "organization_members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)

    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[OrgRole] = mapped_column(ORG_ROLE_ENUM, default=OrgRole.MEMBER, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class OrganizationInvite(Base, TimestampMixin):
    __tablename__ = "organization_invites"

    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[OrgRole] = mapped_column(ORG_ROLE_ENUM, default=OrgRole.MEMBER, nullable=False)
    # SHA-256 digest of the bearer invitation credential. The raw token is
    # returned once in local development and must never be persisted/logged.
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / accepted / expired / revoked
    expires_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    invited_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class OrganizationInviteDelivery(Base, TimestampMixin):
    """Durable encrypted outbox row for invitation delivery."""

    __tablename__ = "organization_invite_deliveries"
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    invite_id: Mapped[str] = mapped_column(
        ForeignKey("organization_invites.id"), nullable=False, unique=True, index=True
    )
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="queued", server_default="queued", nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    next_attempt_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    locked_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    delivered_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_message_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
