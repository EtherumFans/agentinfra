# iCoDer - OAuth 2.0 Client Model (RFC 6749 Client Credentials Grant)
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


class OAuthClient(Base, TimestampMixin):
    """OAuth 2.0 Client for machine-to-machine (M2M) authentication.

    Implements RFC 6749 Client Credentials Grant.
    Used by SDK consumers, CI/CD pipelines, and backend services.

    Corti parity (2026-06-30, Phase 1.0): default ``token_expires_seconds``
    flipped to 5 minutes to match the Corti short-lived-token blast radius
    pattern (see docs/corti-reverse-engineered/SUMMARY.md §13.2).
    Clients may declare ``scopes`` as either iCoDer-style RBAC scopes
    (``api:read``, ``api:write``) or Corti-style capability scopes
    (``transcribe``, ``streams``, ``textgen``, ``facts``).

    Phase 7 Gate 5 §10 additions:
      - ``allowed_origins`` — JSON array of exact Origin strings permitted
        to embed this client's widget (Phase 7 §11.1). NULL = no embed.
      - ``embedded_app_id`` — public app identifier sent to the browser
        so partners can correlate runs to a specific app registration.
    """
    __tablename__ = "oauth_clients"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    client_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    client_secret_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    scopes: Mapped[str] = mapped_column(String(512), default="api:read api:write")  # space-separated
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[str] = mapped_column(String(12), nullable=False, index=True)  # user who created it
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    token_expires_seconds: Mapped[int] = mapped_column(default=300)  # 5 minutes default (Corti parity)

    # Phase 7 Gate 5 §10: partner embed attribution
    allowed_origins: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    embedded_app_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    @classmethod
    def generate_client_id(cls, prefix: str = "icoder") -> str:
        """Generate a unique client_id like 'icoder-abc123def456'."""
        return f"{prefix}-{secrets.token_hex(12)}"

    @classmethod
    def generate_client_secret(cls) -> tuple[str, str]:
        """Generate a client_secret. Returns (plaintext, hash)."""
        plaintext = f"ics_{secrets.token_hex(32)}"
        secret_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        return plaintext, secret_hash

    @classmethod
    def verify_secret(cls, plaintext: str, secret_hash: str) -> bool:
        """Verify a client_secret against its hash."""
        return hashlib.sha256(plaintext.encode()).hexdigest() == secret_hash

    def has_scope(self, scope: str) -> bool:
        """Check if this client has the requested scope."""
        return scope in (self.scopes or "").split()

    def granted_scopes(self) -> set[str]:
        """Return the set of scopes this client may request tokens for."""
        return {s for s in (self.scopes or "").split() if s}

    def is_capability_only(self, capability_scopes: set[str]) -> bool:
        """True iff every granted scope is a Corti-style capability scope.

        Per docs.corti-reverse-engineered/SUMMARY.md §13.2, capability-only
        tokens are short-lived credentials scoped to a single streaming or
        textgen endpoint family, e.g. ``openid transcribe`` for STT dictation
        or ``openid streams`` for ambient clinical intelligence.
        """
        granted = self.granted_scopes()
        return bool(granted) and granted.issubset(capability_scopes)

    def origin_allowed(self, origin: Optional[str]) -> bool:
        """Phase 7 §11.1: exact Origin match against allowed_origins.

        - Empty/None ``allowed_origins`` → no embed permitted (deny).
        - Empty/None ``origin`` → deny (browser always sends Origin on
          cross-origin requests).
        - Exact string match (case-sensitive) → allow.
        - No wildcard support (§11.1 explicitly forbids ``*``).
        """
        if not origin:
            return False
        origins = self.allowed_origins or []
        return origin in origins


class OAuthToken(Base, TimestampMixin):
    """Active OAuth 2.0 access tokens (for revocation/audit)."""
    __tablename__ = "oauth_tokens"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    client_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    scopes: Mapped[str] = mapped_column(String(512), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class TokenBlacklist(Base, TimestampMixin):
    """Revoked JWT tokens — prevents reuse after logout or password change."""
    __tablename__ = "token_blacklist"

    token_hash: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_reason: Mapped[str] = mapped_column(String(64), default="logout")  # logout | password_change | admin


class PasswordResetToken(Base, TimestampMixin):
    """Time-limited password reset tokens."""
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[str] = mapped_column(String(12), ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
