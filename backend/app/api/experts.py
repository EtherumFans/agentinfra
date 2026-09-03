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
from sqlalchemy import func, or_, select
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
    ExpertCapabilityReadinessResponse,
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
    search: Optional[str] = Query(
        None,
        min_length=1,
        max_length=128,
        description="Case-insensitive name or description search.",
    ),
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
    if search is not None:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(Expert.name.ilike(pattern), Expert.description.ilike(pattern))
        )
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


@router.get("/readiness", response_model=ExpertCapabilityReadinessResponse)
async def get_expert_capability_readiness(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
) -> ExpertCapabilityReadinessResponse:
    """Return aggregate-only Expert/MCP readiness without URLs or credentials."""
    expert_count = int((await db.execute(
        select(func.count(Expert.id)).where(Expert.organization_id == current_org.id)
    )).scalar_one())
    published_count = int((await db.execute(
        select(func.count(Expert.id)).where(
            Expert.organization_id == current_org.id,
            Expert.is_published.is_(True),
        )
    )).scalar_one())
    mcp_rows = (await db.execute(
        select(McpServer.authorization_type, McpServer.is_active)
        .join(Expert, Expert.id == McpServer.expert_id)
        .where(
            Expert.organization_id == current_org.id,
            or_(
                McpServer.organization_id == current_org.id,
                McpServer.organization_id.is_(None),
            ),
        )
    )).all()
    authorization_counts = {key: 0 for key in MCP_AUTHORIZATION_TYPE_VALUES}
    for authorization_type, _is_active in mcp_rows:
        key = authorization_type if authorization_type in authorization_counts else "none"
        authorization_counts[key] += 1
    from app.icoder.mcp.tool_registry import TOOL_REGISTRY

    active_count = sum(1 for _auth, active in mcp_rows if bool(active))
    return ExpertCapabilityReadinessResponse(
        expert_count=expert_count,
        published_expert_count=published_count,
        mcp_server_count=len(mcp_rows),
        active_mcp_server_count=active_count,
        mcp_authorization_type_counts=authorization_counts,
        built_in_mcp_tool_count=len(TOOL_REGISTRY),
        tenant_scope_enforced=True,
        credentials_exposed=False,
        external_mcp_live_verified=False,
        aggregate_only=True,
        production_ready=False,
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
    expert_exists = (await db.execute(select(Expert.id).where(
        Expert.id == expert_id,
        Expert.organization_id == current_org.id,
    ))).scalar_one_or_none()
    if expert_exists is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    stmt = select(McpServer).where(
        McpServer.expert_id == expert_id,
        or_(
            McpServer.organization_id == current_org.id,
            McpServer.organization_id.is_(None),
        ),
    )
    if authorization_type is not None:
        stmt = stmt.where(McpServer.authorization_type == authorization_type)
    stmt = stmt.order_by(McpServer.name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_mcp_to_response(m) for m in rows]


# ─────────────────────────────────────────────────────────────────────
# A1B-AE.9 — External-Expert Gate endpoint
# ─────────────────────────────────────────────────────────────────────

@router.get("/external-gate/evaluate")
async def evaluate_external_expert_gate(
    expert_key: str = Query(..., description="The canonical_key of the Expert to evaluate."),
    region: Optional[str] = Query(
        None, description="Tenant region (CN/EU/US). If omitted, region check is skipped."
    ),
    egress_enabled: bool = Query(
        False,
        description="Whether external egress is enabled for this tenant (Charter §6 default: False).",
    ),
    provider_opt_in: bool = Query(
        False, description="Provider-level opt-in for web-search."
    ),
    tenant_opt_in: bool = Query(
        False, description="Tenant-level opt-in for web-search."
    ),
    licence_token_count: int = Query(
        0,
        description=(
            "Number of licence tokens supplied (for drugbank/posos). "
            "A1B-AE.9 does NOT accept the tokens themselves via query "
            "string — that would leak credentials. Callers POST tokens "
            "out-of-band; the gate evaluation just needs the count."
        ),
    ),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Evaluate the External-Expert Gate (A1B-AE.7) for a given Expert.

    Returns the gate's decision: ``permitted`` (bool), ``reason`` (one
    of OK / LICENCE_REQUIRED / EGRESS_DISABLED / REGION_BLOCKED /
    PROVIDER_OPT_IN_MISSING), and a human-readable ``notes`` field.

    The gate does NOT perform any live call. It only rules on what
    *would* be allowed under the supplied context. The caller MUST still
    consult each Expert's own ``live_*_performed`` flag.
    """
    from app.agents.experts.external_expert_gate import evaluate as gate_evaluate

    licence_tokens = ["_"] * max(0, licence_token_count)  # opaque stand-ins
    decision = gate_evaluate(
        expert_key,
        licence_tokens=licence_tokens,
        region=region,
        egress_enabled=egress_enabled,
        provider_opt_in=provider_opt_in,
        tenant_opt_in=tenant_opt_in,
    )
    return {
        "expert_key": decision.expert_key,
        "permitted": decision.permitted,
        "reason": decision.reason,
        "notes": decision.notes,
    }
