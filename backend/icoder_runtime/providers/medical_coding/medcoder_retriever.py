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

import asyncio
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


# ── Subprocess worker (C4) ──
#
# Windows can't safely run BGE-M3 (sentence-transformers + OpenMP) and
# httpx async I/O in the same Python process — the OS kills the
# interpreter with a C-level segfault. The worker runs in a fresh
# subprocess that owns the FAISS index + embedder in isolation; the
# parent process only sends request tuples and reads back candidates.
# See tests/test_services/test_medcoder_retriever_worker.py.

import multiprocessing as _mp  # local alias to avoid name shadowing in callers
from typing import Any, Optional


class MedCodERRetrieverWorker:
    """Subprocess entry point for MedCodER retrieval.

    Protocol: parent pushes ``(req_id, disease, top_k)`` onto ``queue_in``.
    Worker pushes back ``(req_id, candidates)`` on success, or
    ``(req_id, {"error": repr(exc)})`` on failure. Push ``None`` to
    ``queue_in`` to shut down the worker cleanly.

    The worker eagerly calls ``ensure_loaded()`` once so that a missing
    index or FAISS import error is reported back to the parent as
    ``("__startup_error__", "FileNotFoundError(...)")`` instead of
    hanging on the first retrieve.

    Pass a pre-built ``retriever`` to inject a fake one in tests; the
    retriever must be picklable and expose ``ensure_loaded()`` and
    ``retrieve_sync(disease, top_k=...)`` methods.
    """

    STARTUP_ERROR_ID = "__startup_error__"

    @staticmethod
    def run(
        queue_in,
        queue_out,
        index_dir: str = DEFAULT_INDEX_DIR,
        retriever: Optional[Any] = None,
    ) -> None:
        if retriever is None:
            retriever = MedCodERRetriever(index_dir=index_dir)

        try:
            retriever.ensure_loaded()
        except Exception as e:
            try:
                queue_out.put((MedCodERRetrieverWorker.STARTUP_ERROR_ID, repr(e)))
            except Exception:
                pass
            return

        while True:
            try:
                msg = queue_in.get()
            except (EOFError, OSError):
                # Parent process died — exit cleanly
                return
            if msg is None:
                # Sentinel from parent: shut down
                return
            req_id, disease_or_bytes, top_k = msg[0], msg[1], (msg[2] if len(msg) > 2 else None)
            # The parent always encodes the disease as UTF-8 bytes before
            # queuing (see ``_retrieve_via_queue``), so decode back to str
            # here. The legacy str-only path is kept for forward-compat.
            if isinstance(disease_or_bytes, bytes):
                disease = disease_or_bytes.decode("utf-8", errors="replace")
            else:
                disease = disease_or_bytes
            # Probe requests bypass FAISS entirely — the worker just
            # acknowledges liveness with an empty list. This avoids two
            # failure modes: (1) the probe's fake disease text producing
            # a junk candidate that collides with the parent's first real
            # response when the probe times out and the parent resets
            # ``_next_id`` to 0, and (2) BGE-M3 doing a wasted embedding
            # pass for a non-disease string.
            if disease == "__probe__":
                logger.debug(
                    "MedCodERRetrieverWorker: probe ack req_id=%s", req_id,
                )
                queue_out.put((req_id, []))
                continue
            try:
                cands = retriever.retrieve_sync(disease, top_k=top_k)
                logger.debug(
                    "MedCodERRetrieverWorker: req_id=%s disease=%r -> %d cands",
                    req_id, disease, len(cands),
                )
                queue_out.put((req_id, cands))
            except Exception as e:
                # Send an error envelope; keep the loop alive so the
                # parent can continue sending requests.
                queue_out.put((req_id, {"error": repr(e)}))


# ── Subprocess client (C5) ──
#
# SubprocessMedCodERRetriever is the parent-process side of the
# isolation scheme. It owns the worker Process and translates the
# public MedCodERRetriever surface (``retrieve_async`` /
# ``retrieve_sync``) into request/response queue traffic. Callers
# (HybridCodingAdapter) can drop it in wherever they currently use
# MedCodERRetriever; no other code change is required.
#
# Selection: in ``hybrid_adapter._get_retriever``, choose the
# subprocess wrapper when ``MEDCODER_SUBPROCESS=1`` is set in the
# environment, or when running on Windows (``os.name == 'nt'``) so
# the default behavior on the affected platform is the safer one.


class SubprocessMedCodERRetriever:
    """Subprocess-isolated retriever with the same surface as MedCodERRetriever.

    Every call to ``retrieve_async`` (or ``retrieve_sync``) round-trips
    through a worker process that owns the BGE-M3 / FAISS imports.
    The parent never imports those modules, so the Windows segfault
    that occurs when sentence-transformers and httpx share a process
    is avoided.

    Args:
        index_dir: directory containing ``faiss.index`` + ``metadata.pkl``.
        timeout:   seconds to wait for a single response. Default 30s.
    """

    def __init__(self, index_dir: str = DEFAULT_INDEX_DIR, timeout: float = 30.0, probe_timeout: float = 10.0):
        self.index_dir = index_dir
        self.timeout = timeout
        self._q_in: _mp.Queue = _mp.Queue()
        self._q_out: _mp.Queue = _mp.Queue()
        self._proc: _mp.Process = _mp.Process(
            target=MedCodERRetrieverWorker.run,
            args=(self._q_in, self._q_out, index_dir),
            daemon=True,
        )
        self._proc.start()
        self._next_id = 0
        self._lock = threading.Lock()
        self._closed = False
        # C7: Probe the worker at startup so the parent can report
        # "index ready / not ready" without waiting for the first
        # real request. If the worker died during ensure_loaded
        # (missing FAISS, missing index file, OOM), the probe
        # returns False and is_ready reflects that.
        self._probe_ok: bool = self._probe(probe_timeout)

    def _probe(self, probe_timeout: float) -> bool:
        """Synchronous startup probe: send a benign retrieve, wait for response.

        Returns True if the worker responded (even with an empty list,
        which is the legitimate "no candidates" response), False on
        timeout, req_id mismatch, error envelope, or worker death.

        On any failure path the probe drains both queues and resets
        ``_next_id`` to 0 so that the first real ``retrieve_async``
        call allocates ``r0`` and the worker (which is still blocked
        on ``ensure_loaded`` followed by ``queue_in.get``) lines up
        with the parent's counter. Without this reset a slow
        ``ensure_loaded`` (BGE-M3 model load + FAISS index load can
        exceed the 10s probe_timeout) causes the worker's eventual
        probe response to land on the parent's NEXT request —
        manifesting as ``req_id mismatch (got r0, want r1)``.
        """
        if not self._proc.is_alive():
            return False
        req_id = self._alloc_id()
        try:
            self._q_in.put((req_id, "__probe__", 1))
        except Exception:
            return self._probe_failed_reset()
        try:
            resp_id, payload = self._q_out.get(timeout=probe_timeout)
        except Exception:
            return self._probe_failed_reset()
        if resp_id != req_id:
            # The probe response (or the prior startup_error envelope)
            # arrived after timeout / under a different id. Drain and
            # reset so real requests start clean.
            return self._probe_failed_reset()
        if isinstance(payload, dict) and "error" in payload:
            return self._probe_failed_reset()
        return True

    def _probe_failed_reset(self) -> bool:
        """Best-effort recovery after a probe failure.

        Drains BOTH queues (the probe request may still be in q_in,
        which the worker would process and reply to — that reply would
        then collide with our first real call's response because both
        share ``_next_id == 0`` after the reset). Resets ``_next_id``
        to 0 and ``_next_probe_id`` so real calls and any subsequent
        probes do not collide. Returns ``False`` so the caller can
        record ``_probe_ok = False`` for ``is_ready``.
        """
        try:
            for _ in range(64):
                try:
                    self._q_in.get_nowait()
                except Exception:
                    break
        except Exception:
            pass
        try:
            for _ in range(64):
                try:
                    self._q_out.get_nowait()
                except Exception:
                    break
        except Exception:
            pass
        with self._lock:
            self._next_id = 0
            self._next_probe_id = 0
        return False

    def _alloc_id(self) -> str:
        with self._lock:
            rid = f"r{self._next_id}"
            self._next_id += 1
            return rid

    async def retrieve_async(
        self,
        disease: str,
        top_k: int | None = None,
        expand_synonyms: bool = True,
    ) -> list:
        """Async wrapper that round-trips through the worker.

        Delegates to the synchronous :meth:`_retrieve_via_queue` via
        ``run_in_executor`` so the queue-drain logic is shared between
        the async and inline code paths. This avoids the previous
        "req_id mismatch" bug where the worker's late probe response
        was consumed as the parent's real reply.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._retrieve_via_queue, disease, top_k,
        )

    def retrieve_sync(
        self,
        disease: str,
        top_k: int | None = None,
        expand_synonyms: bool = True,
    ) -> list:
        """Synchronous wrapper. In a running event loop, falls back to inline."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        if loop.is_running():
            return self._retrieve_inline(disease, top_k, expand_synonyms)
        return loop.run_until_complete(
            self.retrieve_async(disease, top_k, expand_synonyms)
        )

    def _retrieve_inline(self, disease: str, top_k: int | None, expand_synonyms: bool) -> list:
        return self._retrieve_via_queue(disease, top_k)

    def _retrieve_via_queue(self, disease: str, top_k: int | None) -> list:
        """Synchronous queue round-trip core shared by ``retrieve_async``
        and ``_retrieve_inline``.

        Sends the request, then drains responses until one matches the
        expected ``req_id``. Tolerates stale responses left in the
        queue by a previous probe whose worker reply arrived after the
        parent's ``probe_timeout`` — without this drain the parent's
        real call would consume the worker's late probe reply and
        either fail the ``resp_id == req_id`` check or, worse, accept
        the late probe reply as if it were our own result (causing
        ``req_id mismatch (got r0, want r1)`` or garbage candidates
        returning from a real disease query).
        """
        import time as _time
        if self._closed or not self._proc.is_alive():
            return []
        req_id = self._alloc_id()
        # Send the disease as UTF-8 bytes — see docstring for rationale.
        payload = (req_id, (disease or "").encode("utf-8"), top_k)
        try:
            self._q_in.put(payload)
        except Exception as e:
            logger.warning("SubprocessMedCodERRetriever: send failed: %s", e)
            return []

        deadline = _time.monotonic() + self.timeout
        while True:
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                logger.warning(
                    "SubprocessMedCodERRetriever: timeout waiting for %s",
                    req_id,
                )
                return []
            try:
                resp_id, candidates = self._q_out.get(timeout=remaining)
            except Exception as e:
                logger.warning("SubprocessMedCodERRetriever: receive failed: %s", e)
                return []
            if resp_id == req_id:
                if isinstance(candidates, dict) and "error" in candidates:
                    logger.warning(
                        "SubprocessMedCodERRetriever: worker error: %s",
                        candidates["error"],
                    )
                    return []
                return candidates or []
            logger.debug(
                "SubprocessMedCodERRetriever: drained stale response %s (want %s)",
                resp_id, req_id,
            )

    def close(self) -> None:
        """Send the shutdown sentinel and join the worker. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            self._q_in.put(None)
        except Exception:
            pass
        if self._proc.is_alive():
            self._proc.join(timeout=5)
        if self._proc.is_alive():
            logger.warning("SubprocessMedCodERRetriever: terminating worker")
            self._proc.terminate()
            self._proc.join(timeout=2)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    @property
    def is_alive(self) -> bool:
        return self._proc.is_alive()

    @property
    def is_ready(self) -> bool:
        """True if the worker responded to the startup probe AND is still alive.

        Cached at construction time: ``_probe_ok`` records the
        startup handshake result. ``_proc.is_alive()`` catches
        later deaths. Used by ``/api/health`` to report index
        readiness without blocking the event loop.
        """
        return self._probe_ok and self._proc.is_alive()

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None
