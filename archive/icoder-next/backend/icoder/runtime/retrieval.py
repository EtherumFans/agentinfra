"""BGE-M3 + FAISS retrieval — the production seam for Stage-3 candidate generation.

The deterministic runtime retrieves candidates by ICD synonym search over the catalog
(``CodingExpert.search``). This module is the upgrade path: semantic retrieval with BGE-M3
embeddings + a prebuilt FAISS index over the 37,897-code national catalog (MedCodER Stage 2).

It is **lazy and degrade-safe by construction**:
  - nothing heavy is imported at module import;
  - ``retrieve`` checks for the prebuilt index *first* and raises ``RetrievalUnavailable``
    before importing ``sentence-transformers`` / ``faiss`` — so a misconfigured or
    index-less deployment falls back to catalog search and **never** downloads the 2.3GB
    BGE-M3 model or hits the network as a side effect.

Pairs with the DeepSeek extraction seam in ``gateway.py``: both are reachable by config
(``retriever_from_env`` / ``LLMGateway.from_env``) but unexercised in the offline slice,
which runs on the deterministic provider + catalog search.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, runtime_checkable

ENV_INDEX_DIR = "ICODER_MEDCODER_INDEX_DIR"
DEFAULT_MODEL = "BAAI/bge-m3"


class RetrievalUnavailable(RuntimeError):
    """Raised when the FAISS index or BGE-M3 deps are absent. Callers degrade to catalog search."""


@runtime_checkable
class Retriever(Protocol):
    name: str

    def retrieve(self, term: str, k: int = 20) -> list[dict]: ...


class BgeM3FaissRetriever:
    name = "bge-m3+faiss"

    def __init__(self, index_dir: str, model_name: str = DEFAULT_MODEL):
        self.index_dir = index_dir
        self.model_name = model_name
        self._ready = False
        self._index = None
        self._meta = None
        self._model = None

    def _ensure(self) -> None:
        if self._ready:
            return
        idx = Path(self.index_dir)
        index_file, meta_file = idx / "faiss.index", idx / "metadata.pkl"
        # Cheap path check BEFORE any heavy import — guarantees the unavailable path never
        # imports sentence-transformers (i.e. never triggers a model download).
        if not index_file.is_file() or not meta_file.is_file():
            raise RetrievalUnavailable(
                f"FAISS index not built at {self.index_dir!r} "
                "(run scripts/build_medcoder_index.py); falling back to catalog search"
            )
        try:
            import pickle

            import faiss
            from sentence_transformers import SentenceTransformer
        except ImportError as e:  # deps not installed in this deployment
            raise RetrievalUnavailable(
                f"retrieval deps unavailable ({e}); falling back to catalog search"
            ) from e
        self._index = faiss.read_index(str(index_file))
        with open(meta_file, "rb") as f:
            self._meta = pickle.load(f)
        model_dir = idx / "models"
        self._model = SentenceTransformer(str(model_dir) if model_dir.is_dir() else self.model_name)
        self._ready = True

    def retrieve(self, term: str, k: int = 20) -> list[dict]:
        self._ensure()
        vec = self._model.encode([term], normalize_embeddings=True)
        scores, ids = self._index.search(vec, k)
        hits: list[dict] = []
        for score, i in zip(scores[0].tolist(), ids[0].tolist()):
            if i < 0:
                continue
            m = self._meta[i]
            hits.append({"code": m["code"], "display": m.get("display", ""), "score": float(score)})
        return hits


def retriever_from_env() -> BgeM3FaissRetriever | None:
    """A retriever when ``ICODER_MEDCODER_INDEX_DIR`` is configured, else None (catalog search)."""
    d = os.environ.get(ENV_INDEX_DIR)
    return BgeM3FaissRetriever(d) if d else None
