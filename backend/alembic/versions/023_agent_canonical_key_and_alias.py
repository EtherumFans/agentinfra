"""Phase A1B-AE.4 — Agent canonical_key + agent_type + aliases.

Revision ID: 023
Revises: 022
Create Date: 2026-07-22

A1B-AE.4 lands the Corti public Agent contract fields on the Agent
model so iCoDer can expose both internal routes and Corti-compatible
surfaces (Agent Card §6, create-then-customize Console UX).

Schema changes:

1. ``agents.canonical_key`` VARCHAR(128) NULL — snake_case stable key
   matching Corti public convention (dash-form wins for dual-named
   pairs per A1B-AE.2 §3.4). NULL for iCoDer-original custom Agents
   that have no canonical counterpart.

2. ``agents.agent_type`` VARCHAR(32) NOT NULL DEFAULT 'orchestrator'
   — Corti public §6 3-value enum (expert | orchestrator |
   interviewing-expert).

3. ``agents.aliases`` JSON — list of alternate keys the Agent
   answers to. Populated for legacy underscore-form dual names per
   A1B-AE.2 §3.4 canonical-name rule.

CHECK constraints enforce the agent_type domain. Backfill rules:

- Pre-existing prebuilt Agents get canonical_key derived from name
  slugified to snake_case (lowercase, non-alphanum → '-').
- Pre-existing Agents with NULL agent_type get 'orchestrator' (the
  iCoDer convention for multi-Expert compositions).
- The 3 known dual-named legacy Pack Agents (code_validation,
  compliance_guardrail, note_completeness) get their canonical_key
  set to the dash-form AND their aliases list populated with the
  underscore-form. This is the data-layer half of the clone-404
  fix; the application-layer half is the new AliasResolver service.

Idempotent on re-application per the Migration 019/022 pattern.
"""
from __future__ import annotations

import json
import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AGENT_TYPE_VALUES = ("expert", "orchestrator", "interviewing-expert")
_AGENT_TYPE_DEFAULT = "orchestrator"

# A1B-AE.2 §3.4 — canonical-name rule for the 3 known dual-named pairs.
_DUAL_NAME_FIXES = {
    "code_validation": ("code-validation", ["code_validation"]),
    "compliance_guardrail": ("compliance-guardrail", ["compliance_guardrail"]),
    "note_completeness": ("note-completeness", ["note_completeness"]),
}


def _column_exists(bind, table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(bind).get_columns(table)}


def _slugify(name: str) -> str:
    """Convert a display name to a Corti-style canonical key.

    e.g. 'Medical Coding Agent' → 'medical-coding-agent'
         'ICD-10 索引导航专家' → 'icd-10'
    Non-ASCII names fall back to a truncated md5-derived stable key
    to avoid colliding with Corti public canonical keys.
    """
    if not name:
        return ""
    s = re.sub(r"[^A-Za-z0-9]+", "-", name.strip()).strip("-").lower()
    if not s:
        # Non-ASCII fallback — stable hash of the original name.
        import hashlib
        s = "agent-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return s


def upgrade() -> None:
    bind = op.get_bind()

    # ── §1 Add new columns (idempotent) ──────────────────────────────
    if not _column_exists(bind, "agents", "canonical_key"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.add_column(sa.Column("canonical_key", sa.String(128), nullable=True))
    if not _column_exists(bind, "agents", "agent_type"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "agent_type",
                    sa.String(32),
                    nullable=False,
                    server_default=_AGENT_TYPE_DEFAULT,
                )
            )
    if not _column_exists(bind, "agents", "aliases"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.add_column(sa.Column("aliases", sa.JSON(), nullable=True))

    # ── §2 Indexes ───────────────────────────────────────────────────
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("agents")}
    if "ix_agents_canonical_key" not in indexes:
        op.create_index("ix_agents_canonical_key", "agents", ["canonical_key"])

    # ── §3 CHECK constraint on agent_type enum ───────────────────────
    values_sql = ",".join(f"'{v}'" for v in _AGENT_TYPE_VALUES)
    checks = {
        item["name"] for item in sa.inspect(bind).get_check_constraints("agents")
    }
    if "chk_agents_agent_type_domain" not in checks:
        with op.batch_alter_table("agents") as batch_op:
            batch_op.create_check_constraint(
                "chk_agents_agent_type_domain",
                condition=f"agent_type IN ({values_sql})",
            )

    # ── §4 Backfill canonical_key from name (slug) ───────────────────
    rows = bind.execute(sa.text("SELECT id, name FROM agents WHERE canonical_key IS NULL")).fetchall()
    for row in rows:
        agent_id, name = row[0], row[1] or ""
        # Check dual-name fix table first
        if name in _DUAL_NAME_FIXES:
            canonical, aliases = _DUAL_NAME_FIXES[name]
            bind.execute(
                sa.text(
                    "UPDATE agents SET canonical_key = :ck, aliases = :al "
                    "WHERE id = :id"
                ),
                {"ck": canonical, "al": json.dumps(aliases), "id": agent_id},
            )
        else:
            slug = _slugify(name)
            if slug:
                bind.execute(
                    sa.text("UPDATE agents SET canonical_key = :ck WHERE id = :id"),
                    {"ck": slug, "id": agent_id},
                )

    # ── §5 Backfill aliases JSON to [] for NULL rows ─────────────────
    bind.execute(
        sa.text(
            "UPDATE agents SET aliases = :empty WHERE aliases IS NULL"
        ),
        {"empty": "[]"},
    )


def downgrade() -> None:
    bind = op.get_bind()
    checks = {
        item["name"] for item in sa.inspect(bind).get_check_constraints("agents")
    }
    if "chk_agents_agent_type_domain" in checks:
        with op.batch_alter_table("agents") as batch_op:
            batch_op.drop_constraint("chk_agents_agent_type_domain", type_="check")

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("agents")}
    if "ix_agents_canonical_key" in indexes:
        op.drop_index("ix_agents_canonical_key", table_name="agents")

    with op.batch_alter_table("agents") as batch_op:
        batch_op.drop_column("aliases")
        batch_op.drop_column("agent_type")
        batch_op.drop_column("canonical_key")
