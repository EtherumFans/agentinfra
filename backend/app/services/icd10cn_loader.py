"""ICD-10-CN loader — read-only access to the iCoDerA data assets.

Loads:
  - icd10cn_code_catalog.json (37,897 codes, name_cn, name_en, synonyms, chapter)
  - icd10cn_synonym_map.json (75,968 synonyms + 56,424 term reverse index)

The asset directory defaults to ``E:/iCoDerA/DataAsset`` and can be overridden
via the ``ICODER_DATA_ASSET_DIR`` env var. The directory is treated as read-only
— this module never writes back to it.

Usage:
    from app.services.icd10cn_loader import get_loader
    loader = get_loader()
    entries = loader.all_codes()            # list[ICDEntry]
    by_code = loader.code_dict()            # dict[code, ICDEntry]
    syns = loader.synonyms_for("心衰")       # list[str] (from term_index)
    codes = loader.codes_for_term("心衰")    # list[str]
    ch = loader.chapter_for("I50.900")      # str e.g. "第9章 循环系统疾病"
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)

# Default location of the read-only iCoDerA DataAsset directory.
DEFAULT_ASSET_DIR = r"E:\iCoDerA\DataAsset"

CATALOG_FILENAME = "icd10cn_code_catalog.json"
SYNONYM_FILENAME = "icd10cn_synonym_map.json"


@dataclass(frozen=True)
class ICDEntry:
    """A single ICD-10-CN catalog row."""

    code: str
    name_cn: str
    name_en: str
    synonyms_cn: tuple[str, ...]
    synonyms_en: tuple[str, ...]
    chapter_range: str
    chapter_no: str
    chapter_name: str
    category_code: str
    clinical_category: str
    is_extended: bool = False
    is_dagger_asterisk: bool = False
    is_generated_category: bool = False
    is_insurance_gray: bool = False
    insurance_code: str = ""
    insurance_name: str = ""

    @property
    def all_names(self) -> tuple[str, ...]:
        """Every name and synonym for embedding / display."""
        seen: list[str] = []
        for n in (self.name_cn, self.name_en, *self.synonyms_cn, *self.synonyms_en):
            if n and n not in seen:
                seen.append(n)
        return tuple(seen)


@dataclass
class LoaderStats:
    catalog_codes: int = 0
    synonym_categories: int = 0
    term_index_size: int = 0
    loaded_from: str = ""


class ICD10CNLoader:
    """In-memory loader for the ICD-10-CN catalog + synonym map.

    Thread-safe singleton. The full catalog is small enough to keep resident
    (37k rows × ~500 bytes ≈ 18 MB) so we trade memory for the
    sub-millisecond lookups the retriever needs.
    """

    def __init__(self, asset_dir: str | None = None) -> None:
        self._asset_dir = asset_dir or os.environ.get("ICODER_DATA_ASSET_DIR", DEFAULT_ASSET_DIR)
        self._lock = threading.RLock()
        self._codes_by_code: dict[str, ICDEntry] = {}
        self._chapters: dict[str, dict] = {}  # chapter_range -> chapter dict
        self._term_index: dict[str, list[str]] = {}  # term (lowercased) -> [code]
        self._synonyms_by_category: dict[str, dict] = {}
        self._stats = LoaderStats()
        self._loaded = False

    # ── Lifecycle ──

    def load(self) -> LoaderStats:
        """Load (or reload) catalog + synonym map from disk. Idempotent."""
        with self._lock:
            if self._loaded:
                return self._stats
            cat_path = os.path.join(self._asset_dir, CATALOG_FILENAME)
            syn_path = os.path.join(self._asset_dir, SYNONYM_FILENAME)
            if not os.path.isfile(cat_path):
                raise FileNotFoundError(f"Catalog not found: {cat_path}")
            if not os.path.isfile(syn_path):
                raise FileNotFoundError(f"Synonym map not found: {syn_path}")

            logger.info("Loading ICD-10-CN catalog from %s", cat_path)
            with open(cat_path, encoding="utf-8") as f:
                # Some entries have non-standard escapes — use strict=False to be tolerant.
                catalog = json.load(f, strict=False)

            self._codes_by_code = {
                row["code"]: self._row_to_entry(row)
                for row in catalog.get("codes", [])
            }
            self._chapters = dict(catalog.get("chapters", {}))

            logger.info("Loading synonym map from %s", syn_path)
            with open(syn_path, encoding="utf-8") as f:
                syn = json.load(f, strict=False)

            self._synonyms_by_category = dict(syn.get("synonyms", {}))
            self._term_index = {
                (k or "").lower(): list(v) for k, v in (syn.get("term_index") or {}).items()
            }

            self._stats = LoaderStats(
                catalog_codes=len(self._codes_by_code),
                synonym_categories=len(self._synonyms_by_category),
                term_index_size=len(self._term_index),
                loaded_from=self._asset_dir,
            )
            self._loaded = True
            logger.info(
                "ICD-10-CN loaded: %d codes, %d categories, %d term-index entries",
                self._stats.catalog_codes,
                self._stats.synonym_categories,
                self._stats.term_index_size,
            )
            return self._stats

    def ensure_loaded(self) -> LoaderStats:
        with self._lock:
            if not self._loaded:
                return self.load()
            return self._stats

    # ── Accessors ──

    def code_dict(self) -> dict[str, ICDEntry]:
        self.ensure_loaded()
        with self._lock:
            return dict(self._codes_by_code)

    def all_codes(self) -> list[ICDEntry]:
        self.ensure_loaded()
        with self._lock:
            return list(self._codes_by_code.values())

    def chapters(self) -> dict[str, dict]:
        self.ensure_loaded()
        with self._lock:
            return dict(self._chapters)

    def term_index(self) -> dict[str, list[str]]:
        self.ensure_loaded()
        with self._lock:
            return {k: list(v) for k, v in self._term_index.items()}

    def get(self, code: str) -> ICDEntry | None:
        self.ensure_loaded()
        with self._lock:
            return self._codes_by_code.get(code)

    def has(self, code: str) -> bool:
        self.ensure_loaded()
        with self._lock:
            return code in self._codes_by_code

    def chapter_for(self, code: str) -> str:
        """Return human-readable chapter label like '第9章 循环系统疾病', or ''."""
        entry = self.get(code)
        if not entry:
            return ""
        return f"{entry.chapter_no} {entry.chapter_name}".strip()

    # ── Synonym / term lookup ──

    def codes_for_term(self, term: str) -> list[str]:
        """Reverse lookup: given a Chinese / English term, return candidate codes.

        Case-insensitive. Returns empty list if the term is not indexed.
        """
        if not term:
            return []
        self.ensure_loaded()
        with self._lock:
            return list(self._term_index.get(term.lower(), []))

    def synonyms_for(self, term: str, max_synonyms: int = 3) -> list[str]:
        """Pick up to ``max_synonyms`` co-occurring terms for query expansion.

        We use the term_index as a soft semantic source: any term that
        shares a code with the input is a likely synonym. Returns the
        canonical ``name_cn`` for each shared code, deduped, length-sorted
        descending (prefer longer descriptive names).
        """
        if not term:
            return []
        self.ensure_loaded()
        codes = self.codes_for_term(term)
        if not codes:
            return []
        seen: set[str] = set()
        names: list[str] = []
        with self._lock:
            for c in codes:
                entry = self._codes_by_code.get(c)
                if not entry:
                    continue
                for n in (entry.name_cn, *entry.synonyms_cn):
                    if n and n != term and n not in seen:
                        seen.add(n)
                        names.append(n)
        names.sort(key=lambda s: (-len(s), s))
        return names[:max_synonyms]

    def codes_for_codes(self, codes: Iterable[str]) -> list[ICDEntry]:
        """Bulk lookup: filter unknown codes, return ICDEntry list (preserves order)."""
        self.ensure_loaded()
        with self._lock:
            out: list[ICDEntry] = []
            for c in codes:
                e = self._codes_by_code.get(c)
                if e is not None:
                    out.append(e)
            return out

    def stats(self) -> LoaderStats:
        self.ensure_loaded()
        with self._lock:
            return LoaderStats(**vars(self._stats))

    # ── Internal ──

    @staticmethod
    def _row_to_entry(row: dict) -> ICDEntry:
        return ICDEntry(
            code=row.get("code", ""),
            name_cn=row.get("name_cn", ""),
            name_en=row.get("name_en", ""),
            synonyms_cn=tuple(row.get("synonyms_cn") or ()),
            synonyms_en=tuple(row.get("synonyms_en") or ()),
            chapter_range=row.get("chapter_range", ""),
            chapter_no=row.get("chapter_no", ""),
            chapter_name=row.get("chapter_name", ""),
            category_code=row.get("category_code", ""),
            clinical_category=row.get("clinical_category", ""),
            is_extended=bool(row.get("is_extended", False)),
            is_dagger_asterisk=bool(row.get("is_dagger_asterisk", False)),
            is_generated_category=bool(row.get("is_generated_category", False)),
            is_insurance_gray=bool(row.get("is_insurance_gray", False)),
            insurance_code=row.get("insurance_code", ""),
            insurance_name=row.get("insurance_name", ""),
        )


# ── Module-level singleton ──

_singleton: ICD10CNLoader | None = None
_singleton_lock = threading.Lock()


def get_loader() -> ICD10CNLoader:
    """Return the process-wide loader, loading on first call."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = ICD10CNLoader()
            _singleton.load()
        return _singleton


def reset_singleton() -> None:
    """For tests: drop the cached loader so the next get_loader() reloads from disk."""
    global _singleton
    with _singleton_lock:
        _singleton = None
