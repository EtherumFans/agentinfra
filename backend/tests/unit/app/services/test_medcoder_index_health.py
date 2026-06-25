"""M2.5 — index_health_check() unit tests.

5 cases (per plan):
  1. test_health_check_ok                  — all checks pass
  2. test_health_check_missing_faiss       — faiss.index absent
  3. test_health_check_missing_metadata    — metadata.pkl absent
  4. test_health_check_ntotal_zero         — empty FAISS (corrupt)
  5. test_health_check_dim_mismatch        — wrong embedding dim

Each case writes a small synthetic FAISS index + metadata into a
``tmp_path`` so we don't depend on the real ``data/medcoder/``.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import pytest

from app.services.medcoder_index_health import (
    EXPECTED_DIM,
    index_health_check,
    is_retriever_available,
    is_icd9cm3_retriever_available,
)


def _build_fake_index(path: Path, ntotal: int, dim: int) -> None:
    """Write a minimal FAISS IndexFlatIP with ``ntotal`` zero vectors.

    We don't need real embeddings — the health check only inspects
    ``ntotal`` and ``d``. Zero vectors are valid FAISS entries.
    """
    import numpy as np
    import faiss  # type: ignore

    arr = np.zeros((ntotal, dim), dtype="float32")
    index = faiss.IndexFlatIP(dim)
    if ntotal > 0:
        index.add(arr)
    faiss.write_index(index, str(path))


def _build_fake_metadata(path: Path, n: int) -> None:
    """Write a metadata pickle aligned with the FAISS index."""
    meta = [{"code": f"X{i:05d}", "name_cn": f"测试码{i}"} for i in range(n)]
    with open(path, "wb") as f:
        pickle.dump(meta, f)


# ── OK case ──


def test_health_check_ok(tmp_path: Path):
    """All checks pass when both files exist and align."""
    faiss_path = tmp_path / "faiss.index"
    meta_path = tmp_path / "metadata.pkl"
    _build_fake_index(faiss_path, ntotal=10, dim=EXPECTED_DIM)
    _build_fake_metadata(meta_path, n=10)

    h = index_health_check(tmp_path)
    assert h["status"] == "ok"
    assert h["reason"] is None
    assert h["ntotal"] == 10
    assert h["dim"] == EXPECTED_DIM
    assert h["metadata_len"] == 10
    # All checks True
    assert all(h["checks"].values())
    assert is_retriever_available(h)


# ── Missing FAISS ──


def test_health_check_missing_faiss(tmp_path: Path):
    """FAISS index absent → degraded with specific reason."""
    meta_path = tmp_path / "metadata.pkl"
    _build_fake_metadata(meta_path, n=10)

    h = index_health_check(tmp_path)
    assert h["status"] == "degraded"
    assert "FAISS index not found" in h["reason"]
    assert h["checks"]["faiss_exists"] is False
    assert h["checks"]["metadata_exists"] is True
    # Short-circuit: downstream checks stay False
    assert h["checks"]["faiss_loads"] is False
    assert h["checks"]["ntotal_positive"] is False
    assert h["ntotal"] is None
    assert not is_retriever_available(h)


# ── Missing metadata ──


def test_health_check_missing_metadata(tmp_path: Path):
    """Metadata pickle absent → degraded with specific reason."""
    faiss_path = tmp_path / "faiss.index"
    _build_fake_index(faiss_path, ntotal=10, dim=EXPECTED_DIM)
    # No metadata.pkl

    h = index_health_check(tmp_path)
    assert h["status"] == "degraded"
    assert "Metadata pickle not found" in h["reason"]
    assert h["checks"]["faiss_exists"] is True
    assert h["checks"]["metadata_exists"] is False
    assert h["ntotal"] is None  # short-circuit before load
    assert h["dim"] is None
    assert not is_retriever_available(h)


# ── ntotal = 0 ──


def test_health_check_ntotal_zero(tmp_path: Path):
    """Empty FAISS (ntotal=0) → degraded as 'empty or corrupt'."""
    faiss_path = tmp_path / "faiss.index"
    meta_path = tmp_path / "metadata.pkl"
    _build_fake_index(faiss_path, ntotal=0, dim=EXPECTED_DIM)
    _build_fake_metadata(meta_path, n=0)

    h = index_health_check(tmp_path)
    assert h["status"] == "degraded"
    assert "ntotal=0" in h["reason"]
    assert "empty or corrupt" in h["reason"]
    assert h["checks"]["faiss_loads"] is True
    assert h["checks"]["ntotal_positive"] is False
    assert h["ntotal"] == 0


# ── dim mismatch ──


def test_health_check_dim_mismatch(tmp_path: Path):
    """FAISS dim != EXPECTED_DIM (1024) → degraded with reason about wrong model."""
    faiss_path = tmp_path / "faiss.index"
    meta_path = tmp_path / "metadata.pkl"
    _build_fake_index(faiss_path, ntotal=10, dim=384)  # wrong dim
    _build_fake_metadata(meta_path, n=10)

    h = index_health_check(tmp_path)
    assert h["status"] == "degraded"
    assert "dim=384" in h["reason"]
    assert f"expected {EXPECTED_DIM}" in h["reason"]
    assert "BGE-M3" in h["reason"]
    assert h["checks"]["faiss_loads"] is True
    assert h["checks"]["dim_match"] is False
    assert h["dim"] == 384


# ── Bonus: metadata/ntotal mismatch ──


def test_health_check_metadata_length_mismatch(tmp_path: Path):
    """Metadata length != ntotal → degraded 'out of sync'."""
    faiss_path = tmp_path / "faiss.index"
    meta_path = tmp_path / "metadata.pkl"
    _build_fake_index(faiss_path, ntotal=10, dim=EXPECTED_DIM)
    _build_fake_metadata(meta_path, n=5)  # mismatch

    h = index_health_check(tmp_path)
    assert h["status"] == "degraded"
    assert "out of sync" in h["reason"]
    assert "metadata_len=5" in h["reason"]
    assert "ntotal=10" in h["reason"]


# ── ICD-9-CM-3 helper ──


def test_is_icd9cm3_retriever_available_ok(tmp_path: Path):
    """``is_icd9cm3_retriever_available`` checks the icd9cm3 filenames."""
    faiss_path = tmp_path / "faiss_icd9cm3.index"
    meta_path = tmp_path / "metadata_icd9cm3.pkl"
    _build_fake_index(faiss_path, ntotal=5, dim=EXPECTED_DIM)
    _build_fake_metadata(meta_path, n=5)

    assert is_icd9cm3_retriever_available(tmp_path) is True


def test_is_icd9cm3_retriever_available_degraded(tmp_path: Path):
    """If the icd9cm3 index is missing, helper returns False."""
    # No files at all
    assert is_icd9cm3_retriever_available(tmp_path) is False
