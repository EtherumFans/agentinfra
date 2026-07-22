# iCoDer - Expert Registry API (A1B-AE.3)
"""Expert Registry REST endpoints — A1B-AE.3.

This module exposes the ``/api/v1/experts`` surface, surfacing the
provenance fields added by Migration 022 (Charter Amendment 1 §7).
Prior to A1B-AE.3, the Expert model existed but had no dedicated REST
API — Experts were referenced opaquely via ``agent.expert_ids`` and
discovered programmatically via ``expert_registry.list_all()``.

A1B-AE.3 does NOT break that programmatic surface. It adds three new
endpoints for first-class Expert inspection:

- ``GET /api/v1/experts`` — list (filter by origin, corti_alignment,
  pack_dir, category, prebuilt flag).
- ``GET /api/v1/experts/{id}`` — detail (full provenance block).
- ``GET /api/v1/experts/registry/reconcile`` — audit: cross-check the
  DB rows against ``backend/agent_catalog/expert_catalog.json``
  produced by A1B-AE.2.

Read-only by design. Expert creation happens via seed.py / Pack load /
CLI; A1B-AE.4 will add Corti-Console-style Agent CRUD that wraps
Expert create.

Provenance: this module draws on two evidence tiers per Charter
Amendment 1:

- CLEAN_ROOM_PUBLIC — Corti public docs /agentic/experts (A1B-AE.1 §3.2
  9-key registry).
- REVERSE_ENGINEERED — Corti Console network trace session
  2026-07-22T0739-UTC (no /rest/v1/experts endpoint observed; Experts
  are embedded inside agent_definitions per Console pattern).
"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.models.expert import (
    Expert,
    McpServer,
    EXPERT_ORIGIN_VALUES,
    EXPERT_CORTI_ALIGNMENT_VALUES,
    MCP_AUTHORIZATION_TYPE_VALUES,
)
from app.models.user import User
from app.models.organization import Organization
from app.schemas.expert import (
    ExpertResponse,
    ExpertListResponse,
    ExpertRegistryReconcileEntry,
    ExpertRegistryReconcileResponse,
    McpServerResponse,
)


router = APIRouter(prefix="/api/v1/experts", tags=["expert-registry"])


# ── Helpers ─────────────────────────────────────────────────────────
def _expert_to_response(e: Expert) -> ExpertResponse:
    return ExpertResponse(
        id=e.id,
        name=e.name,
        description=e.description or "",
        category=e.category or "",
        icon=e.icon or "Bot",
        system_prompt=e.system_prompt or "",
        tools=[],
        config={},
        is_active=True,
        created_at=getattr(e, "created_at", None),
        updated_at=getattr(e, "updated_at", None),
        canonical_key=e.canonical_key,
        origin=e.origin or "ICODER_INTERNAL",
        corti_alignment=e.corti_alignment or "UNKNOWN",
        pack_dir=e.pack_dir,
        provenance=e.provenance,
    )


def _mcp_to_response(m: McpServer) -> McpServerResponse:
    return McpServerResponse(
        id=m.id,
        expert_id=m.expert_id,
        name=m.name,
        url=m.url,
        transport_type=m.transport_type or "streamable_http",
        description=m.description or "",
        authorization_type=m.authorization_type or "none",
        auth_type=m.auth_type or "none",
        is_active=bool(m.is_active),
    )


# ── Endpoints ───────────────────────────────────────────────────────

@router.get("", response_model=ExpertListResponse)
async def list_experts(
    origin: Optional[str] = Query(
        None,
        description=f"Filter by origin. One of {EXPERT_ORIGIN_VALUES}.",
    ),
    corti_alignment: Optional[str] = Query(
        None,
        description=f"Filter by corti_alignment. One of {EXPERT_CORTI_ALIGNMENT_VALUES}.",
    ),
    pack_dir: Optional[str] = Query(None, description="Filter by Pack directory."),
    category: Optional[str] = Query(None, description="Filter by category."),
    is_prebuilt: Optional[bool] = Query(None, description="Filter by is_prebuilt flag."),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """List Experts with optional provenance filters.

    Default (no filter): returns ALL Experts visible to this
    organization. Caller can filter by any provenance dimension.
    """
    if origin is not None and origin not in EXPERT_ORIGIN_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"origin must be one of {EXPERT_ORIGIN_VALUES}",
        )
    if (
        corti_alignment is not None
        and corti_alignment not in EXPERT_CORTI_ALIGNMENT_VALUES
    ):
        raise HTTPException(
            status_code=400,
            detail=f"corti_alignment must be one of {EXPERT_CORTI_ALIGNMENT_VALUES}",
        )

    stmt = select(Expert).where(Expert.organization_id == current_org.id)
    if origin is not None:
        stmt = stmt.where(Expert.origin == origin)
    if corti_alignment is not None:
        stmt = stmt.where(Expert.corti_alignment == corti_alignment)
    if pack_dir is not None:
        stmt = stmt.where(Expert.pack_dir == pack_dir)
    if category is not None:
        stmt = stmt.where(Expert.category == category)
    if is_prebuilt is not None:
        stmt = stmt.where(Expert.is_prebuilt == is_prebuilt)
    stmt = stmt.order_by(Expert.category, Expert.name)

    result = await db.execute(stmt)
    experts = result.scalars().all()
    return ExpertListResponse(
        experts=[_expert_to_response(e) for e in experts],
        total=len(experts),
    )


@router.get("/registry/reconcile", response_model=ExpertRegistryReconcileResponse)
async def reconcile_expert_registry(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Audit: cross-check DB rows vs A1B-AE.2 expert_catalog.json.

    Returns a per-entry comparison. ``db_status`` is one of:

    - ``PRESENT`` — DB row exists with a matching canonical_key.
    - ``MISSING`` — catalog entry has no DB row (expected for
      CORTI_REFERENCE entries not yet implemented).
    - ``DIVERGENT`` — DB row exists but origin / corti_alignment /
      pack_dir differ from the catalog.
    """
    # Load the A1B-AE.2 catalog
    catalog_path = Path(__file__).resolve().parents[2] / "agent_catalog" / "expert_catalog.json"
    if not catalog_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"expert_catalog.json not found at {catalog_path}",
        )

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog_entries = catalog.get("entries", [])

    # Load all DB experts (org-scoped)
    stmt = select(Expert).where(Expert.organization_id == current_org.id)
    result = await db.execute(stmt)
    db_rows = result.scalars().all()

    # Index DB rows by canonical_key when present, else by name
    db_by_key: dict[str, Expert] = {}
    db_by_name: dict[str, Expert] = {}
    for r in db_rows:
        if r.canonical_key:
            db_by_key[r.canonical_key] = r
        if r.name:
            db_by_name[r.name.lower()] = r

    entries: list[ExpertRegistryReconcileEntry] = []
    present = 0
    missing = 0
    divergent = 0

    for cat in catalog_entries:
        cat_key = cat.get("key")
        cat_origin = cat.get("origin", "PACK_DECLARED")
        cat_align = cat.get("corti_alignment", "UNKNOWN")
        cat_pack = cat.get("pack_dir")
        cat_src = cat.get("source_file")

        # Try to find a matching DB row
        row = db_by_key.get(cat_key) if cat_key else None
        if row is None and cat_key:
            # Fall back to name match (case-insensitive)
            row = db_by_name.get(cat_key.lower())

        if row is None:
            entries.append(
                ExpertRegistryReconcileEntry(
                    catalog_key=cat_key or "",
                    catalog_origin=cat_origin,
                    catalog_corti_alignment=cat_align,
                    catalog_pack_dir=cat_pack,
                    catalog_source_file=cat_src,
                    db_status="MISSING",
                    divergences=[],
                )
            )
            missing += 1
            continue

        divergences: list[str] = []
        if row.origin != cat_origin:
            divergences.append(
                f"origin: db={row.origin!r} vs catalog={cat_origin!r}"
            )
        if row.corti_alignment != cat_align:
            divergences.append(
                f"corti_alignment: db={row.corti_alignment!r} vs catalog={cat_align!r}"
            )
        if (row.pack_dir or None) != (cat_pack or None):
            divergences.append(
                f"pack_dir: db={row.pack_dir!r} vs catalog={cat_pack!r}"
            )

        status = "DIVERGENT" if divergences else "PRESENT"
        if divergences:
            divergent += 1
        else:
            present += 1

        entries.append(
            ExpertRegistryReconcileEntry(
                db_id=row.id,
                db_name=row.name,
                catalog_key=cat_key or "",
                catalog_origin=cat_origin,
                catalog_corti_alignment=cat_align,
                catalog_pack_dir=cat_pack,
                catalog_source_file=cat_src,
                db_status=status,
                divergences=divergences,
            )
        )

    return ExpertRegistryReconcileResponse(
        catalog_path=str(catalog_path),
        catalog_count=len(catalog_entries),
        db_count_total=len(db_rows),
        db_count_canonical_keyed=len(db_by_key),
        entries=entries,
        summary={
            "present": present,
            "missing": missing,
            "divergent": divergent,
            "charter": "A1B-AE.3",
            "catalog_charter": "A1B-AE.2",
        },
    )


@router.get("/{expert_id}", response_model=ExpertResponse)
async def get_expert(
    expert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Get a single Expert by ID, including the full provenance block."""
    stmt = select(Expert).where(
        Expert.id == expert_id,
        Expert.organization_id == current_org.id,
    )
    result = await db.execute(stmt)
    row = result.scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    return _expert_to_response(row)


@router.get("/{expert_id}/mcp_servers", response_model=list[McpServerResponse])
async def list_expert_mcp_servers(
    expert_id: str,
    authorization_type: Optional[str] = Query(
        None,
        description=f"Filter by authorization_type. One of {MCP_AUTHORIZATION_TYPE_VALUES}.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """List MCP servers attached to an Expert.

    Exposes the A1B-AE.3 ``authorization_type`` enum so consumers can
    see at a glance which auth mode each MCP server requires.
    """
    if (
        authorization_type is not None
        and authorization_type not in MCP_AUTHORIZATION_TYPE_VALUES
    ):
        raise HTTPException(
            status_code=400,
            detail=f"authorization_type must be one of {MCP_AUTHORIZATION_TYPE_VALUES}",
        )
    stmt = select(McpServer).where(McpServer.expert_id == expert_id)
    if authorization_type is not None:
        stmt = stmt.where(McpServer.authorization_type == authorization_type)
    stmt = stmt.order_by(McpServer.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_mcp_to_response(m) for m in rows]
