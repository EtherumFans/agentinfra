"""BGE-M3 local embedder — lazy-loaded sentence-transformers wrapper.

BAAI/bge-m3 is a multilingual embedding model with strong Chinese coverage.
We keep it local so the embeddings stay inside the hospital network
(``DataPolicy.allow_external_llm`` only constrains *external* LLM calls —
loading a local model is permitted).

Design:
  - Lazy load: the first embed() call downloads (~2.3 GB) and caches the
    model under ``data/medcoder/models/``. Subsequent boots reuse it.
  - Deterministic: encode with ``normalize_embeddings=True`` so inner
    product == cosine similarity. We do cosine via the inner product.
  - Batched: caller passes a list; we chunk at 32 to stay friendly to
    the GPU/CPU.
  - Single-process lock to avoid concurrent model loads.

The class is deliberately minimal — the rest of the medcoder pipeline
only needs ``embed(list[str]) -> list[list[float]]``.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Sequence

# E1.9 (2026-06-27): OMP runtime conflict suppression. faiss-cpu ships
# libomp140.x86_64.dll, torch (via mkl) ships libiomp5md.dll. Loading
# both in the same process triggers OMP Error #15 ("multiple copies of
# the OpenMP runtime") which aborts the process. MedCodER's retriever
# loads faiss AND may import torch (e.g. for fp16 dtype resolution), so
# we suppress the conflict. Set BEFORE the first torch import. No-op on
# platforms where this isn't relevant.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np

logger = logging.getLogger(__name__)

# Where the model is downloaded / cached. The build_medcoder_index.py script
# pre-populates this dir; embed() also falls back to the HF cache.
DEFAULT_MODEL_DIR = "data/medcoder/models"
MODEL_NAME = "BAAI/bge-m3"
EMBED_DIM = 1024
BATCH_SIZE = 32


class BGEEmbedder:
    """Thin wrapper around sentence_transformers for BGE-M3.

    The model is loaded once on first use and reused. If the local cache
    doesn't exist we try to download — failures surface to the caller
    who can decide whether to degrade (e.g., fall back to keyword RAG).
    """

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        model_dir: str = DEFAULT_MODEL_DIR,
        batch_size: int = BATCH_SIZE,
        device: str | None = None,
        torch_dtype: str | None = None,
        model_kwargs: dict | None = None,
        encode_kwargs: dict | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_dir = model_dir
        self.batch_size = batch_size
        # E1.9 (2026-06-27): memory knobs. fp16 load halves peak memory
        # (3-4 GB → 1.5-2 GB) and keeps the dev box viable for full
        # icoder_201 + ccl2026_val_100 eval. Defaults: device=cpu,
        # torch_dtype=float16. Both env-overridable via MEDCODER_BGE_*
        # so subprocess workers (Windows spawn inherits parent env)
        # get consistent settings without explicit plumbing.
        self.device = device or os.environ.get("MEDCODER_BGE_DEVICE", "cpu")
        self.torch_dtype = (
            torch_dtype or os.environ.get("MEDCODER_BGE_DTYPE", "float16")
        )
        # Store the dtype string in model_kwargs; resolve to torch.dtype
        # at load time (avoid ``import torch`` in __init__ — costs ~1s
        # per BGEEmbedder() and breaks under pytest's torch C-ext load
        # when other tests have already imported torch in a way that
        # confuses the loader).
        _mk: dict = dict(model_kwargs or {})
        # E1.10 (2026-06-28): use ``dtype`` (new name) instead of
        # ``torch_dtype`` (deprecated in sentence-transformers 3.x /
        # transformers 4.50+). The deprecated key still works but logs
        # a warning AND — under sentence-transformers 3.2.1 + Windows
        # — has been observed to NOT actually downcast weights, leaving
        # the model at fp32 (~2.3 GB on disk → 2.3 GB resident) which
        # then OOMs on 32-batch encode. The new ``dtype`` key is what
        # transformers passes to AutoModel.from_pretrained, which is
        # where the downcast actually happens.
        if "dtype" not in _mk and "torch_dtype" not in _mk and self.torch_dtype != "float32":
            _mk["dtype"] = self.torch_dtype  # string; resolved in _load()
        self.model_kwargs = _mk
        self.encode_kwargs = dict(encode_kwargs or {})
        self._model = None
        self._lock = threading.Lock()
        self._load_error: Exception | None = None

    @property
    def dim(self) -> int:
        return EMBED_DIM

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> Exception | None:
        return self._load_error

    def ensure_loaded(self) -> None:
        """Load the model if not already loaded. Safe to call concurrently."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            self._load()

    def _load(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as e:
            self._load_error = e
            raise RuntimeError(
                "sentence-transformers is not installed. "
                "Run `pip install -r requirements.txt` (includes sentence-transformers)."
            ) from e

        # Prefer the local cache dir if populated; otherwise let HF download.
        os.makedirs(self.model_dir, exist_ok=True)
        local_path = self.model_dir
        # If the dir has no model files, fall back to the canonical name so
        # sentence-transformers will use the standard HF cache location.
        if not _dir_has_model(local_path):
            local_path = self.model_name

        logger.info("Loading BGE-M3 from %s (device=%s, dtype=%s, this can take a few minutes on first call)",
                    local_path, self.device, self.torch_dtype)
        # Resolve string dtype → torch.dtype. sentence-transformers 3.x
        # expects a real torch.dtype; passing a string raises TypeError.
        # We resolve here (not in __init__) so tests that never call
        # ``_load()`` — i.e., inspecting default attributes — don't pay
        # the ~1s torch import cost. ``import torch`` happens only when
        # a real model load is triggered; tests that only inspect attrs
        # never trigger it (and so avoid the OMP runtime conflict with
        # faiss-cpu that some Windows + pytest combos hit).
        load_kwargs = dict(self.model_kwargs or {})
        # Resolve string dtype → torch.dtype. E1.10: prefer the new
        # ``dtype`` key; fall back to legacy ``torch_dtype`` if a
        # caller passed it explicitly (back-compat for any test that
        # hand-built BGEEmbedder with model_kwargs={"torch_dtype": ...}).
        if "dtype" in load_kwargs and isinstance(load_kwargs["dtype"], str):
            import torch  # type: ignore
            load_kwargs["dtype"] = getattr(torch, load_kwargs["dtype"])
        elif "torch_dtype" in load_kwargs and isinstance(load_kwargs["torch_dtype"], str):
            import torch  # type: ignore
            load_kwargs["torch_dtype"] = getattr(torch, load_kwargs["torch_dtype"])
        self._model = SentenceTransformer(
            local_path,
            cache_folder=self.model_dir,
            device=self.device,
            model_kwargs=load_kwargs or None,
        )
        # Sanity: dim must match.
        if getattr(self._model, "get_sentence_embedding_dimension", lambda: None)() not in (None, EMBED_DIM):
            actual = self._model.get_sentence_embedding_dimension()
            logger.warning("BGE-M3 dim mismatch: expected %d, got %d", EMBED_DIM, actual)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode ``texts`` into 1024-dim unit vectors (cosine = inner product).

        Empty / None inputs return a single zero vector — this keeps the
        downstream retriever simple (length always matches len(texts)).

        For large inputs prefer :meth:`embed_numpy` to avoid Python-list
        materialization (saves ~1 GB of overhead at 38k × 1024).
        """
        if not texts:
            return []
        arr = self.embed_numpy(texts)
        return arr.tolist()

    def embed_numpy(self, texts: Sequence[str]) -> np.ndarray:
        """Encode ``texts`` into a 2-D float32 array of shape (len(texts), dim).

        This is the memory-efficient path used by the FAISS index builder
        and the runtime retriever. Vectors are L2-normalized so inner
        product == cosine.
        """
        if not texts:
            return np.zeros((0, self.dim), dtype="float32")
        self.ensure_loaded()
        normalized = [(t or " ").strip() or " " for t in texts]
        encode_kwargs = dict(self.encode_kwargs)
        encode_kwargs.setdefault("batch_size", self.batch_size)
        encode_kwargs.setdefault("normalize_embeddings", True)
        encode_kwargs.setdefault("show_progress_bar", False)
        encode_kwargs.setdefault("convert_to_numpy", True)
        vectors = self._model.encode(  # type: ignore[union-attr]
            normalized,
            **encode_kwargs,
        )
        arr = np.asarray(vectors, dtype="float32")
        if arr.ndim != 2 or arr.shape[1] != self.dim:
            raise RuntimeError(
                f"Unexpected embedding shape {arr.shape}; expected (N, {self.dim})"
            )
        return np.ascontiguousarray(arr)

    def embed_one(self, text: str) -> list[float]:
        """Convenience: encode a single string and return the vector."""
        if not text:
            return [0.0] * self.dim
        arr = self.embed_numpy([text])
        return arr[0].tolist()


def _dir_has_model(path: str) -> bool:
    """Return True if ``path`` looks like a populated HF model cache directory."""
    if not os.path.isdir(path):
        return False
    # Common HF / sentence-transformers files that indicate a usable model.
    markers = ("config.json", "config_sentence_transformers.json", "modules.json", "model.safetensors", "pytorch_model.bin")
    return any(os.path.isfile(os.path.join(path, m)) for m in markers)
