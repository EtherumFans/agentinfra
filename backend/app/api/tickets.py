"""iCoDer Tickets API — Corti parity for /tickets (Tickets Portal).

Corti /tickets IA:
- external Zendesk-style help portal (target=_blank)
- list tickets (All / Created by me / filter / search)
- create new ticket

iCoDer in-app equivalent:
* ``GET    /api/tickets``              — list (search + status + priority + paginate)
* ``POST   /api/tickets``              — create
* ``GET    /api/tickets/{id}``         — get one
* ``PATCH  /api/tickets/{id}``         — update status / priority / subject / desc
* ``DELETE /api/tickets/{id}``         — delete
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.models.ticket import Ticket, TicketStatus, TicketPriority
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


class TicketOut(BaseModel):
    id: str
    subject: str
    description: str
    status: str
    priority: str
    created_by_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TicketListOut(BaseModel):
    tickets: list[TicketOut]
    total: int
    page: int
    page_size: int


class TicketCreateIn(BaseModel):
    subject: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="", max_length=65536)
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketUpdateIn(BaseModel):
    subject: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=65536)
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None


def _to_out(t: Ticket) -> TicketOut:
    return TicketOut(
        id=t.id,
        subject=t.subject,
        description=t.description,
        status=t.status.value if hasattr(t.status, "value") else str(t.status),
        priority=t.priority.value if hasattr(t.priority, "value") else str(t.priority),
        created_by_id=t.created_by_id,
        created_at=t.created_at.isoformat() if t.created_at else None,
        updated_at=t.updated_at.isoformat() if t.updated_at else None,
    )


@router.get("", response_model=TicketListOut)
async def list_tickets(
    search: str = Query("", description="Search subject/description"),
    status: str = Query("", description="Filter by status"),
    priority: str = Query("", description="Filter by priority"),
    created_by_me: bool = Query(False, description="Only tickets I created"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TicketListOut:
    q = select(Ticket).where(Ticket.organization_id == current_org.id)
    if created_by_me:
        q = q.where(Ticket.created_by_id == user.id)
    if search:
        like = f"%{search}%"
        q = q.where(
            or_(
                Ticket.subject.ilike(like),
                Ticket.description.ilike(like),
            )
        )
    if status:
        try:
            q = q.where(Ticket.status == TicketStatus(status))
        except ValueError:
            pass
    if priority:
        try:
            q = q.where(Ticket.priority == TicketPriority(priority))
        except ValueError:
            pass
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(Ticket.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()
    return TicketListOut(
        tickets=[_to_out(t) for t in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketCreateIn,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    t = Ticket(
        organization_id=current_org.id,
        created_by_id=user.id,
        subject=body.subject.strip(),
        description=body.description.strip(),
        status=TicketStatus.OPEN,
        priority=body.priority,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _to_out(t)


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    t = (await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.organization_id == current_org.id,
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TICKET_NOT_FOUND", "ticket_id": ticket_id},
        )
    return _to_out(t)


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: str,
    body: TicketUpdateIn,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TicketOut:
    t = (await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.organization_id == current_org.id,
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TICKET_NOT_FOUND", "ticket_id": ticket_id},
        )
    if body.subject is not None:
        t.subject = body.subject.strip()
    if body.description is not None:
        t.description = body.description.strip()
    if body.status is not None:
        t.status = body.status
    if body.priority is not None:
        t.priority = body.priority
    await db.commit()
    await db.refresh(t)
    return _to_out(t)


@router.delete("/{ticket_id}", status_code=204)
async def delete_ticket(
    ticket_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    t = (await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id,
            Ticket.organization_id == current_org.id,
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TICKET_NOT_FOUND", "ticket_id": ticket_id},
        )
    await db.delete(t)
    await db.commit()


__all__ = ["router"]