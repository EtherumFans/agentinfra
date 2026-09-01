"""API Key management endpoints with database persistence"""
import hashlib
import secrets
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.models.api_key import ApiKey

router = APIRouter(prefix="/api/keys", tags=["keys"])


def _generate_key() -> tuple[str, str, str]:
    """Generate a new API key. Returns (full_key, key_prefix, key_hash)."""
    raw = secrets.token_hex(32)
    full_key = "sk-" + raw
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:10] + "\u2022" * 8
    return full_key, key_prefix, key_hash


@router.get("")
async def list_keys(
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List API keys for the current user"""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.owner_id == user.id,
            ApiKey.organization_id == current_org.id,
            ApiKey.is_active == True,
        ).order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return {
        "keys": [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "status": "active" if k.is_active else "revoked",
                "created_at": k.created_at.isoformat(),
                "last_used": k.last_used_at.isoformat() if k.last_used_at else None,
            }
            for k in keys
        ]
    }


@router.post("")
async def create_key(
    name: str = "Default Key",
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. Returns the full key only once."""
    full_key, key_prefix, key_hash = _generate_key()
    api_key = ApiKey(
        organization_id=current_org.id,
        owner_id=user.id,
        name=name,
        key_prefix=key_prefix,
        key_hash=key_hash,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "key_full": full_key,  # only returned once
        "status": "active",
        "created_at": api_key.created_at.isoformat(),
    }


@router.delete("/{key_id}")
async def delete_key(
    key_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key"""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == current_org.id,
            ApiKey.is_active == True,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Key not found")
    if key.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    key.is_active = False
    await db.commit()
    return {"status": "deleted"}
