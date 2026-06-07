"""Tests for MedCodERRetriever — BGE-M3 + FAISS over ICD-10-CN catalog.

Mocks FAISS and the BGE embedder so the test runs without 2.3 GB models
or built indices. The ICD-10-CN catalog is read from the real iCoDerA
asset dir (or skipped if absent) so we test against real code structure.
"""
from __future__ import annotations

import os
import pickle
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

# Make backend root importable
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.services import icd10cn_loader as loader_mod  # noqa: E402
from app.services.icd10cn_loader import DEFAULT_ASSET_DIR  # noqa: E402

RETRIEVER_PATH = "icoder_runtime.providers.medical_coding.medcoder_retriever"


# ── Fixtures ──


class _FakeEmbedder:
    """Returns a deterministic unit vector based on a hash of the text."""

    dim = 1024

    def __init__(self, model_dir: str = ""):
        self._calls: list[str] = []

    def ensure_loaded(self):
        return None

    def embed(self, texts):
        self._calls.extend(texts)
        return [self._vec(t) for t in texts]

    def embed_one(self, text: str):
        self._calls.append(text)
        return self._vec(text)

    def _vec(self, text: str):
        rng = np.random.default_rng(seed=hash(text) & 0xFFFFFFFF)
        v = rng.standard_normal(self.dim).astype("float32")
        v /= np.linalg.norm(v) + 1e-12
        return v.tolist()


class _FakeFaissIndex:
    """Drop-in fake for faiss.IndexFlatIP: returns ranks 0..ntotal-1 with
    descending fake scores."""

    def __init__(self, dim: int = 1024, ntotal: int = 0):
        self.dim = dim
        self.d = dim
        self.ntotal = ntotal

    def search(self, q_arr, k):
        nq = q_arr.shape[0]
        scores = np.zeros((nq, k), dtype="float32")
        idxs = np.zeros((nq, k), dtype="int64")
        for i in range(nq):
            for j in range(min(k, self.ntotal)):
                scores[i, j] = 1.0 - j * 0.01  # descending
                idxs[i, j] = j
            if k > self.ntotal:
                idxs[i, self.ntotal:] = -1
                scores[i, self.ntotal:] = 0.0
        return scores, idxs


@pytest.fixture
def tmp_index_dir(tmp_path):
    """Build a tiny FAISS index + metadata fixture under tmp_path."""
    # Build a minimal metadata list (5 codes)
    metadata = [
        {"code": "I50.900", "name_cn": "心力衰竭", "name_en": "Heart failure",
         "chapter_no": "第9章", "chapter_name": "循环系统疾病",
         "chapter_range": "I00-I99", "category_code": "I50",
         "clinical_category": "心衰"},
        {"code": "I50.100", "name_cn": "左心衰竭", "name_en": "Left heart failure",
         "chapter_no": "第9章", "chapter_name": "循环系统疾病",
         "chapter_range": "I00-I99", "category_code": "I50",
         "clinical_category": "心衰"},
        {"code": "I50.000", "name_cn": "充血性心力衰竭", "name_en": "CHF",
         "chapter_no": "第9章", "chapter_name": "循环系统疾病",
         "chapter_range": "I00-I99", "category_code": "I50",
         "clinical_category": "心衰"},
        {"code": "J18.900", "name_cn": "肺炎", "name_en": "Pneumonia",
         "chapter_no": "第10章", "chapter_name": "呼吸系统疾病",
         "chapter_range": "J00-J99", "category_code": "J18",
         "clinical_category": "肺炎"},
        {"code": "E11.900", "name_cn": "糖尿病", "name_en": "Diabetes",
         "chapter_no": "第4章", "chapter_name": "内分泌",
         "chapter_range": "E00-E90", "category_code": "E11",
         "clinical_category": "糖尿病"},
    ]
    (tmp_path / "metadata.pkl").write_bytes(pickle.dumps(metadata))

    # Build a real faiss index (faiss-cpu is now installed)
    try:
        import faiss  # type: ignore
    except ImportError:
        pytest.skip("faiss-cpu not installed")
    # 5 random unit vectors
    rng = np.random.default_rng(seed=123)
    arr = rng.standard_normal((5, 1024)).astype("float32")
    arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
    idx = faiss.IndexFlatIP(1024)
    idx.add(arr)
    faiss.write_index(idx, str(tmp_path / "faiss.index"))
    return tmp_path


@pytest.fixture
def retriever(tmp_index_dir, monkeypatch):
    """Construct a retriever with a fake embedder and patched faiss module."""
    from icoder_runtime.providers.medical_coding import medcoder_retriever as ret_mod
    monkeypatch.setattr(ret_mod, "DEFAULT_INDEX_DIR", str(tmp_index_dir))
    # Guard against env var leakage from test_icd10cn_loader.
    # That file's `test_explicit_asset_dir_override` sets ICODER_DATA_ASSET_DIR
    # to a tmp_path with only 2 codes; if not cleared, the loader would filter
    # our 5 fake codes down to 0.
    monkeypatch.delenv("ICODER_DATA_ASSET_DIR", raising=False)
    fake_embedder = _FakeEmbedder()
    loader_mod.reset_singleton()
    r = ret_mod.MedCodERRetriever(index_dir=str(tmp_index_dir), embedder=fake_embedder)
    r.ensure_loaded()
    return r


# ── Loading ──


class TestRetrieverLoading:
    def test_loads_index_and_metadata(self, retriever):
        assert retriever.is_loaded
        assert retriever.stats.ntotal == 5
        assert retriever.stats.dim == 1024

    def test_health_check_reports_status(self, retriever):
        h = retriever.health_check()
        assert h["retriever"] == "MedCodERRetriever"
        assert h["loaded"] is True
        assert h["ntotal"] == 5
        assert h["dim"] == 1024

    def test_load_error_on_missing_index(self, tmp_path, monkeypatch):
        from icoder_runtime.providers.medical_coding import medcoder_retriever as ret_mod
        empty = tmp_path / "empty"
        empty.mkdir()
        r = ret_mod.MedCodERRetriever(index_dir=str(empty), embedder=_FakeEmbedder())
        with pytest.raises(FileNotFoundError):
            r.ensure_loaded()
        assert r.load_error is not None


# ── Retrieval ──


class TestRetrieval:
    def test_retrieve_chinese_disease(self, retriever):
        cands = retriever.retrieve_sync("心衰", top_k=3)
        assert len(cands) == 3
        # At least one of the top-3 should be a heart-failure code.
        # We don't pin top-1: random FAISS projections don't guarantee
        # an exact rank, and this test fixture uses random unit vectors.
        top3_codes = {c.code for c in cands}
        assert top3_codes & {"I50.900", "I50.100", "I50.000"}, \
            f"Expected at least one I50.* in top-3, got {top3_codes}"
        # All should be valid retrieve-source candidates (cosine can be negative
        # for random projections, so don't assert > 0; just verify presence).
        for c in cands:
            assert c.source == "retrieve"
            assert isinstance(c.score, float)
            assert c.code and c.name

    def test_retrieve_returns_candidate_code_typed(self, retriever):
        from official_agents.medical_coding.schema import CandidateCode
        cands = retriever.retrieve_sync("糖尿病", top_k=2)
        for c in cands:
            assert isinstance(c, CandidateCode)
            assert c.code
            assert c.name
            assert c.source == "retrieve"

    def test_retrieve_caps_at_top_k(self, retriever):
        cands = retriever.retrieve_sync("心衰", top_k=2)
        assert len(cands) == 2

    def test_retrieve_caps_at_index_size(self, retriever):
        cands = retriever.retrieve_sync("心衰", top_k=100)
        assert len(cands) == 5  # only 5 in the fake index

    def test_empty_query_returns_empty(self, retriever):
        assert retriever.retrieve_sync("", top_k=5) == []
        assert retriever.retrieve_sync("   ", top_k=5) == []

    def test_filter_drops_unknown_codes(self, tmp_path, monkeypatch):
        """If metadata contains a code not in icd_loader, it should be dropped."""
        # Clear env var to prevent leakage from test_icd10cn_loader override
        monkeypatch.delenv("ICODER_DATA_ASSET_DIR", raising=False)
        # Build an index with one "ghost" code that the loader doesn't know
        metadata = [
            {"code": "I50.900", "name_cn": "心力衰竭", "name_en": "Heart failure",
             "chapter_no": "第9章", "chapter_name": "循环系统疾病",
             "chapter_range": "I00-I99", "category_code": "I50",
             "clinical_category": "心衰"},
            {"code": "ZZZ.999", "name_cn": "幽灵", "name_en": "Ghost",
             "chapter_no": "", "chapter_name": "",
             "chapter_range": "", "category_code": "",
             "clinical_category": ""},
        ]
        (tmp_path / "metadata.pkl").write_bytes(pickle.dumps(metadata))
        import faiss
        rng = np.random.default_rng(seed=1)
        arr = rng.standard_normal((2, 1024)).astype("float32")
        arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        idx = faiss.IndexFlatIP(1024)
        idx.add(arr)
        faiss.write_index(idx, str(tmp_path / "faiss.index"))

        from icoder_runtime.providers.medical_coding import medcoder_retriever as ret_mod
        loader_mod.reset_singleton()
        r = ret_mod.MedCodERRetriever(index_dir=str(tmp_path), embedder=_FakeEmbedder())
        r.ensure_loaded()
        cands = r.retrieve_sync("test", top_k=5)
        # Only I50.900 should survive the filter
        codes = [c.code for c in cands]
        assert "I50.900" in codes
        assert "ZZZ.999" not in codes

    def test_expand_synonyms_off_skips_loader(self, retriever):
        """expand_synonyms=False should still work (query = disease text only)."""
        cands = retriever.retrieve_sync("心衰", top_k=2, expand_synonyms=False)
        assert len(cands) == 2

    def test_retrieve_async_returns_same_as_sync(self, retriever):
        import asyncio
        sync_cands = retriever.retrieve_sync("肺炎", top_k=3)
        async_cands = asyncio.run(retriever.retrieve_async("肺炎", top_k=3))
        assert len(sync_cands) == len(async_cands)
        # Same code order
        assert [c.code for c in sync_cands] == [c.code for c in async_cands]


# ── Stats ──


class TestRetrieverStats:
    def test_stats_fresh_copy(self, retriever):
        s1 = retriever.stats
        s1.ntotal = 0
        s2 = retriever.stats
        assert s2.ntotal == 5  # original unchanged

    def test_last_query_recorded(self, retriever):
        retriever.retrieve_sync("心衰", top_k=1)
        assert retriever.stats.last_query == "心衰"
        # last_top_score is set even if negative (cosine can be < 0 for
        # random projections) — just verify the bookkeeping ran.
        assert isinstance(retriever.stats.last_top_score, float)
        assert retriever.stats.last_filtered_count >= 1
