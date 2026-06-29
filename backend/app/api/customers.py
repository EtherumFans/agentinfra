"""iCoDer Customers API — Corti parity for Embedded Assistant end-user mgmt.

Corti /customers IA:
- list with Name / NFR / Region / Customer ID / Created / Actions
- search by name / customer ID / region / tenant
- Add customer modal: Display Name + Customer ID Suffix (alphanumeric/-/_)
  + Region (US / EU; iCoDer adds CN)
- pagination (page size 20 default)

Endpoints
---------
* ``GET    /api/customers``           — list (search + paginate)
* ``POST   /api/customers``           — create
* ``GET    /api/customers/{id}``      — get one
* ``DELETE /api/customers/{id}``      — delete
"""
from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.customer import Customer, CustomerRegion
from app.models.user import User

router = APIRouter(prefix="/api/customers", tags=["customers"])

_CUSTOMER_ID_SUFFIX_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class CustomerOut(BaseModel):
    id: str
    display_name: str
    customer_id: str
    region: str
    nfr: int
    created_at: Optional[str] = None


class CustomerListOut(BaseModel):
    customers: list[CustomerOut]
    total: int
    page: int
    page_size: int


class CustomerCreateIn(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=256)
    customer_id_suffix: str = Field(..., min_length=1, max_length=64)
    region: CustomerRegion = CustomerRegion.CN


def _to_out(c: Customer) -> CustomerOut:
    return CustomerOut(
        id=c.id,
        display_name=c.display_name,
        customer_id=c.customer_id,
        region=c.region.value if hasattr(c.region, "value") else str(c.region),
        nfr=c.nfr,
        created_at=c.created_at.isoformat() if c.created_at else None,
    )


def _resolve_org_slug(user: User) -> str:
    """Tenant prefix for the public-facing ``customer_id``.

    Falls back to the user's email local-part when no org slug is set;
    this matches Corti's behaviour where ``songluhua/`` prefix mirrors
    the project slug in the URL.
    """
    org = getattr(user, "organization", None)
    if org and getattr(org, "slug", None):
        return org.slug
    if user.email and "@" in user.email:
        return user.email.split("@", 1)[0].replace(".", "-")
    return f"u-{user.id}"


@router.get("", response_model=CustomerListOut)
async def list_customers(
    search: str = Query("", description="Search name/customer_id/region"),
    region: str = Query("", description="Filter by region (us/eu/cn)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerListOut:
    q = select(Customer).where(Customer.organization_id == user.organization_id)
    if search:
        like = f"%{search}%"
        q = q.where(
            or_(
                Customer.display_name.ilike(like),
                Customer.customer_id.ilike(like),
                Customer.region.ilike(like),
            )
        )
    if region:
        try:
            region_enum = CustomerRegion(region.lower())
        except ValueError:
            region_enum = None
        if region_enum is not None:
            q = q.where(Customer.region == region_enum)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(Customer.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()
    return CustomerListOut(
        customers=[_to_out(c) for c in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=CustomerOut, status_code=201)
async def create_customer(
    body: CustomerCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerOut:
    suffix = body.customer_id_suffix.strip()
    if not _CUSTOMER_ID_SUFFIX_RE.match(suffix):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_CUSTOMER_ID_SUFFIX",
                "message": "Customer ID Suffix must be alphanumeric, dash, or underscore (max 64 chars).",
            },
        )
    slug = _resolve_org_slug(user)
    customer_id = f"{slug}/{suffix}"
    exists = (await db.execute(
        select(Customer).where(Customer.customer_id == customer_id)
    )).scalar_one_or_none()
    if exists:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "CUSTOMER_ID_TAKEN",
                "message": f"Customer ID '{customer_id}' is already in use.",
            },
        )
    c = Customer(
        organization_id=user.organization_id,
        display_name=body.display_name.strip(),
        customer_id=customer_id,
        region=body.region,
        nfr=0,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return _to_out(c)


@router.get("/{customer_id:path}", response_model=CustomerOut)
async def get_customer(
    customer_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomerOut:
    c = (await db.execute(
        select(Customer).where(
            Customer.customer_id == customer_id,
            Customer.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "CUSTOMER_NOT_FOUND",
                "customer_id": customer_id,
            },
        )
    return _to_out(c)


@router.delete(
    "/{customer_id:path}",
    status_code=204,
    response_class=Response,
)
async def delete_customer(
    customer_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    c = (await db.execute(
        select(Customer).where(
            Customer.customer_id == customer_id,
            Customer.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "CUSTOMER_NOT_FOUND", "customer_id": customer_id},
        )
    await db.delete(c)
    await db.commit()
    return Response(status_code=204)


__all__ = ["router"]