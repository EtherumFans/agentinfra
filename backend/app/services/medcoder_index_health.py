"""MedCodER FAISS index health check.

M2.5 — Recover retrieval governance.

The MedCodER 5-stage pipeline silently degraded to Stage 1 LLM-only when
``data/medcoder/faiss.index`` was removed (2026-06-19). This module makes
that failure **loud and observable** at startup.

API:
    index_health_check(index_dir: str | Path) -> dict
        Returns a structured health report with the shape:
            {
              "status": "ok" | "degraded",
              "reason": str | None,
              "checks": {
                "faiss_exists": bool,
                "metadata_exists": bool,
                "faiss_loads": bool,
                "metadata_loads": bool,
                "ntotal_positive": bool,
                "dim_match": bool,
                "metadata_length_matches": bool,
              },
              "index_dir": str,
              "faiss_path": str,
              "metadata_path": str,
              "ntotal": int | None,
              "dim": int | None,
              "metadata_len": int | None,
            }

Design constraints (M2.5 user constraints):
  - NO silent continue: if ANY check fails, status="degraded" with a
    specific reason. Callers are expected to:
      1. log loudly (ERROR level) at startup
      2. store the report on ``app.state.medcoder_index_health``
      3. downstream calls (e.g. MCP ``search_icd``) read the report
         and return ``-32002 Retriever Unavailable`` instead of
         silently returning empty candidates
  - Checks are read-only — never writes to the index, never rebuilds
    automatically. Rebuild is a separate explicit operation
    (``scripts/build_medcoder_index.py``).
  - Pure function: no module-level state, no caching, no side effects
    on import. ``app/main.py`` calls it explicitly during startup.
"""

from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Expected dimension for BGE-M3. Centralized so tests + production
# agree on the value.
EXPECTED_DIM: int = 1024


# ── Public API ──


def index_health_check(
    index_dir: str | Path,
    *,
    faiss_filename: str = "faiss.index",
    metadata_filename: str = "metadata.pkl",
    expected_dim: int = EXPECTED_DIM,
) -> dict[str, Any]:
    """Run all checks against ``index_dir/faiss_filename`` and metadata.

    Returns the health report dict. Never raises — a broken index
    surfaces as ``status="degraded"`` with a descriptive reason.
    """
    index_dir = Path(index_dir)
    faiss_path = index_dir / faiss_filename
    metadata_path = index_dir / metadata_filename

    checks: dict[str, bool] = {
        "faiss_exists": False,
        "metadata_exists": False,
        "faiss_loads": False,
        "metadata_loads": False,
        "ntotal_positive": False,
        "dim_match": False,
        "metadata_length_matches": False,
    }
    ntotal: int | None = None
    dim: int | None = None
    metadata_len: int | None = None

    # 1. Existence checks (cheap; run first so we can short-circuit).
    checks["faiss_exists"] = faiss_path.is_file()
    checks["metadata_exists"] = metadata_path.is_file()

    if not checks["faiss_exists"]:
        return _degraded(
            index_dir, faiss_path, metadata_path, checks,
            ntotal=ntotal, dim=dim, metadata_len=metadata_len,
            reason=f"FAISS index not found at {faiss_path}",
        )

    if not checks["metadata_exists"]:
        return _degraded(
            index_dir, faiss_path, metadata_path, checks,
            ntotal=ntotal, dim=dim, metadata_len=metadata_len,
            reason=f"Metadata pickle not found at {metadata_path}",
        )

    # 2. Load FAISS index.
    try:
        import faiss  # type: ignore
    except ImportError:
        return _degraded(
            index_dir, faiss_path, metadata_path, checks,
            ntotal=ntotal, dim=dim, metadata_len=metadata_len,
            reason="faiss-cpu not installed (run `pip install faiss-cpu`)",
        )

    try:
        # E1.10 (2026-06-28): use IO_FLAG_MMAP to avoid Windows
        # std::bad_alloc on contiguous heap allocation. Health check
        # is the gate that decides whether smoke_recall runs at all,
        # so this MUST succeed in the same constrained memory
        # environments where retriever usage also matters.
        index = faiss.read_index(str(faiss_path), faiss.IO_FLAG_MMAP)
    except Exception as e:  # noqa: BLE001 — surface any load failure
        return _degraded(
            index_dir, faiss_path, metadata_path, checks,
            ntotal=ntotal, dim=dim, metadata_len=metadata_len,
            reason=f"FAISS index failed to load: {e}",
        )

    checks["faiss_loads"] = True
    ntotal = int(getattr(index, "ntotal", 0))
    dim = int(getattr(index, "d", 0))

    # 3. Load metadata pickle.
    try:
        with open(metadata_path, "rb") as f:
            meta = pickle.load(f)
    except Exception as e:  # noqa: BLE001
        return _degraded(
            index_dir, faiss_path, metadata_path, checks,
            ntotal=ntotal, dim=dim, metadata_len=metadata_len,
            reason=f"Metadata pickle failed to load: {e}",
        )

    checks["metadata_loads"] = True
    metadata_len = len(meta) if hasattr(meta, "__len__") else 0

    # 4. Anomaly checks.
    checks["ntotal_positive"] = ntotal > 0
    checks["dim_match"] = dim == expected_dim
    checks["metadata_length_matches"] = (
        metadata_len == ntotal and metadata_len > 0
    )

    if not checks["ntotal_positive"]:
        return _degraded(
            index_dir, faiss_path, metadata_path, checks,
            ntotal=ntotal, dim=dim, metadata_len=metadata_len,
            reason=f"FAISS ntotal={ntotal} (expected > 0) — empty or corrupt",
        )

    if not checks["dim_match"]:
        return _degraded(
            index_dir, faiss_path, metadata_path, checks,
            ntotal=ntotal, dim=dim, metadata_len=metadata_len,
            reason=(
                f"FAISS dim={dim} but expected {expected_dim} "
                "(BGE-M3) — wrong embedding model or stale index"
            ),
        )

    if not checks["metadata_length_matches"]:
        return _degraded(
            index_dir, faiss_path, metadata_path, checks,
            ntotal=ntotal, dim=dim, metadata_len=metadata_len,
            reason=(
                f"metadata_len={metadata_len} != FAISS ntotal={ntotal} "
                "— index and metadata are out of sync"
            ),
        )

    # 5. All checks passed.
    return {
        "status": "ok",
        "reason": None,
        "checks": checks,
        "index_dir": str(index_dir),
        "faiss_path": str(faiss_path),
        "metadata_path": str(metadata_path),
        "ntotal": ntotal,
        "dim": dim,
        "metadata_len": metadata_len,
    }


def _degraded(
    index_dir: Path,
    faiss_path: Path,
    metadata_path: Path,
    checks: dict[str, bool],
    *,
    ntotal: int | None,
    dim: int | None,
    metadata_len: int | None,
    reason: str,
) -> dict[str, Any]:
    """Helper — builds the degraded report dict."""
    return {
        "status": "degraded",
        "reason": reason,
        "checks": checks,
        "index_dir": str(index_dir),
        "faiss_path": str(faiss_path),
        "metadata_path": str(metadata_path),
        "ntotal": ntotal,
        "dim": dim,
        "metadata_len": metadata_len,
    }


# ── Helpers for downstream callers ──


def is_retriever_available(health: dict[str, Any]) -> bool:
    """True if the index is healthy enough to serve retrieval queries.

    Convenience for ``mcp/handlers/search_icd.py`` and any other
    caller that wants a boolean check.
    """
    return health.get("status") == "ok"


def is_icd9cm3_retriever_available(
    index_dir: str | Path,
    *,
    faiss_filename: str = "faiss_icd9cm3.index",
    metadata_filename: str = "metadata_icd9cm3.pkl",
) -> bool:
    """Convenience: check the ICD-9-CM-3 index. Separate file names from the
    ICD-10-CN index, so this just re-runs ``index_health_check`` with the
    right filenames."""
    h = index_health_check(
        index_dir, faiss_filename=faiss_filename, metadata_filename=metadata_filename,
    )
    return h["status"] == "ok"


__all__ = [
    "EXPECTED_DIM",
    "index_health_check",
    "is_retriever_available",
    "is_icd9cm3_retriever_available",
]
