"""Phase A1A Gate 3R.3 — Deployment profile resolver for trace capture.

Replaces the binary ``RUNTRACE_STORE=memory|db`` + ``RUNTRACE_FAIL_CLOSED``
matrix with named profiles. Each profile binds a specific deployment
context to a concrete trace persistence policy so the cloud-mode
validation logic can reason about intent, not raw flags.

Profiles (Phase A1A Gate 3R.3 charter §3R.3):

  MEMORY_DEV
    - Run store: in-memory (``RunTraceStore``)
    - Fail-closed on DB write error: N/A (no DB writes)
    - Deployment context: local single-developer workflow, unit tests,
      CI smoke runs. Never used in cloud production.

  BEST_EFFORT_DB
    - Run store: DB-backed (``DbRunTraceStore``)
    - Fail-closed on DB write error: False (transient failures are
      logged + recorded on run_history.trace_capture_status=FAILED,
      but the run continues)
    - Deployment context: default cloud mode. Trace persistence is
      a best-effort audit signal; a transient DB issue must NOT
      downgrade a successful business operation.

  REQUIRED_DB
    - Run store: DB-backed (``DbRunTraceStore``)
    - Fail-closed on DB write error: True (any DB write failure
      propagates to the caller; the run is marked failed)
    - Deployment context: compliance environments that demand strict
      "no trace left behind". Hospital-on-prem installations that
      paid for SLA-backed audit would set this.

Resolution order (highest precedence first):

  1. ``ICODER_RUNTRACE_PROFILE`` env var (explicit operator override)
  2. Derived from ``ICODER_DEPLOYMENT_MODE`` + ``RUNTRACE_STORE`` +
     ``RUNTRACE_FAIL_CLOSED`` (backwards compat with Gate 3.3)
     - cloud + RUNTRACE_STORE=db + RUNTRACE_FAIL_CLOSED=False → BEST_EFFORT_DB
     - cloud + RUNTRACE_STORE=db + RUNTRACE_FAIL_CLOSED=True  → REQUIRED_DB
     - cloud + RUNTRACE_STORE=memory                           → rejected
       (existing cloud-mode validation refuses to boot)
     - local + RUNTRACE_STORE=memory                           → MEMORY_DEV
     - local + RUNTRACE_STORE=db                               → BEST_EFFORT_DB
       (local dev can still exercise the DB store)

Backwards compat: callers reading ``settings.RUNTRACE_STORE`` and
``settings.RUNTRACE_FAIL_CLOSED`` continue to work — the profile is
an overlay that resolves these flags from a single source of truth.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class DeploymentProfile:
    """The three named deployment profiles for trace capture.

    Stored as plain strings so they round-trip through env vars,
    Settings, and the audit log without serialization glue.
    """

    MEMORY_DEV = "MEMORY_DEV"
    BEST_EFFORT_DB = "BEST_EFFORT_DB"
    REQUIRED_DB = "REQUIRED_DB"

    ALL_PROFILES: frozenset[str] = frozenset({
        MEMORY_DEV,
        BEST_EFFORT_DB,
        REQUIRED_DB,
    })

    # Profiles that satisfy the cloud-mode "trace survives the run"
    # guarantee. MEMORY_DEV is local-only and refused at boot by
    # Settings validation when ICODER_DEPLOYMENT_MODE=cloud.
    CLOUD_ALLOWED: frozenset[str] = frozenset({
        BEST_EFFORT_DB,
        REQUIRED_DB,
    })

    @classmethod
    def is_cloud_allowed(cls, profile: Optional[str]) -> bool:
        return profile in cls.CLOUD_ALLOWED

    @classmethod
    def is_db_backed(cls, profile: Optional[str]) -> bool:
        """True if the profile routes trace writes through DbRunTraceStore."""
        return profile in {cls.BEST_EFFORT_DB, cls.REQUIRED_DB}

    @classmethod
    def is_fail_closed(cls, profile: Optional[str]) -> bool:
        """True if the profile propagates DB write failures to the caller."""
        return profile == cls.REQUIRED_DB


# ── Resolver ────────────────────────────────────────────────────────────


_ENV_OVERRIDE_VAR = "RUNTRACE_DEPLOYMENT_PROFILE"


def resolve_profile(
    *,
    deployment_mode: str,
    runtrace_store: str,
    runtrace_fail_closed: bool,
    explicit_profile: Optional[str] = None,
) -> str:
    """Resolve the deployment profile from settings + env override.

    Order of precedence (highest first):
      1. ``explicit_profile`` arg (caller-supplied, typically from
         ``ICODER_RUNTRACE_PROFILE`` env var)
      2. Derived from the (deployment_mode, runtrace_store,
         runtrace_fail_closed) triple — the Gate 3.3 matrix

    Raises ``ValueError`` for invalid ``explicit_profile`` values.
    Cloud-vs-MEMORY_DEV rejection is enforced later by Settings
    validation, NOT here — this function only resolves intent.
    """
    # 1. Explicit override
    if explicit_profile:
        normalized = explicit_profile.strip().upper()
        if normalized not in DeploymentProfile.ALL_PROFILES:
            raise ValueError(
                f"Unknown deployment profile: {explicit_profile!r}. "
                f"Must be one of {sorted(DeploymentProfile.ALL_PROFILES)}."
            )
        return normalized

    # 2. Derive from settings
    store_norm = (runtrace_store or "").strip().lower()
    if store_norm == "memory":
        # Memory store is MEMORY_DEV regardless of deployment_mode.
        # Settings validation handles the cloud-vs-memory refusal
        # separately — we don't second-guess the operator here.
        return DeploymentProfile.MEMORY_DEV

    if store_norm == "db":
        if deployment_mode == "cloud" and runtrace_fail_closed:
            return DeploymentProfile.REQUIRED_DB
        return DeploymentProfile.BEST_EFFORT_DB

    # Unknown store value — fall back to MEMORY_DEV (Settings will
    # refuse cloud boot, so this is safe in local dev only).
    logger.warning(
        "deployment_profile: unknown RUNTRACE_STORE=%r; defaulting to MEMORY_DEV",
        runtrace_store,
    )
    return DeploymentProfile.MEMORY_DEV


def get_current_profile() -> str:
    """Convenience accessor — resolve the profile from current Settings + env.

    Imports Settings lazily so this module can be imported from
    config.py without a circular import.
    """
    from app.config import settings
    explicit = os.environ.get(_ENV_OVERRIDE_VAR) or getattr(
        settings, "RUNTRACE_DEPLOYMENT_PROFILE", None
    )
    try:
        return resolve_profile(
            deployment_mode=settings.ICODER_DEPLOYMENT_MODE,
            runtrace_store=settings.RUNTRACE_STORE,
            runtrace_fail_closed=getattr(settings, "RUNTRACE_FAIL_CLOSED", False),
            explicit_profile=explicit,
        )
    except ValueError:
        # An invalid env var should refuse boot at Settings validation,
        # not here. Re-raise so the caller can surface the error.
        raise


__all__ = ["DeploymentProfile", "resolve_profile", "get_current_profile"]
