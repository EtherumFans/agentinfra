"""iCoDer M3-0 — CodingReviewRun SQLAlchemy model.

A CodingReviewRun is the persistent state of a single invocation of the
MedCodER 5-stage Coding Review Agent
(``icoder/medcoder-coding-review-agent@1.0.0``). It replaces
the in-memory ``_RUNS_STORE: dict`` previously used by
``app.api.icoder_coding_review``.

Phase D3 (2026-06-26): the legacy 14-stage ``homepage-coding-review``
agent has been removed; the ``agent_ref`` column still accepts the
legacy string for back-compat reads of historical rows.

Design notes
------------
* The PK is a 24-char hex string (uuid4) that matches the ``run_id`` exposed
  in the API response — so external code can correlate the API run_id with
  the DB row without a second lookup.
* Human-review records live as a JSON list on the row (``human_review_records``)
  rather than a separate child table. The cardinality is bounded (a single
  run has at most a handful of human-review entries) and we always fetch the
  full record on read, so a join is not worth the schema complexity.
* ``encounter_text_redacted`` holds the redacted text used for report
  export (PHI redaction at export, Commit 8). The original raw text never
  leaves the authenticated workbench view.
* ``drg_route`` and ``pipeline_stage_meta`` are nullable to support
  pre-Commit-7 / pre-Commit-6 runs that did not populate them.
* ``created_at`` uses a Python-side default (sub-second precision) rather
  than ``server_default=func.now()`` because SQLite's ``func.now()`` is
  second-precision — without microsecond precision, two runs inserted in
  the same second would be order-tie ambiguous in DESC list queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _new_run_id() -> str:
    """24-char hex id, matches the run_id exposed in the API response."""
    return uuid.uuid4().hex[:24]


def _utcnow() -> datetime:
    """Naive UTC datetime with sub-second precision (avoids SQLite sec-only now)."""
    return datetime.utcnow()


class CodingReviewRun(Base):
    """Persistent state of a single 14-stage coding-review run.

    Columns (id, created_at, updated_at) are defined explicitly to match
    the 24-char run_id length used by the API. The TimestampMixin pattern
    in this codebase uses 12-char ids; we need 24 to match the API contract.
    """

    __tablename__ = "coding_review_runs"

    # PK + timestamps — explicit so we control the PK length + ordering precision
    id: Mapped[str] = mapped_column(String(24), primary_key=True, default=_new_run_id)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, server_default=func.now(), onupdate=func.now(),
    )

    # Tenant + ownership
    organization_id: Mapped[Optional[str]] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=True, index=True,
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Agent identity
    agent_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="official_reference_agent",
    )
    prediction_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="link_validation",
    )

    # Case linkage (free-form string; not a FK — case_id may be a de-id handle)
    case_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    input_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")

    # Pipeline outcome — mirrors the API response
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unavailable")
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    business_result_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")

    # Encoded payloads — JSON for forward-compatible schema evolution
    primary_diagnosis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    secondary_diagnoses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    procedures: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    high_risk_coding_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_chain: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_route: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    safety_gate: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    drg_route: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    pipeline_stages_observed: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pipeline_stage_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Human-review records — bounded JSON list (1 row per review action)
    human_review_records: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Encounter text (raw) + redacted copy used for export
    encounter_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    encounter_text_redacted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Version metadata — populated from data/versions.json (Commit 8)
    model_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    code_dict_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rule_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    data_asset_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_coding_review_runs_org_created", "organization_id", "created_at"),
        Index("ix_coding_review_runs_status", "status"),
    )
