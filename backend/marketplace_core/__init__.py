"""Unified Marketplace Core — shared across standalone and embedded marketplace deployments."""

from .models import PackageRecord, PackageIndex
from .storage import StorageAdapter, FileSystemStorage, get_storage
from .service import MarketplaceService

__all__ = [
    "PackageRecord",
    "PackageIndex",
    "StorageAdapter",
    "FileSystemStorage",
    "get_storage",
    "MarketplaceService",
]
