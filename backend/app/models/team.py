# iCoDer - Team Models
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin
import enum


class TeamRole(str, enum.Enum):
    OWNER = "owner"
    CODER = "coder"
    DEPT_HEAD = "dept_head"
    VIEWER = "viewer"


class TeamMember(Base, TimestampMixin):
    __tablename__ = "team_members"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(12), ForeignKey("users.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[TeamRole] = mapped_column(Enum(TeamRole), default=TeamRole.CODER, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / pending / removed
    invited_by: Mapped[str] = mapped_column(String(12), ForeignKey("users.id"), nullable=False)


class TeamInvite(Base, TimestampMixin):
    __tablename__ = "team_invites"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[TeamRole] = mapped_column(Enum(TeamRole), default=TeamRole.CODER, nullable=False)
    invited_by: Mapped[str] = mapped_column(String(12), ForeignKey("users.id"), nullable=False)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending / accepted / expired
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
