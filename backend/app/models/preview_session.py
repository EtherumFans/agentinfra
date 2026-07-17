"""SQLAlchemy model for preview_sessions (Phase 7 Gate 13A-1).

Per Gate 13A architecture (reports/phase7/gate13a/PHASE7_GATE13A_THREAT_MODEL.md),
the Console's /ai-studio/embedded-assistant page issues a short-lived
(60s) signed Bootstrap Ticket that the iframe exchanges for a scoped
Runtime Token via authenticated POST. The DB row mirrors the ticket
claims and tracks usage so tickets can be revoked, marked USED, and
audited.

Schema:
  - id (PK)
  - preview_session_id (opaque UUID exposed in iframe URL — NOT the JWT)
  - organization_id (FK to organizations)
  - user_id (FK to users — Console user who created the session)
  - api_client_id (NULL for Console sessions; partner sessions may set this)
  - expected_parent_origin (e.g. http://localhost:3000 or https://console.icoder.cloud)
  - expected_iframe_origin (same as backend origin; the iframe is same-origin)
  - nonce (random 16-byte hex; MessageChannel handshake proves knowledge)
  - allowed_agent_ids (JSON list of agent_ref strings; empty = all)
  - allowed_scopes (JSON list of scope strings)
  - jti (JWT ID; unique per ticket)
  - single_use (bool; default True — ticket consumed on exchange)
  - token_version (int; bumped when signature format changes)
  - status (PENDING / EXCHANGED / REVOKED / EXPIRED)
  - issued_at, expires_at
  - exchanged_at (NULL until exchange succeeds)
  - exchanged_from_ip (audit field)

Indexes:
  - UNIQUE (jti) — prevents duplicate ticket IDs
  - INDEX (preview_session_id) — fast lookup by URL param
  - INDEX (expires_at) — periodic cleanup
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PreviewSession(Base):
    """A short-lived Console → iframe bootstrap session.

    The ticket is HMAC-signed (see app/services/preview_ticket.py) and
    bound to (preview_session_id, organization_id, user_id, parent_origin,
    nonce). The iframe must prove knowledge of the nonce via MessageChannel
    handshake before the parent trusts any message from it.
    """

    __tablename__ = "preview_sessions"

    __table_args__ = (
        UniqueConstraint("jti", name="uq_preview_sessions_jti"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    preview_session_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="Opaque UUID exposed in iframe URL (NOT the JWT)",
    )
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(12),
        ForeignKey("organizations.id"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=True, index=True,
    )
    api_client_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
        comment="NULL for Console sessions; set for partner preview sessions",
    )
    expected_parent_origin: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="The Console origin (e.g. http://localhost:3000)",
    )
    expected_iframe_origin: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="The iframe origin (always backend origin — same-host)",
    )
    nonce: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="Random hex; both sides must prove knowledge via MessageChannel",
    )
    allowed_agent_ids: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True,
        comment="JSON list of agent_ref strings; empty/NULL = all agents allowed",
    )
    allowed_scopes: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True,
        comment="JSON list of scope strings granted to the Runtime Token",
    )
    jti: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="JWT ID; unique per ticket; included in signature payload",
    )
    single_use: Mapped[bool] = mapped_column(
        # SQLite doesn't have bool; use Integer 0/1
        Integer, nullable=False, default=1,
        comment="1 = ticket consumed on first successful exchange",
    )
    token_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
        comment="Ticket format version; bumped on signature-scheme changes",
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING",
        comment="PENDING | EXCHANGED | REVOKED | EXPIRED",
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    exchanged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    exchanged_from_ip: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment="Client IP at ticket exchange; audit field",
    )

    def __repr__(self) -> str:
        return (
            f"<PreviewSession id={self.id} "
            f"psid={self.preview_session_id[:8]}... "
            f"status={self.status} jti={self.jti[:8]}...>"
        )
