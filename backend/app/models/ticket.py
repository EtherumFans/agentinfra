# iCoDer — Ticket model for Corti parity (Tickets Portal).
#
# Corti /tickets IA: external Zendesk-style help portal (target=_blank to
# help.corti.app/tickets-portal). iCoDer surfaces an in-app equivalent
# (no external infra dependency) with the same conceptual IA: tickets
# have subject / description / status / priority and are scoped to the
# user's organization.
#
# iCoDer extension: a fully in-app workflow so users can create, track,
# and resolve tickets without leaving the console.
import enum
from sqlalchemy import String, Enum, ForeignKey, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Ticket(Base, TimestampMixin):
    """A support ticket surfaced via the Tickets Portal.

    iCoDer-side equivalent of Corti's external Zendesk portal. Tickets
    are org-scoped; status transitions are free-form (no FSM gate —
    that would block self-service triage UX).
    """

    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_org_id", "organization_id"),
        Index("ix_tickets_status", "status"),
    )

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    created_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus), default=TicketStatus.OPEN, nullable=False
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority), default=TicketPriority.MEDIUM, nullable=False
    )