# iCoDer - Expert & MCP Server Models
"""Expert Registry + MCP Server models.

A1B-AE.3 (2026-07-22) extended these models with provenance fields per
Charter Amendment 1 §7 (dual-tier CLEAN_ROOM_PUBLIC + REVERSE_ENGINEERED
provenance). The new columns are:

- ``canonical_key`` — snake_case stable key matching Corti public docs
  (e.g. ``coding-expert``); unique where NOT NULL. Existing Corti-public
  Experts (the 9-key registry) plus reverse-engineered additions get
  canonical keys.
- ``origin`` — one of {CLEAN_ROOM_PUBLIC, REVERSE_ENGINEERED,
  ICODER_INTERNAL, PACK_DECLARED}. Classifies where the Expert definition
  came from.
- ``corti_alignment`` — one of {CORTI_REFERENCE, CORTI_ALIGNED,
  CORTI_ADAPTED, ICODER_ONLY, UNKNOWN}. Classifies how closely the iCoDer
  Expert mirrors a Corti-public counterpart.
- ``pack_dir`` — name of the official_agents/ subdirectory that declares
  this Expert (link to A1B-AE.2 catalog). NULL for Experts that are not
  Pack-declared.
- ``provenance`` — JSON blob holding the Charter Amendment 1 §7.2
  mandatory declaration block (sources, observation_session_ids,
  clean_room_attested, reverse_engineering_method, captured_at, etc.).

The McpServer model also gains ``authorization_type`` (enum 4 values per
Corti public docs §9 A1B-AE.3 clean-room observation: none | inherit |
bearer | oauth2.0). The legacy ``auth_type`` column is preserved for
backward compatibility; reads fall back to it when ``authorization_type``
is NULL.
"""
from sqlalchemy import String, Boolean, Integer, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import TimestampMixin


# A1B-AE.3 — Provenance enum values (Charter Amendment 1 §7)
EXPERT_ORIGIN_VALUES = (
    "CLEAN_ROOM_PUBLIC",      # clean-room copy of Corti public docs
    "REVERSE_ENGINEERED",     # observed via headed browser behind login
    "ICODER_INTERNAL",        # iCoDer-original Python module
    "PACK_DECLARED",          # declared inside an agent_pack.json
)

EXPERT_CORTI_ALIGNMENT_VALUES = (
    "CORTI_REFERENCE",        # Corti public docs reference, not yet implemented
    "CORTI_ALIGNED",          # 1:1 alignment with a Corti-public Expert
    "CORTI_ADAPTED",          # adapted from Corti-public shape, iCoDer extensions
    "ICODER_ONLY",            # no Corti-public counterpart
    "UNKNOWN",                # not yet classified
)

# A1B-AE.3 — MCP authorization enum (Corti public docs §9 — 4 values exhaustive)
MCP_AUTHORIZATION_TYPE_VALUES = (
    "none",       # MCP server is fully public
    "inherit",    # MCP server inherits calling agent's auth (user session token)
    "bearer",     # static bearer token provided via DataPart at thread creation
    "oauth2.0",   # OAuth2 client_credentials via DataPart at thread creation
)


class Expert(Base, TimestampMixin):
    __tablename__ = "experts"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(64), default="Bot")
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    is_prebuilt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    # Registry fields
    capabilities: Mapped[list] = mapped_column(JSON, default=list)  # ["diagnosis_coding", "procedure_coding"]
    input_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # JSON Schema for input
    output_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # JSON Schema for output
    tags: Mapped[list] = mapped_column(JSON, default=list)  # ["ICD-10", "CM", "outpatient"]

    # ── A1B-AE.3 Provenance fields (Charter Amendment 1 §7) ──────────
    canonical_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True,
    )
    origin: Mapped[str] = mapped_column(
        String(32), nullable=False, default="ICODER_INTERNAL", server_default="icoder_internal",
    )
    corti_alignment: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNKNOWN", server_default="unknown",
    )
    pack_dir: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
    )
    provenance: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )


class McpServer(Base, TimestampMixin):
    __tablename__ = "mcp_servers"

    organization_id: Mapped[str] = mapped_column(String(12), ForeignKey("organizations.id"), nullable=True, index=True)
    expert_id: Mapped[str] = mapped_column(String(12), ForeignKey("experts.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    transport_type: Mapped[str] = mapped_column(String(32), default="streamable_http")
    description: Mapped[str] = mapped_column(Text, default="")
    auth_type: Mapped[str] = mapped_column(String(32), default="none")  # none / bearer / oauth2 — LEGACY column, kept for back-compat
    authorization_type: Mapped[str] = mapped_column(
        String(32), default="none", server_default="none",
    )  # A1B-AE.3 — Corti canonical enum: none | inherit | bearer | oauth2.0
    auth_header: Mapped[str | None] = mapped_column(String(512), nullable=True)  # e.g. "Bearer sk-xxx"
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
