"""Tests for ``app.services.medcoder_index_health`` — FAISS index health gate.

These tests cover the M2.5 governance contract: when retrieval assets are
missing or corrupt, the runtime MUST report ``status="degraded"`` rather
than silently passing empty results through MedCodER Stage 2.

Test matrix (per Phase A plan):
  1. ok            — both files present and well-formed
  2. missing faiss — only metadata exists
  3. missing meta  — only faiss exists
  4. ntotal=0      — empty index
  5. dim mismatch  — wrong embedding model

The tests are filesystem-driven (no fixture generator) so they can run
without rebuilding the real index. We synthesize tiny valid FAISS +
metadata artifacts in a tmp dir to exercise the happy path.
"""
from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

import pytest

# Make ``backend`` importable as a package root for ``app.*``.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.medcoder_index_health import (  # noqa: E402
    EXPECTED_DIM,
    index_health_check,
    is_icd9cm3_retriever_available,
    is_retriever_available,
)


def _write_valid_faiss(path: Path, ntotal: int = 4, dim: int = EXPECTED_DIM) -> None:
    """Write a tiny but valid FAISS IndexFlatIP."""
    import faiss
    import numpy as np

    index = faiss.IndexFlatIP(dim)
    if ntotal > 0:
        # Random unit vectors are fine for an existence test.
        rng = np.random.default_rng(42)
        vecs = rng.normal(size=(ntotal, dim)).astype("float32")
        # Normalize each row so cosine sims are bounded.
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        vecs = vecs / np.clip(norms, 1e-9, None)
        index.add(np.ascontiguousarray(vecs))
    faiss.write_index(index, str(path))


def _write_valid_metadata(path: Path, ntotal: int) -> None:
    meta = [
        {
            "code": f"T{i:03d}",
            "name_cn": f"测试码 {i}",
            "name_en": f"Test code {i}",
            "chapter_no": 1,
            "chapter_name": "测试章",
            "chapter_range": "T00-T99",
            "category_code": f"T{i:02d}",
            "clinical_category": "test",
        }
        for i in range(ntotal)
    ]
    with open(path, "wb") as f:
        pickle.dump(meta, f)


def test_ok(tmp_path: Path) -> None:
    """Happy path — both files present, valid, length matches."""
    _write_valid_faiss(tmp_path / "faiss.index", ntotal=4)
    _write_valid_metadata(tmp_path / "metadata.pkl", ntotal=4)
    report = index_health_check(tmp_path)
    assert report["status"] == "ok", report
    assert report["ntotal"] == 4
    assert report["dim"] == EXPECTED_DIM
    assert report["metadata_len"] == 4
    assert report["checks"]["faiss_exists"] is True
    assert report["checks"]["metadata_exists"] is True
    assert report["checks"]["faiss_loads"] is True
    assert report["checks"]["metadata_loads"] is True
    assert report["checks"]["ntotal_positive"] is True
    assert report["checks"]["dim_match"] is True
    assert report["checks"]["metadata_length_matches"] is True
    assert is_retriever_available(report) is True


def test_missing_faiss(tmp_path: Path) -> None:
    """Only metadata present — must report degraded, not silently ok."""
    _write_valid_metadata(tmp_path / "metadata.pkl", ntotal=4)
    report = index_health_check(tmp_path)
    assert report["status"] == "degraded"
    assert report["reason"] is not None and "FAISS index not found" in report["reason"]
    assert report["checks"]["faiss_exists"] is False
    assert report["ntotal"] is None
    assert is_retriever_available(report) is False


def test_missing_metadata(tmp_path: Path) -> None:
    """Only faiss present — must report degraded."""
    _write_valid_faiss(tmp_path / "faiss.index", ntotal=4)
    report = index_health_check(tmp_path)
    assert report["status"] == "degraded"
    assert report["reason"] is not None and "Metadata pickle not found" in report["reason"]
    assert report["checks"]["metadata_exists"] is False
    assert is_retriever_available(report) is False


def test_ntotal_zero(tmp_path: Path) -> None:
    """Empty index (0 vectors) — must report degraded, ntotal_positive=False."""
    _write_valid_faiss(tmp_path / "faiss.index", ntotal=0)
    _write_valid_metadata(tmp_path / "metadata.pkl", ntotal=0)
    report = index_health_check(tmp_path)
    assert report["status"] == "degraded"
    assert report["reason"] is not None and "ntotal=0" in report["reason"]
    assert report["checks"]["faiss_loads"] is True
    assert report["checks"]["ntotal_positive"] is False
    assert is_retriever_available(report) is False


def test_dim_mismatch(tmp_path: Path) -> None:
    """Wrong embedding model (dim != 1024) — must report degraded."""
    _write_valid_faiss(tmp_path / "faiss.index", ntotal=4, dim=768)
    _write_valid_metadata(tmp_path / "metadata.pkl", ntotal=4)
    report = index_health_check(tmp_path)
    assert report["status"] == "degraded"
    assert report["reason"] is not None and "dim=768" in report["reason"]
    assert report["checks"]["faiss_loads"] is True
    assert report["checks"]["dim_match"] is False
    assert is_retriever_available(report) is False


def test_metadata_length_mismatch(tmp_path: Path) -> None:
    """Index and metadata out of sync — must report degraded."""
    _write_valid_faiss(tmp_path / "faiss.index", ntotal=4)
    _write_valid_metadata(tmp_path / "metadata.pkl", ntotal=2)
    report = index_health_check(tmp_path)
    assert report["status"] == "degraded"
    assert report["reason"] is not None and "out of sync" in report["reason"]
    assert report["checks"]["metadata_length_matches"] is False
    assert is_retriever_available(report) is False


def test_icd9cm3_helper(tmp_path: Path) -> None:
    """is_icd9cm3_retriever_available uses correct filenames and gates on status."""
    _write_valid_faiss(tmp_path / "faiss_icd9cm3.index", ntotal=2)
    _write_valid_metadata(tmp_path / "metadata_icd9cm3.pkl", ntotal=2)
    assert is_icd9cm3_retriever_available(tmp_path) is True

    # Remove only the ICD-10 files — the helper should still be OK
    # (it only checks ICD-9-CM-3).
    (tmp_path / "faiss_icd9cm3.index").unlink()
    assert is_icd9cm3_retriever_available(tmp_path) is False


def test_empty_index_dir(tmp_path: Path) -> None:
    """Brand-new empty dir — both files missing, degraded."""
    report = index_health_check(tmp_path)
    assert report["status"] == "degraded"
    assert report["checks"]["faiss_exists"] is False
    assert report["checks"]["metadata_exists"] is False
    assert is_retriever_available(report) is False