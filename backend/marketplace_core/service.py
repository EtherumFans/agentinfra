"""Marketplace Service — business logic shared across deployments."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .models import PackageRecord, PackageIndex
from .storage import StorageAdapter, get_storage

logger = logging.getLogger(__name__)


class MarketplaceService:
    """Core marketplace operations: publish, search, download, stats.

    Uses a StorageAdapter for persistence. Can be used by:
    - Standalone marketplace server (marketplace/server.py)
    - Platform marketplace API (app/api/marketplace.py)
    """

    def __init__(self, storage: StorageAdapter | None = None):
        self._storage = storage or get_storage()

    # ── Query ──

    def search(
        self,
        query: str = "",
        category: str = "",
        agent_type: str = "",
        sort: str = "newest",
        limit: int = 50,
    ) -> dict[str, Any]:
        idx = self._storage.load_index()
        results = idx.search(query=query, category=category, agent_type=agent_type)
        results = idx.sort(results, by=sort)
        return {
            "packages": [p.to_summary() for p in results[:limit]],
            "total": len(results),
        }

    def get_package(self, pkg_id: str) -> dict | None:
        idx = self._storage.load_index()
        pkg = idx.packages.get(pkg_id)
        if pkg:
            return pkg.to_dict()
        return None

    def list_categories(self) -> dict[str, Any]:
        idx = self._storage.load_index()
        cats = idx.categories
        return {"categories": [{"name": k, "count": v} for k, v in sorted(cats.items())]}

    def get_stats(self) -> dict[str, Any]:
        idx = self._storage.load_index()
        return {
            "total_packages": len(idx.packages),
            "total_downloads": idx.total_downloads,
            "categories": len(idx.categories),
            "latest_publish": max((p.published_at for p in idx.packages.values()), default=""),
        }

    # ── Publish ──

    def publish(
        self,
        pack: dict,
        publisher_name: str = "",
        publisher_email: str = "",
        *,
        validate: bool = True,
    ) -> dict[str, Any]:
        """Publish an agent package to the marketplace.

        If validate=True, the pack is validated against AgentPackageV1 schema.
        """
        if validate:
            from icoder_runtime.core.agent_pack_v1 import AgentPackageV1
            pkg = AgentPackageV1.from_dict(pack)
            pkg_id = f"{pkg.name.lower().replace(' ', '-')}-{pkg.version}"
        else:
            manifest = pack.get("manifest", {})
            name = manifest.get("name", "unknown")
            version = manifest.get("version", "0.0.0")
            pkg_id = f"{name.lower().replace(' ', '-')}-{version}"

        # Build package record
        manifest = pack.get("manifest", {})
        record = PackageRecord(
            id=pkg_id,
            name=manifest.get("name", ""),
            version=manifest.get("version", ""),
            description=manifest.get("description", ""),
            category=manifest.get("category", "general"),
            icon=manifest.get("icon", "Bot"),
            agent_type=pack.get("agent_type", "certified"),
            publisher_name=publisher_name or "Unknown",
            publisher_email=publisher_email or "",
            expert_count=len(pack.get("experts", [])),
            tool_count=len(pack.get("tools", [])),
            downloads=0,
            published_at=datetime.now(timezone.utc).isoformat(),
            integrity=pack.get("integrity", {}),
            min_runtime_version=(pack.get("requirements", {}) or {}).get("min_runtime_version", "1.0.0"),
        )

        # Save
        self._storage.save_package(record, pack)
        idx = self._storage.load_index()
        idx.packages[pkg_id] = record
        self._storage.save_index(idx)

        logger.info(f"Published: {pkg_id} by {publisher_name}")
        return {"id": pkg_id, "name": record.name, "published": True}

    # ── Download ──

    def download(self, pkg_id: str) -> dict | None:
        """Get the full package data for download. Increments download count."""
        pack = self._storage.load_package(pkg_id)
        if pack is not None:
            self._storage.increment_downloads(pkg_id)
        return pack
