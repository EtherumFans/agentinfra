# iCoDer - Tenant Scoping Helper
"""Utilities for enforcing organization-level data isolation in queries."""

from typing import TypeVar
from sqlalchemy import select, Select
from sqlalchemy.sql import functions as func

T = TypeVar("T")


def scope_query(stmt, model, org_id: str):
    """Add WHERE organization_id = :org_id to a SQLAlchemy statement.

    Usage:
        stmt = select(Encounter)
        stmt = scope_query(stmt, Encounter, org_id)
        result = await db.execute(stmt)
    """
    if hasattr(model, "organization_id"):
        return stmt.where(model.organization_id == org_id)
    return stmt


def set_org_context(instance, org_id: str):
    """Set organization_id on a new model instance before save.

    Usage:
        encounter = Encounter(...)
        set_org_context(encounter, org_id)
        db.add(encounter)
    """
    if hasattr(instance, "organization_id"):
        instance.organization_id = org_id


def org_count_query(model, org_id: str) -> Select:
    """Build a COUNT query scoped to an organization.

    Usage:
        stmt = org_count_query(Encounter, org_id)
        result = await db.execute(stmt)
        total = result.scalar()
    """
    stmt = select(func.count()).select_from(model)
    if hasattr(model, "organization_id"):
        stmt = stmt.where(model.organization_id == org_id)
    return stmt


def org_filter(org_id: str):
    """Return a simple filter clause for queries.

    Usage:
        stmt = select(Encounter).where(org_filter(org_id))
    """
    return lambda model: model.organization_id == org_id
