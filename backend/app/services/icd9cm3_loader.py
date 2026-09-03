"""ICD-9-CM-3 loader — read-only access to the iCoDerA procedure catalog.

Loads:
  - icd9cm3_code_catalog.json (13,617 codes, name_cn, name_en, synonyms,
    chapter, insurance metadata)

The asset directory defaults to ``E:/iCoDerA/DataAsset`` and can be
overridden via the ``ICODER_DATA_ASSET_DIR`` env var. The directory is
treated as read-only — this module never writes back to it.

E1.5 — closes audit gap #3. Mirrors ``icd10cn_loader.py`` so the
``MedCodERICD9CM3Retriever`` can apply a catalog compliance filter to
ghost codes that may have leaked into the FAISS metadata.

Usage::

    from app.services.icd9cm3_loader import get_loader
    loader = get_loader()
    by_code = loader.code_dict()            # dict[code, ICD9CM3Entry]
    ch = loader.chapter_for("45.2301")      # str e.g. "第1章 操作与介入"
    if loader.has("45.2301"): ...            # catalog membership check
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Default location of the read-only iCoDerA DataAsset directory.
# Inherits the same convention as icd10cn_loader so a single env var
# points both loaders at the same asset root.
DEFAULT_ASSET_DIR = str(
    Path(__file__).resolve().parents[2] / "data" / "code_dicts" / "assets"
)

CATALOG_FILENAME = "icd9cm3_code_catalog.json"


@dataclass(frozen=True)
class ICD9CM3Entry:
    """A single ICD-9-CM-3 catalog row."""

    code: str
    name_cn: str
    name_en: str
    category: str
    entry_option: str
    synonyms_cn: tuple[str, ...]
    synonyms_en: tuple[str, ...]
    chapter_range: str
    chapter_no: str
    chapter_name: str
    is_extended: bool = False
    insurance_code: str = ""
    is_insurance_gray: bool = False

    @property
    def all_names(self) -> tuple[str, ...]:
        """Every name and synonym for embedding / display."""
        seen: list[str] = []
        for n in (self.name_cn, self.name_en, *self.synonyms_cn, *self.synonyms_en):
            if n and n not in seen:
                seen.append(n)
        return tuple(seen)


@dataclass
class ICD9CM3LoaderStats:
    catalog_codes: int = 0
    chapters: int = 0
    loaded_from: str = ""


class ICD9CM3Loader:
    """In-memory loader for the ICD-9-CM-3 procedure catalog.

    Thread-safe singleton. The catalog is small (~13.6k rows, ~2.5 MB on
    disk) so we trade memory for sub-millisecond lookups the retriever
    needs during ``retrieve_async``.
    """

    def __init__(self, asset_dir: str | None = None) -> None:
        self._asset_dir = asset_dir or os.environ.get("ICODER_DATA_ASSET_DIR", DEFAULT_ASSET_DIR)
        self._lock = threading.RLock()
        self._codes_by_code: dict[str, ICD9CM3Entry] = {}
        self._chapters: dict[str, str] = {}  # chapter_range -> chapter_name
        self._stats = ICD9CM3LoaderStats()
        self._loaded = False

    # ── Lifecycle ──

    def load(self) -> "ICD9CM3LoaderStats":
        """Load (or reload) catalog from disk. Idempotent."""
        with self._lock:
            if self._loaded:
                return self._stats
            cat_path = os.path.join(self._asset_dir, CATALOG_FILENAME)
            if not os.path.isfile(cat_path):
                raise FileNotFoundError(f"ICD-9-CM-3 catalog not found: {cat_path}")

            logger.info("Loading ICD-9-CM-3 catalog from %s", cat_path)
            with open(cat_path, encoding="utf-8") as f:
                # Some entries have non-standard escapes — be tolerant.
                catalog = json.load(f, strict=False)

            self._codes_by_code = {
                row["code"]: self._row_to_entry(row)
                for row in catalog.get("codes", [])
                if row.get("code")
            }
            # Chapters: icd9cm3_code_catalog.json stores chapters as
            # ``{range: name}`` (range "00", "01", etc.). Fall back to empty
            # dict if absent.
            self._chapters = dict(catalog.get("chapters", {}))

            self._stats = ICD9CM3LoaderStats(
                catalog_codes=len(self._codes_by_code),
                chapters=len(self._chapters),
                loaded_from=self._asset_dir,
            )
            self._loaded = True
            logger.info(
                "ICD-9-CM-3 loaded: %d codes, %d chapters",
                self._stats.catalog_codes,
                self._stats.chapters,
            )
            return self._stats

    def ensure_loaded(self) -> "ICD9CM3LoaderStats":
        with self._lock:
            if not self._loaded:
                return self.load()
            return self._stats

    # ── Accessors ──

    def code_dict(self) -> dict[str, ICD9CM3Entry]:
        self.ensure_loaded()
        with self._lock:
            return dict(self._codes_by_code)

    def all_codes(self) -> list[ICD9CM3Entry]:
        self.ensure_loaded()
        with self._lock:
            return list(self._codes_by_code.values())

    def chapters(self) -> dict[str, str]:
        self.ensure_loaded()
        with self._lock:
            return dict(self._chapters)

    def get(self, code: str) -> ICD9CM3Entry | None:
        self.ensure_loaded()
        with self._lock:
            return self._codes_by_code.get(code)

    def has(self, code: str) -> bool:
        """Catalog membership check (used by MedCodERICD9CM3Retriever filter)."""
        self.ensure_loaded()
        with self._lock:
            return code in self._codes_by_code

    def chapter_for(self, code: str) -> str:
        """Return human-readable chapter label like '第1章 操作与介入', or ''.

        Falls back to the entry's stored chapter_no + chapter_name if the
        chapter index doesn't have a key for this code.
        """
        entry = self.get(code)
        if not entry:
            return ""
        if entry.chapter_no or entry.chapter_name:
            return f"{entry.chapter_no} {entry.chapter_name}".strip()
        return ""

    def stats(self) -> ICD9CM3LoaderStats:
        with self._lock:
            return ICD9CM3LoaderStats(**vars(self._stats))

    # ── Internal ──

    @staticmethod
    def _row_to_entry(row: dict) -> ICD9CM3Entry:
        return ICD9CM3Entry(
            code=row.get("code", ""),
            name_cn=row.get("name_cn", ""),
            name_en=row.get("name_en", ""),
            category=row.get("category", ""),
            entry_option=row.get("entry_option", ""),
            synonyms_cn=tuple(row.get("synonyms_cn") or ()),
            synonyms_en=tuple(row.get("synonyms_en") or ()),
            chapter_range=row.get("chapter_range", ""),
            chapter_no=row.get("chapter_no", ""),
            chapter_name=row.get("chapter_name", ""),
            is_extended=bool(row.get("is_extended", False)),
            insurance_code=row.get("insurance_code", ""),
            is_insurance_gray=bool(row.get("is_insurance_gray", False)),
        )


# ── Module-level singleton ──

_singleton: ICD9CM3Loader | None = None
_singleton_lock = threading.Lock()


def get_loader() -> ICD9CM3Loader:
    """Return the process-wide ICD-9-CM-3 loader, loading on first call."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = ICD9CM3Loader()
            _singleton.load()
        return _singleton


def reset_singleton() -> None:
    """For tests: drop the cached loader so the next get_loader() reloads from disk."""
    global _singleton
    with _singleton_lock:
        _singleton = None


__all__ = [
    "CATALOG_FILENAME",
    "DEFAULT_ASSET_DIR",
    "ICD9CM3Entry",
    "ICD9CM3Loader",
    "ICD9CM3LoaderStats",
    "get_loader",
    "reset_singleton",
]
