"""iCoDer Agent Marketplace — ISV upload, search, download Agent packs.

Uses unified marketplace_core for storage and service logic.
Usage: python server.py --port 8767
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

# Add backend to path so we can import marketplace_core and icoder_runtime
_BACKEND = Path(__file__).parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from marketplace_core.service import MarketplaceService
from marketplace_core.storage import FileSystemStorage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Storage ──
BASE_DIR = Path(__file__).parent
_storage = FileSystemStorage(BASE_DIR)
_service = MarketplaceService(_storage)


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
    stats = _service.get_stats()
    return {"status": "healthy", "packages": stats["total_packages"]}


@app.post("/api/packages")
async def publish_package(req: PublishRequest):
    try:
        result = _service.publish(
            req.pack,
            publisher_name=req.publisher_name,
            publisher_email=req.publisher_email,
        )
        return result
    except Exception as e:
        detail = e.detail if hasattr(e, "detail") else {"errors": [str(e)]}
        raise HTTPException(status_code=400, detail=detail)


@app.get("/api/packages")
async def list_packages(
    search: str = "",
    category: str = "",
    sort: str = "newest",
    limit: int = 50,
):
    return _service.search(query=search, category=category, sort=sort, limit=limit)


@app.get("/api/packages/categories")
async def list_categories():
    return _service.list_categories()


@app.get("/api/packages/{pkg_id}")
async def get_package(pkg_id: str):
    pkg = _service.get_package(pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return pkg


@app.get("/api/packages/{pkg_id}/download")
async def download_package(pkg_id: str):
    pack = _service.download(pkg_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Package file not found")
    # Write temp file for FileResponse
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".icoder-agent", delete=False, encoding="utf-8")
    json.dump(pack, tmp, ensure_ascii=False, indent=2)
    tmp.close()
    return FileResponse(
        tmp.name,
        media_type="application/json",
        filename=f"{pkg_id}.icoder-agent",
    )


@app.get("/api/stats")
async def marketplace_stats():
    return _service.get_stats()


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
