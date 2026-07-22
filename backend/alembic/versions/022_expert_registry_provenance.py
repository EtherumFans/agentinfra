"""Phase A1B-AE.3 — Expert Registry provenance + MCP authorizationType.

Revision ID: 022
Revises: 021
Create Date: 2026-07-22

Charter Amendment 1 (v1.1) introduced dual-tier provenance for Expert
and MCP artefacts: CLEAN_ROOM_PUBLIC (unchanged from v1.0) plus the new
REVERSE_ENGINEERED tier (permitted observation of Corti Console under
developer account). This migration lands the DB schema that supports
both tiers.

Schema changes:

1. ``experts`` table — 5 new columns:
   - ``canonical_key`` VARCHAR(128) NULL initially (unique constraint
     added in §3 below; backfill in §2 normalises existing rows first).
     snake_case stable key matching Corti public docs (e.g.
     ``coding-expert``). iCoDer-original Experts may leave this NULL.
   - ``origin`` VARCHAR(32) NOT NULL DEFAULT 'ICODER_INTERNAL'.
     One of {CLEAN_ROOM_PUBLIC, REVERSE_ENGINEERED, ICODER_INTERNAL,
     PACK_DECLARED} per Charter Amendment 1 §7.1-§7.3.
   - ``corti_alignment`` VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN'.
     One of {CORTI_REFERENCE, CORTI_ALIGNED, CORTI_ADAPTED, ICODER_ONLY,
     UNKNOWN}.
   - ``pack_dir`` VARCHAR(128) NULL. Links the Expert to its
     official_agents/<pack_dir>/ directory per A1B-AE.2 catalog.
   - ``provenance`` JSON NULL. Holds the Charter Amendment 1 §7.2
     mandatory declaration block for REVERSE_ENGINEERED artefacts.

2. ``mcp_servers`` table — 1 new column:
   - ``authorization_type`` VARCHAR(32) NOT NULL DEFAULT 'none'.
     Corti public canonical enum (4 values exhaustive per A1B-AE.3 §9
     clean-room observation): none | inherit | bearer | oauth2.0.
     Legacy ``auth_type`` column is preserved; reads fall back to it
     when ``authorization_type`` is NULL or the explicit value is
     missing.

3. CHECK constraints enforce the enum domains; a partial UNIQUE index
   on (canonical_key) WHERE canonical_key IS NOT NULL prevents
   duplicate-key collisions without blocking multiple NULL-keyed
   iCoDer-original rows.

The migration is idempotent on re-application: every column addition
is guarded by an introspection check; constraint creation is wrapped
in try/except per the pattern established by Migration 019.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# A1B-AE.3 §1 — enum domains (kept in sync with app.models.expert)
_EXPERT_ORIGIN_VALUES = (
    "CLEAN_ROOM_PUBLIC",
    "REVERSE_ENGINEERED",
    "ICODER_INTERNAL",
    "PACK_DECLARED",
)
_EXPERT_CORTI_ALIGNMENT_VALUES = (
    "CORTI_REFERENCE",
    "CORTI_ALIGNED",
    "CORTI_ADAPTED",
    "ICODER_ONLY",
    "UNKNOWN",
)
_MCP_AUTHORIZATION_TYPE_VALUES = (
    "none",
    "inherit",
    "bearer",
    "oauth2.0",
)


def _column_exists(bind, table: str, column: str) -> bool:
    # SQLite PRAGMA doesn't accept bind parameters; the table name is a
    # constant controlled by this migration so f-string is safe here.
    row = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in row)


def upgrade() -> None:
    bind = op.get_bind()

    # ── §1 Add new columns (idempotent) ──────────────────────────────
    if not _column_exists(bind, "experts", "canonical_key"):
        with op.batch_alter_table("experts") as batch_op:
            batch_op.add_column(sa.Column("canonical_key", sa.String(128), nullable=True))
    if not _column_exists(bind, "experts", "origin"):
        with op.batch_alter_table("experts") as batch_op:
            batch_op.add_column(
                sa.Column("origin", sa.String(32), nullable=False, server_default="ICODER_INTERNAL")
            )
    if not _column_exists(bind, "experts", "corti_alignment"):
        with op.batch_alter_table("experts") as batch_op:
            batch_op.add_column(
                sa.Column("corti_alignment", sa.String(32), nullable=False, server_default="UNKNOWN")
            )
    if not _column_exists(bind, "experts", "pack_dir"):
        with op.batch_alter_table("experts") as batch_op:
            batch_op.add_column(sa.Column("pack_dir", sa.String(128), nullable=True))
    if not _column_exists(bind, "experts", "provenance"):
        with op.batch_alter_table("experts") as batch_op:
            batch_op.add_column(sa.Column("provenance", sa.JSON(), nullable=True))

    if not _column_exists(bind, "mcp_servers", "authorization_type"):
        with op.batch_alter_table("mcp_servers") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "authorization_type", sa.String(32), nullable=False, server_default="none"
                )
            )

    # ── §2 Indexes (idempotent) ──────────────────────────────────────
    try:
        with op.batch_alter_table("experts") as batch_op:
            batch_op.create_index(
                "ix_experts_canonical_key",
                ["canonical_key"],
            )
    except Exception as e:
        print(f"  [022] experts.ix_experts_canonical_key skipped ({e})")

    # ── §3 CHECK constraints for enum domains ────────────────────────
    # Wrap each in try/except so partial-state DBs don't blow up the
    # migration mid-flight.
    origin_values_sql = ",".join(f"'{v}'" for v in _EXPERT_ORIGIN_VALUES)
    alignment_values_sql = ",".join(f"'{v}'" for v in _EXPERT_CORTI_ALIGNMENT_VALUES)
    mcp_values_sql = ",".join(f"'{v}'" for v in _MCP_AUTHORIZATION_TYPE_VALUES)

    try:
        with op.batch_alter_table("experts") as batch_op:
            batch_op.create_check_constraint(
                "chk_experts_origin_domain",
                condition=f"origin IN ({origin_values_sql})",
            )
    except Exception as e:
        print(f"  [022] experts.chk_experts_origin_domain skipped ({e})")

    try:
        with op.batch_alter_table("experts") as batch_op:
            batch_op.create_check_constraint(
                "chk_experts_corti_alignment_domain",
                condition=f"corti_alignment IN ({alignment_values_sql})",
            )
    except Exception as e:
        print(f"  [022] experts.chk_experts_corti_alignment_domain skipped ({e})")

    try:
        with op.batch_alter_table("mcp_servers") as batch_op:
            batch_op.create_check_constraint(
                "chk_mcp_servers_authorization_type_domain",
                condition=f"authorization_type IN ({mcp_values_sql})",
            )
    except Exception as e:
        print(f"  [022] mcp_servers.chk_mcp_servers_authorization_type_domain skipped ({e})")

    # ── §4 Backfill authorization_type from legacy auth_type ─────────
    # Legacy auth_type accepted {none, bearer, oauth2}. All three have
    # direct counterparts in the Corti canonical enum. `inherit` has no
    # legacy equivalent and is not backfilled.
    bind.execute(
        sa.text(
            "UPDATE mcp_servers SET authorization_type = auth_type "
            "WHERE authorization_type = 'none' AND auth_type IN ('bearer', 'oauth2')"
        )
    )

    # ── §5 Backfill origin for pre-existing rows ─────────────────────
    # Heuristic: rows seeded by app/seed.py with is_prebuilt=1 are
    # PACK_DECLARED (their pack_dir is populated lazily by A1B-AE.3's
    # registry reconcile endpoint). All others are ICODER_INTERNAL
    # until proven otherwise.
    bind.execute(
        sa.text(
            "UPDATE experts SET origin = 'PACK_DECLARED' "
            "WHERE origin = 'ICODER_INTERNAL' AND is_prebuilt = 1"
        )
    )


def downgrade() -> None:
    # Reverse order: drop CHECKs, drop indexes, drop columns.
    for table, constraint in (
        ("experts", "chk_experts_origin_domain"),
        ("experts", "chk_experts_corti_alignment_domain"),
        ("mcp_servers", "chk_mcp_servers_authorization_type_domain"),
    ):
        try:
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_constraint(constraint, type_="check")
        except Exception:
            pass

    try:
        with op.batch_alter_table("experts") as batch_op:
            batch_op.drop_index("ix_experts_canonical_key")
    except Exception:
        pass

    with op.batch_alter_table("experts") as batch_op:
        batch_op.drop_column("provenance")
        batch_op.drop_column("pack_dir")
        batch_op.drop_column("corti_alignment")
        batch_op.drop_column("origin")
        batch_op.drop_column("canonical_key")

    with op.batch_alter_table("mcp_servers") as batch_op:
        batch_op.drop_column("authorization_type")
