"""MedCodER retriever — BGE-M3 + FAISS over the iCoDerA ICD-10-CN catalog.

The retriever is stage 2 of the MedCodER pipeline (Baksi et al., NAACL 2025
Industry Track). For a free-text disease mention it returns the top-K ICD
codes from a dense index of the 37,897-row ICD-10-CN catalog.

Pipeline:
  disease_text
    └─► synonym expansion (iCoDerA synonym_map.term_index)
    └─► BGE-M3 embed (single vector — query is short)
    └─► FAISS top-20 cosine over IndexFlatIP
    └─► filter through icd10cn_loader.code_dict (catalog compliance)
    └─► CandidateCode list (score = inner product = cosine)

The retriever is **lazy-loaded** — the FAISS index is read on the first
``retrieve_async()`` call so cold-start stays fast.

Usage::

    from icoder_runtime.providers.medical_coding.medcoder_retriever import (
        MedCodERRetriever,
    )
    r = MedCodERRetriever(index_dir="data/medcoder")
    cands = await r.retrieve_async("心衰", top_k=20)
    # cands is list[CandidateCode]
"""
from __future__ import annotations

import logging
import os
import pickle
import threading
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)

DEFAULT_INDEX_DIR = "data/medcoder"
INDEX_FILENAME = "faiss.index"
META_FILENAME = "metadata.pkl"
DEFAULT_TOP_K = 20


@dataclass
class RetrieverStats:
    """Introspection data for health check / debugging."""
    loaded: bool = False
    ntotal: int = 0
    dim: int = 0
    source: str = ""
    last_query: str = ""
    last_top_score: float = 0.0
    last_filtered_count: int = 0


class MedCodERRetriever:
    """Top-K ICD retriever backed by BGE-M3 + FAISS IndexFlatIP.

    The index is loaded on first use (``ensure_loaded()``) and cached for
    subsequent calls. Thread-safe initialization.

    Args:
        index_dir: directory containing ``faiss.index`` + ``metadata.pkl``.
        embedder: a BGEEmbedder-compatible object (defaults to a fresh one).
        icd_loader: ICD10CNLoader-compatible object (defaults to ``get_loader()``).
        default_top_k: default top-K if not specified per query.
    """

    def __init__(
        self,
        index_dir: str = DEFAULT_INDEX_DIR,
        embedder=None,
        icd_loader=None,
        default_top_k: int = DEFAULT_TOP_K,
    ):
        self.index_dir = index_dir
        self.default_top_k = default_top_k
        self._embedder = embedder
        self._icd_loader = icd_loader
        self._lock = threading.Lock()
        self._loaded = False
        self._index = None
        self._metadata: list[dict] = []
        self._stats = RetrieverStats()
        self._load_error: Exception | None = None

    # ── Public API ──

    @property
    def stats(self) -> RetrieverStats:
        return RetrieverStats(**self._stats.__dict__)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def load_error(self) -> Exception | None:
        return self._load_error

    def ensure_loaded(self) -> None:
        """Load the FAISS index + metadata if not already. Idempotent."""
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load()

    async def retrieve_async(
        self,
        disease: str,
        top_k: int | None = None,
        expand_synonyms: bool = True,
    ) -> list:
        """Retrieve top-K ICD candidate codes for a disease mention.

        Returns a list of ``CandidateCode`` (from the official schema) with
        ``source="retrieve"``. The list is empty for blank / unknown input.
        """
        from official_agents.medical_coding.schema import CandidateCode

        text = (disease or "").strip()
        if not text:
            return []

        self.ensure_loaded()
        if self._index is None:
            logger.warning("MedCodERRetriever: index not loaded, returning empty list")
            return []

        k = min(top_k or self.default_top_k, self._index.ntotal)

        # Build the query text (with optional synonym expansion)
        query_text = text
        if expand_synonyms:
            syns = self._get_synonyms(text)
            if syns:
                query_text = f"{text} | " + " | ".join(syns[:3])

        # Embed + search
        embedder = self._get_embedder()
        try:
            q_vec = embedder.embed_one(query_text)
        except Exception as e:
            logger.error("MedCodERRetriever: embed failed: %s", e)
            return []

        try:
            import faiss  # type: ignore
            import numpy as np  # type: ignore
            arr = np.asarray([q_vec], dtype="float32")
            scores, idxs = self._index.search(arr, k)
        except Exception as e:
            logger.error("MedCodERRetriever: faiss search failed: %s", e)
            return []

        flat_scores = scores[0].tolist() if hasattr(scores, "tolist") else list(scores[0])
        flat_idxs = idxs[0].tolist() if hasattr(idxs, "tolist") else list(idxs[0])

        # Filter through catalog (drop codes not in iCoDerA loader)
        loader = self._get_loader()
        out: list[CandidateCode] = []
        for score, idx in zip(flat_scores, flat_idxs):
            if idx < 0 or idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            code = meta.get("code", "")
            if not code:
                continue
            if loader is not None and not loader.has(code):
                continue
            out.append(CandidateCode(
                code=code,
                name=meta.get("name_cn", ""),
                score=float(score),
                chapter=meta.get("chapter_name", ""),
                source="retrieve",
            ))

        # Update stats (best effort)
        self._stats.last_query = text
        self._stats.last_top_score = out[0].score if out else 0.0
        self._stats.last_filtered_count = len(out)
        return out

    def retrieve_sync(
        self,
        disease: str,
        top_k: int | None = None,
        expand_synonyms: bool = True,
    ) -> list:
        """Synchronous wrapper for tests / non-async contexts.

        The retriever is I/O-bound on embed + FAISS, both of which are CPU;
        use ``retrieve_async`` from the runtime, this in tests.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        if loop.is_running():
            # Fall back to a direct call: encode + search without await
            return self._retrieve_inline(disease, top_k, expand_synonyms)
        return loop.run_until_complete(self.retrieve_async(disease, top_k, expand_synonyms))

    def _retrieve_inline(self, disease: str, top_k: int | None, expand_synonyms: bool) -> list:
        """In-process retrieve without asyncio (for nested-loop tests)."""
        from official_agents.medical_coding.schema import CandidateCode

        text = (disease or "").strip()
        if not text:
            return []
        self.ensure_loaded()
        if self._index is None:
            return []
        k = min(top_k or self.default_top_k, self._index.ntotal)
        query_text = text
        if expand_synonyms:
            syns = self._get_synonyms(text)
            if syns:
                query_text = f"{text} | " + " | ".join(syns[:3])
        embedder = self._get_embedder()
        try:
            q_vec = embedder.embed_one(query_text)
        except Exception:
            return []
        try:
            import faiss  # noqa: F401  (type check)
            import numpy as np
            arr = np.asarray([q_vec], dtype="float32")
            scores, idxs = self._index.search(arr, k)
        except Exception:
            return []
        loader = self._get_loader()
        out: list[CandidateCode] = []
        for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
            if idx < 0 or idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            code = meta.get("code", "")
            if not code:
                continue
            if loader is not None and not loader.has(code):
                continue
            out.append(CandidateCode(
                code=code, name=meta.get("name_cn", ""),
                score=float(score), chapter=meta.get("chapter_name", ""),
                source="retrieve",
            ))
        return out

    def health_check(self) -> dict:
        return {
            "retriever": "MedCodERRetriever",
            "loaded": self._loaded,
            "ntotal": self._stats.ntotal,
            "dim": self._stats.dim,
            "source": self._stats.source,
            "load_error": str(self._load_error) if self._load_error else None,
        }

    # ── Internals ──

    def _get_embedder(self):
        if self._embedder is None:
            from .embedding_bge_m3 import BGEEmbedder
            self._embedder = BGEEmbedder()
        return self._embedder

    def _get_loader(self):
        if self._icd_loader is None:
            from app.services.icd10cn_loader import get_loader
            self._icd_loader = get_loader()
        return self._icd_loader

    def _get_synonyms(self, text: str) -> list[str]:
        """Best-effort synonym expansion via the ICD-10-CN loader."""
        loader = self._get_loader()
        if loader is None:
            return []
        try:
            return loader.synonyms_for(text, max_synonyms=3)
        except Exception:
            return []

    def _load(self) -> None:
        try:
            import faiss  # type: ignore
        except ImportError as e:
            self._load_error = e
            raise RuntimeError(
                "faiss-cpu not installed. Run `pip install faiss-cpu`."
            ) from e

        index_path = os.path.join(self.index_dir, INDEX_FILENAME)
        meta_path = os.path.join(self.index_dir, META_FILENAME)
        if not os.path.isfile(index_path):
            self._load_error = FileNotFoundError(index_path)
            raise FileNotFoundError(
                f"FAISS index not found at {index_path}. "
                f"Run `python scripts/build_medcoder_index.py` first."
            )
        if not os.path.isfile(meta_path):
            self._load_error = FileNotFoundError(meta_path)
            raise FileNotFoundError(f"metadata.pkl not found at {meta_path}")

        logger.info("MedCodERRetriever: loading FAISS index from %s", index_path)
        self._index = faiss.read_index(index_path)
        with open(meta_path, "rb") as f:
            self._metadata = pickle.load(f)
        self._stats.loaded = True
        self._stats.ntotal = self._index.ntotal
        self._stats.dim = self._index.d
        self._stats.source = index_path
        self._loaded = True
        logger.info("MedCodERRetriever: loaded ntotal=%d dim=%d", self._index.ntotal, self._index.d)

        # Sanity: ntotal should match metadata length
        if self._index.ntotal != len(self._metadata):
            logger.warning(
                "MedCodERRetriever: index ntotal=%d != metadata len=%d",
                self._index.ntotal, len(self._metadata),
            )
