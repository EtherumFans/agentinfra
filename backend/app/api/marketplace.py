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

# ── Storage (shared with main platform) ──
_STORE_DIR = Path(__file__).parent.parent.parent / "marketplace_data"
_STORE_DIR.mkdir(exist_ok=True)
_PACKAGES_DIR = _STORE_DIR / "packages"
_PACKAGES_DIR.mkdir(exist_ok=True)
_INDEX_FILE = _STORE_DIR / "index.json"


def _load_index():
    if _INDEX_FILE.exists():
        return json.loads(_INDEX_FILE.read_text(encoding="utf-8"))
    return {"packages": {}}


def _save_index(data):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    _INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_pack(pack):
    errors = []
    if not pack.get("format_version"): errors.append("Missing format_version")
    m = pack.get("manifest", {})
    if not m.get("name"): errors.append("Missing manifest.name")
    if not m.get("version"): errors.append("Missing manifest.version")
    return errors


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
    idx = _load_index()
    pkgs = list(idx["packages"].values())
    if search:
        q = search.lower()
        pkgs = [p for p in pkgs if q in p["name"].lower() or q in p.get("description", "").lower()]
    if category:
        pkgs = [p for p in pkgs if p.get("category") == category]
    if sort == "downloads":
        pkgs.sort(key=lambda p: p.get("downloads", 0), reverse=True)
    elif sort == "name":
        pkgs.sort(key=lambda p: p["name"])
    else:
        pkgs.sort(key=lambda p: p.get("published_at", ""), reverse=True)
    return {"packages": pkgs[:limit], "total": len(pkgs)}


@router.post("/api/marketplace/packages", status_code=201)
async def publish_package(
    req: PublishRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pack = req.pack
    errors = _validate_pack(pack)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    manifest = pack["manifest"]
    pkg_id = f"{manifest['name'].lower().replace(' ','-')}-{manifest['version']}"

    pkg_dir = _PACKAGES_DIR / pkg_id
    pkg_dir.mkdir(exist_ok=True)
    (pkg_dir / "package.json").write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")

    idx = _load_index()
    idx["packages"][pkg_id] = {
        "id": pkg_id, "name": manifest["name"], "version": manifest["version"],
        "description": manifest.get("description", ""),
        "category": manifest.get("category", "general"),
        "icon": manifest.get("icon", "Bot"),
        "agent_type": pack.get("agent_type", "certified"),
        "expert_count": len(pack.get("experts", [])),
        "tool_count": len(pack.get("tools", [])),
        "publisher_name": req.publisher_name or user.username,
        "publisher_email": req.publisher_email or user.email,
        "downloads": 0,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "integrity": pack.get("integrity", {}),
    }
    _save_index(idx)
    return {"id": pkg_id, "name": manifest["name"], "published": True}


@router.get("/api/marketplace/packages/categories")
async def list_categories():
    idx = _load_index()
    cats = {}
    for p in idx["packages"].values():
        c = p.get("category", "general")
        cats[c] = cats.get(c, 0) + 1
    return {"categories": [{"name": k, "count": v} for k, v in sorted(cats.items())]}


@router.get("/api/marketplace/packages/{pkg_id}")
async def get_package(pkg_id: str):
    idx = _load_index()
    pkg = idx["packages"].get(pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@router.get("/api/marketplace/packages/{pkg_id}/download")
async def download_package(pkg_id: str):
    pkg_path = _PACKAGES_DIR / pkg_id / "package.json"
    if not pkg_path.exists():
        raise HTTPException(status_code=404, detail="Package file not found")
    idx = _load_index()
    if pkg_id in idx["packages"]:
        idx["packages"][pkg_id]["downloads"] = idx["packages"][pkg_id].get("downloads", 0) + 1
        _save_index(idx)
    return FileResponse(pkg_path, media_type="application/json", filename=f"{pkg_id}.icoder-agent")


@router.get("/api/marketplace/stats")
async def marketplace_stats():
    idx = _load_index()
    pkgs = idx["packages"].values()
    return {
        "total_packages": len(pkgs),
        "total_downloads": sum(p.get("downloads", 0) for p in pkgs),
        "categories": len(set(p.get("category") for p in pkgs)),
    }
