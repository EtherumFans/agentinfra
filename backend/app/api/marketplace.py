"""Marketplace API — Agent pack registry integrated into main platform.

GET  /api/marketplace/packages          — Browse/search (no auth)
POST /api/marketplace/packages          — Publish (auth required)
GET  /api/marketplace/packages/{id}     — Package detail
GET  /api/marketplace/packages/{id}/download — Download + count
GET  /api/marketplace/stats             — Stats
GET  /marketplace                       — Marketplace frontend HTML
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["marketplace"])

# ── Storage (shared with main platform, uses unified MarketplaceService) ──
_STORE_DIR = Path(__file__).parent.parent.parent / "marketplace_data"
_STORE_DIR.mkdir(exist_ok=True)
_PACKAGES_DIR = _STORE_DIR / "packages"
_PACKAGES_DIR.mkdir(exist_ok=True)

from marketplace_core.storage import FileSystemStorage
from marketplace_core.service import MarketplaceService

_storage = FileSystemStorage(_STORE_DIR)
_service = MarketplaceService(_storage)


class PublishRequest(BaseModel):
    pack: dict
    publisher_name: str = ""
    publisher_email: str = ""


@router.get("/marketplace", response_class=HTMLResponse)
async def marketplace_frontend():
    html_path = Path(__file__).parent.parent.parent.parent / "marketplace" / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>iCoDer Marketplace</h1>"


@router.get("/api/marketplace/packages")
async def list_packages(search: str = "", category: str = "", sort: str = "newest", limit: int = 50):
    return _service.search(query=search, category=category, sort=sort, limit=limit)


@router.post("/api/marketplace/packages", status_code=201)
async def publish_package(
    req: PublishRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pack = req.pack
    try:
        result = _service.publish(
            pack,
            publisher_name=req.publisher_name or user.username,
            publisher_email=req.publisher_email or (user.email or ""),
        )
        return result
    except Exception as e:
        detail = e.detail if hasattr(e, "detail") else {"errors": [str(e)]}
        raise HTTPException(status_code=400, detail=detail)


@router.get("/api/marketplace/packages/categories")
async def list_categories():
    return _service.list_categories()


@router.get("/api/marketplace/packages/{pkg_id}")
async def get_package(pkg_id: str):
    pkg = _service.get_package(pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@router.get("/api/marketplace/packages/{pkg_id}/download")
async def download_package(pkg_id: str):
    pack = _service.download(pkg_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Package file not found")
    # Write temp file for download
    # Return download as streaming response to avoid temp file leak
    from fastapi.responses import StreamingResponse
    import io
    content = json.dumps(pack, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.StringIO(content),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{pkg_id}.icoder-agent"'},
    )


@router.get("/api/marketplace/stats")
async def marketplace_stats():
    return _service.get_stats()


@router.post("/api/marketplace/packages/{pkg_id}/install")
async def install_package(
    pkg_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Install a marketplace package to the Embedded Runtime.

    Writes to BOTH the RuntimeAgentRegistry (new) AND the DB Agent table (backward compat).
    The installed agent is immediately runnable via /api/agents/{id}/run.
    """
    pkg_path = _PACKAGES_DIR / pkg_id / "package.json"
    if not pkg_path.exists():
        raise HTTPException(status_code=404, detail="Package not found")

    try:
        pack = json.loads(pkg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid package file")

    # Get the platform runtime
    try:
        from app.main import app as _app
        rt = _app.state.platform_runtime if hasattr(_app.state, "platform_runtime") else None
    except Exception:
        rt = None

    if not rt:
        raise HTTPException(status_code=503, detail="Platform Runtime not available")

    # Install into RuntimeAgentRegistry (new persistent store)
    try:
        result = rt.install_agent(
            pack,
            publisher_name=user.username,
            publisher_email=user.email or "",
        )
    except Exception as e:
        detail = e.detail if hasattr(e, "detail") else {"errors": [str(e)]}
        raise HTTPException(status_code=400, detail=detail)

    # Also sync to DB Agent table for backward compat with old /api/agents/{id}/run
    manifest = pack.get("manifest", {})
    try:
        db_agent = Agent(
            id=result["agent_id"],
            name=manifest.get("name", ""),
            description=manifest.get("description", ""),
            category=manifest.get("category", "general"),
            icon=manifest.get("icon", "Bot"),
            system_prompt=pack.get("system_prompt", ""),
            expert_ids=[e.get("id") for e in pack.get("experts", [])],
            status="published",
            organization_id=user.organization_id,
        )
        db.add(db_agent)
        await db.commit()
        logger.info(f"Agent synced to DB: {result['agent_id']}")
    except Exception as e:
        logger.warning(f"Failed to sync agent to DB (registry install succeeded): {e}")
        await db.rollback()

    return result


@router.get("/api/marketplace/installed")
async def list_installed_agents(
    user: User = Depends(get_current_user),
):
    """List agents installed in the Embedded Runtime."""
    try:
        from app.main import app as _app
        rt = _app.state.platform_runtime if hasattr(_app.state, "platform_runtime") else None
    except Exception:
        rt = None

    if not rt:
        return {"agents": [], "total": 0}

    agents = rt.list_agents()
    return {"agents": agents, "total": len(agents)}
