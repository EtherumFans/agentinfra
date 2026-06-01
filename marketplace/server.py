"""iCoDer Agent Marketplace — ISV upload, search, download Agent packs.

Usage: python server.py --port 8080
"""

import argparse
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Storage ──
BASE_DIR = Path(__file__).parent
PACKAGES_DIR = BASE_DIR / "packages"
PACKAGES_DIR.mkdir(exist_ok=True)
INDEX_FILE = BASE_DIR / "index.json"


def _load_index() -> dict:
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    return {"packages": {}, "updated_at": ""}


def _save_index(data: dict):
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _validate_pack(pack: dict) -> list[str]:
    errors = []
    if not pack.get("format_version"):
        errors.append("Missing format_version")
    m = pack.get("manifest", {})
    if not m.get("name"):
        errors.append("Missing manifest.name")
    if not m.get("version"):
        errors.append("Missing manifest.version")
    if not pack.get("system_prompt"):
        errors.append("Missing system_prompt")
    return errors


# ── App ──
app = FastAPI(title="iCoDer Marketplace", version="1.0.0")


class PublishRequest(BaseModel):
    pack: dict
    publisher_name: str = ""
    publisher_email: str = ""


@app.get("/", response_class=HTMLResponse)
async def frontend():
    html = BASE_DIR / "index.html"
    if html.exists():
        return html.read_text(encoding="utf-8")
    return "<h1>iCoDer Marketplace</h1>"


@app.get("/api/health")
async def health():
    idx = _load_index()
    return {"status": "healthy", "packages": len(idx["packages"])}


@app.post("/api/packages")
async def publish_package(req: PublishRequest):
    pack = req.pack
    errors = _validate_pack(pack)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    manifest = pack["manifest"]
    pkg_id = f"{manifest['name'].lower().replace(' ','-')}-{manifest['version']}"

    # Save pack file
    pkg_dir = PACKAGES_DIR / pkg_id
    pkg_dir.mkdir(exist_ok=True)
    pack_path = pkg_dir / "package.json"
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")

    # Update index
    idx = _load_index()
    idx["packages"][pkg_id] = {
        "id": pkg_id,
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest.get("description", ""),
        "category": manifest.get("category", "general"),
        "icon": manifest.get("icon", "Bot"),
        "publisher_name": req.publisher_name or "Unknown",
        "publisher_email": req.publisher_email or "",
        "expert_count": len(pack.get("experts", [])),
        "tool_count": len(pack.get("tools", [])),
        "downloads": 0,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "integrity": pack.get("integrity", {}),
    }
    _save_index(idx)

    logger.info(f"Published: {pkg_id} by {req.publisher_name}")
    return {"id": pkg_id, "name": manifest["name"], "published": True}


@app.get("/api/packages")
async def list_packages(
    search: str = "",
    category: str = "",
    sort: str = "newest",
    limit: int = 50,
):
    idx = _load_index()
    pkgs = list(idx["packages"].values())

    if search:
        q = search.lower()
        pkgs = [p for p in pkgs if q in p["name"].lower() or q in p.get("description","").lower()]
    if category:
        pkgs = [p for p in pkgs if p.get("category") == category]

    if sort == "downloads":
        pkgs.sort(key=lambda p: p.get("downloads", 0), reverse=True)
    elif sort == "name":
        pkgs.sort(key=lambda p: p["name"])
    else:
        pkgs.sort(key=lambda p: p.get("published_at", ""), reverse=True)

    result = []
    for p in pkgs[:limit]:
        result.append({
            "id": p["id"], "name": p["name"], "version": p["version"],
            "description": p.get("description",""), "category": p.get("category","general"),
            "icon": p.get("icon","Bot"), "expert_count": p.get("expert_count",0),
            "tool_count": p.get("tool_count",0),
            "publisher_name": p.get("publisher_name",""),
            "downloads": p.get("downloads",0),
            "published_at": p.get("published_at",""),
        })
    return {"packages": result, "total": len(result)}


@app.get("/api/packages/categories")
async def list_categories():
    idx = _load_index()
    cats: dict[str, int] = {}
    for p in idx["packages"].values():
        c = p.get("category", "general")
        cats[c] = cats.get(c, 0) + 1
    return {"categories": [{"name": k, "count": v} for k, v in sorted(cats.items())]}


@app.get("/api/packages/{pkg_id}")
async def get_package(pkg_id: str):
    idx = _load_index()
    pkg = idx["packages"].get(pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@app.get("/api/packages/{pkg_id}/download")
async def download_package(pkg_id: str):
    pkg_path = PACKAGES_DIR / pkg_id / "package.json"
    if not pkg_path.exists():
        raise HTTPException(status_code=404, detail="Package file not found")

    # Increment download count
    idx = _load_index()
    if pkg_id in idx["packages"]:
        idx["packages"][pkg_id]["downloads"] = idx["packages"][pkg_id].get("downloads", 0) + 1
        _save_index(idx)

    return FileResponse(
        pkg_path,
        media_type="application/json",
        filename=f"{pkg_id}.icoder-agent",
    )


@app.get("/api/stats")
async def marketplace_stats():
    idx = _load_index()
    pkgs = idx["packages"].values()
    total_downloads = sum(p.get("downloads", 0) for p in pkgs)
    return {
        "total_packages": len(pkgs),
        "total_downloads": total_downloads,
        "categories": len(set(p.get("category") for p in pkgs)),
        "latest_publish": max((p.get("published_at","") for p in pkgs), default=""),
    }


def main():
    parser = argparse.ArgumentParser(description="iCoDer Marketplace Server")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    import uvicorn
    logger.info(f"Marketplace: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
