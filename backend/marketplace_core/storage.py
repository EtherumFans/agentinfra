"""Storage adapters for Marketplace. Supports filesystem (default) and pluggable backends."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import PackageRecord, PackageIndex

logger = logging.getLogger(__name__)


class StorageAdapter(ABC):
    """Abstract storage for marketplace index and packages."""

    @abstractmethod
    def load_index(self) -> PackageIndex:
        ...

    @abstractmethod
    def save_index(self, index: PackageIndex):
        ...

    @abstractmethod
    def save_package(self, record: PackageRecord, pack_data: dict):
        ...

    @abstractmethod
    def load_package(self, pkg_id: str) -> dict | None:
        ...

    @abstractmethod
    def increment_downloads(self, pkg_id: str):
        ...


class FileSystemStorage(StorageAdapter):
    """Filesystem-backed storage. Index as JSON, packages as individual files.

    Directory structure:
        {root}/
          index.json
          packages/
            {pkg_id}/
              package.json
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._pkg_dir = self.root / "packages"
        self._pkg_dir.mkdir(exist_ok=True)
        self._index_file = self.root / "index.json"

    def load_index(self) -> PackageIndex:
        idx = PackageIndex()
        if self._index_file.exists():
            try:
                data = json.loads(self._index_file.read_text(encoding="utf-8"))
                for pid, pdata in data.get("packages", {}).items():
                    idx.packages[pid] = PackageRecord.from_dict(pdata)
                idx.updated_at = data.get("updated_at", "")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Corrupted index file: {e}")
        return idx

    def save_index(self, index: PackageIndex):
        index.updated_at = datetime.now(timezone.utc).isoformat()
        data: dict[str, Any] = {"packages": {}, "updated_at": index.updated_at}
        for pid, pkg in index.packages.items():
            data["packages"][pid] = pkg.to_dict()
        self._index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_package(self, record: PackageRecord, pack_data: dict):
        pkg_dir = self._pkg_dir / record.id
        pkg_dir.mkdir(exist_ok=True)
        (pkg_dir / "package.json").write_text(
            json.dumps(pack_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load_package(self, pkg_id: str) -> dict | None:
        pkg_file = self._pkg_dir / pkg_id / "package.json"
        if pkg_file.exists():
            return json.loads(pkg_file.read_text(encoding="utf-8"))
        return None

    def increment_downloads(self, pkg_id: str):
        idx = self.load_index()
        if pkg_id in idx.packages:
            idx.packages[pkg_id].downloads += 1
            self.save_index(idx)


# Default storage singleton — initialized lazily
_storage: StorageAdapter | None = None


def get_storage(root: str | Path = "") -> StorageAdapter:
    global _storage
    if _storage is None:
        if root:
            _storage = FileSystemStorage(root)
        else:
            # Default to marketplace_data/ alongside the marketplace module
            default_root = Path(__file__).parent.parent.parent / "marketplace_data"
            _storage = FileSystemStorage(default_root)
    return _storage


def init_storage(root: str | Path) -> StorageAdapter:
    global _storage
    _storage = FileSystemStorage(root)
    return _storage
