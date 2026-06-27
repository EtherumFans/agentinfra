"""Tests for MedCodERICD9CM3Retriever — BGE-M3 + FAISS over ICD-9-CM-3.

E1.3 (2026-06-27): closes the procedure-side retrieval gap. Mirrors
``test_medcoder_retriever.py`` but uses the ICD-9-CM-3 index filenames
(``faiss_icd9cm3.index`` / ``metadata_icd9cm3.pkl``) and skips the
catalog filter (no ``ICD9CM3Loader`` exists yet — audit gap #3).

Uses a fake embedder so the test runs without 2.3 GB BGE-M3 or a built
13,617-code index. A real icd9cm3 index, if present in ``data/medcoder/``,
is exercised by the smoke test in ``test_medcoder_icd9cm3_smoke.py``
(deferred to E1.4 — wall time ~30s).
"""
from __future__ import annotations

import asyncio
import os
import pickle
import sys

import numpy as np
import pytest

# Make backend root importable
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# ── Fixtures ──


class _FakeEmbedder:
    """Deterministic unit vector keyed by a hash of the text.

    Same shape as the diagnosis retriever test fake — keeps the two
    test files in sync (if you change one, change the other).
    """

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
    """Drop-in fake: returns ranks 0..ntotal-1 with descending scores."""

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
                scores[i, j] = 1.0 - j * 0.01
                idxs[i, j] = j
            if k > self.ntotal:
                idxs[i, self.ntotal:] = -1
                scores[i, self.ntotal:] = 0.0
        return scores, idxs


@pytest.fixture
def tmp_icd9cm3_index_dir(tmp_path):
    """Build a tiny ICD-9-CM-3 fixture under tmp_path.

    5 fake procedure codes spanning two chapters. Mirrors the real
    metadata shape produced by ``scripts/build_medcoder_icd9cm3_index.py``.
    """
    metadata = [
        {"code": "45.2301", "name_cn": "结肠镜检查", "name_en": "Colonoscopy",
         "category": "diagnostic", "chapter_no": "第1章",
         "chapter_name": "操作与介入", "chapter_range": "00.00-99.99",
         "is_extended": False, "insurance_code": "",
         "is_insurance_gray": False},
        {"code": "45.2302", "name_cn": "结肠镜下活检", "name_en": "Colonoscopic biopsy",
         "category": "diagnostic", "chapter_no": "第1章",
         "chapter_name": "操作与介入", "chapter_range": "00.00-99.99",
         "is_extended": False, "insurance_code": "",
         "is_insurance_gray": False},
        {"code": "45.4100", "name_cn": "结肠息肉切除术", "name_en": "Polypectomy of colon",
         "category": "therapeutic", "chapter_no": "第1章",
         "chapter_name": "操作与介入", "chapter_range": "00.00-99.99",
         "is_extended": True, "insurance_code": "45.4100",
         "is_insurance_gray": False},
        {"code": "88.0101", "name_cn": "腹部CT", "name_en": "Abdominal CT",
         "category": "diagnostic", "chapter_no": "第1章",
         "chapter_name": "操作与介入", "chapter_range": "00.00-99.99",
         "is_extended": False, "insurance_code": "",
         "is_insurance_gray": False},
        {"code": "96.0401", "name_cn": "气管插管", "name_en": "Endotracheal intubation",
         "category": "therapeutic", "chapter_no": "第1章",
         "chapter_name": "操作与介入", "chapter_range": "00.00-99.99",
         "is_extended": False, "insurance_code": "",
         "is_insurance_gray": False},
    ]
    (tmp_path / "metadata_icd9cm3.pkl").write_bytes(pickle.dumps(metadata))

    try:
        import faiss  # type: ignore
    except ImportError:
        pytest.skip("faiss-cpu not installed")
    rng = np.random.default_rng(seed=321)
    arr = rng.standard_normal((5, 1024)).astype("float32")
    arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
    idx = faiss.IndexFlatIP(1024)
    idx.add(arr)
    faiss.write_index(idx, str(tmp_path / "faiss_icd9cm3.index"))
    return tmp_path


@pytest.fixture
def retriever(tmp_icd9cm3_index_dir):
    from icoder_runtime.providers.medical_coding import medcoder_retriever as ret_mod
    # Permissive loader: synthetic test fixtures use codes not in the
    # real catalog. E1.5 catalog filter is exercised by
    # ``test_catalog_filter_drops_ghost_codes``.
    class _PermissiveLoader:
        def has(self, code: str) -> bool:
            return True
    return ret_mod.MedCodERICD9CM3Retriever(
        index_dir=str(tmp_icd9cm3_index_dir),
        embedder=_FakeEmbedder(),
        icd9cm3_loader=_PermissiveLoader(),
    )


# ── Loading ──


class TestIcd9cm3RetrieverLoading:
    def test_loads_index_and_metadata(self, retriever):
        retriever.ensure_loaded()
        assert retriever.is_loaded
        assert retriever.stats.ntotal == 5
        assert retriever.stats.dim == 1024

    def test_health_check_reports_status(self, retriever):
        retriever.ensure_loaded()
        h = retriever.health_check()
        assert h["retriever"] == "MedCodERICD9CM3Retriever"
        assert h["loaded"] is True
        assert h["ntotal"] == 5
        assert h["dim"] == 1024
        assert "load_error" in h

    def test_load_error_on_missing_index(self, tmp_path):
        from icoder_runtime.providers.medical_coding import medcoder_retriever as ret_mod
        empty = tmp_path / "empty"
        empty.mkdir()
        r = ret_mod.MedCodERICD9CM3Retriever(
            index_dir=str(empty), embedder=_FakeEmbedder(),
        )
        with pytest.raises(FileNotFoundError):
            r.ensure_loaded()
        assert r.load_error is not None


# ── Retrieval ──


class TestIcd9cm3Retrieval:
    def test_retrieve_returns_candidate_code_typed(self, retriever):
        from official_agents.medical_coding.schema import CandidateCode
        cands = retriever.retrieve_sync("结肠镜", top_k=3)
        # Random FAISS projections don't guarantee a specific rank,
        # so just verify the surface.
        for c in cands:
            assert isinstance(c, CandidateCode)
            assert c.code
            assert c.name
            assert c.source == "retrieve"
            assert c.chapter  # populated from metadata chapter_name

    def test_retrieve_caps_at_top_k(self, retriever):
        cands = retriever.retrieve_sync("结肠镜", top_k=2)
        assert len(cands) == 2

    def test_retrieve_caps_at_index_size(self, retriever):
        cands = retriever.retrieve_sync("结肠镜", top_k=100)
        assert len(cands) == 5

    def test_empty_query_returns_empty(self, retriever):
        assert retriever.retrieve_sync("", top_k=5) == []
        assert retriever.retrieve_sync("   ", top_k=5) == []

    def test_catalog_filter_drops_ghost_codes(self, tmp_path):
        """E1.5: catalog compliance filter drops codes not in
        ``icd9cm3_loader``. Mirrors the diagnosis retriever's filter.
        Test pins that ``icd9cm3_loader=None`` still allows the filter
        to be disabled (synthetic indexes, FAISS-only behavior).
        """
        metadata = [
            {"code": "45.2301", "name_cn": "结肠镜检查", "name_en": "Colonoscopy",
             "category": "diagnostic", "chapter_no": "第1章",
             "chapter_name": "操作与介入", "chapter_range": "00.00-99.99"},
            {"code": "ZZ.9999", "name_cn": "幽灵", "name_en": "Ghost",
             "category": "", "chapter_no": "", "chapter_name": "",
             "chapter_range": ""},
        ]
        (tmp_path / "metadata_icd9cm3.pkl").write_bytes(pickle.dumps(metadata))
        import faiss
        rng = np.random.default_rng(seed=99)
        arr = rng.standard_normal((2, 1024)).astype("float32")
        arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        idx = faiss.IndexFlatIP(1024)
        idx.add(arr)
        faiss.write_index(idx, str(tmp_path / "faiss_icd9cm3.index"))

        from icoder_runtime.providers.medical_coding import medcoder_retriever as ret_mod

        # Stub loader: only ``45.2301`` is in the catalog. Ghost code
        # ``ZZ.9999`` is filtered out.
        class _StubLoader:
            def has(self, code: str) -> bool:
                return code == "45.2301"

        r = ret_mod.MedCodERICD9CM3Retriever(
            index_dir=str(tmp_path),
            embedder=_FakeEmbedder(),
            icd9cm3_loader=_StubLoader(),
        )
        r.ensure_loaded()
        cands = r.retrieve_sync("test", top_k=5)
        codes = [c.code for c in cands]
        assert "ZZ.9999" not in codes
        assert "45.2301" in codes

    def test_permissive_loader_lets_ghost_codes_through(self, tmp_path):
        """E1.5: callers control filtering by the loader's ``has()``
        behavior. A permissive loader (always True) effectively
        disables the filter — used in tests where raw FAISS ranking
        is what's under test.
        """
        metadata = [
            {"code": "45.2301", "name_cn": "结肠镜检查", "name_en": "Colonoscopy",
             "category": "diagnostic", "chapter_no": "第1章",
             "chapter_name": "操作与介入", "chapter_range": "00.00-99.99"},
            {"code": "ZZ.9999", "name_cn": "幽灵", "name_en": "Ghost",
             "category": "", "chapter_no": "", "chapter_name": "",
             "chapter_range": ""},
        ]
        (tmp_path / "metadata_icd9cm3.pkl").write_bytes(pickle.dumps(metadata))
        import faiss
        rng = np.random.default_rng(seed=99)
        arr = rng.standard_normal((2, 1024)).astype("float32")
        arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-12
        idx = faiss.IndexFlatIP(1024)
        idx.add(arr)
        faiss.write_index(idx, str(tmp_path / "faiss_icd9cm3.index"))

        from icoder_runtime.providers.medical_coding import medcoder_retriever as ret_mod

        class _PermissiveLoader:
            def has(self, code: str) -> bool:
                return True

        r = ret_mod.MedCodERICD9CM3Retriever(
            index_dir=str(tmp_path),
            embedder=_FakeEmbedder(),
            icd9cm3_loader=_PermissiveLoader(),
        )
        r.ensure_loaded()
        cands = r.retrieve_sync("test", top_k=5)
        codes = [c.code for c in cands]
        # Permissive loader — both codes survive.
        assert "ZZ.9999" in codes
        assert "45.2301" in codes

    def test_retrieve_async_returns_same_as_sync(self, retriever):
        sync_cands = retriever.retrieve_sync("结肠镜", top_k=3)
        async_cands = asyncio.run(retriever.retrieve_async("结肠镜", top_k=3))
        assert [c.code for c in sync_cands] == [c.code for c in async_cands]

    def test_expand_synonyms_arg_accepted(self, retriever):
        """``expand_synonyms`` is accepted for API parity with the
        diagnosis retriever; the 9cm3 retriever ignores it (no
        synonym loader). This test pins that contract.
        """
        cands_with = retriever.retrieve_sync("结肠镜", top_k=2, expand_synonyms=True)
        cands_without = retriever.retrieve_sync("结肠镜", top_k=2, expand_synonyms=False)
        assert [c.code for c in cands_with] == [c.code for c in cands_without]


# ── Stats ──


class TestIcd9cm3RetrieverStats:
    def test_last_query_recorded(self, retriever):
        retriever.retrieve_sync("结肠镜", top_k=1)
        assert retriever.stats.last_query == "结肠镜"
        assert isinstance(retriever.stats.last_top_score, float)


# ── Strategy integration ──


class TestIcd9cm3Stage2Procedure:
    def test_stage2_retrieve_procedure_returns_stage2_result(self, tmp_icd9cm3_index_dir, monkeypatch):
        from icoder_runtime.providers.medical_coding import medcoder_strategy as strat_mod
        # Force the strategy to use the in-process procedure retriever
        # (subprocess would also work, but for unit tests we keep it
        # in-process to avoid the multi-process startup cost).
        monkeypatch.setattr(strat_mod.os, "name", "posix", raising=False)
        monkeypatch.setenv("MEDCODER_SUBPROCESS", "0")

        from icoder_runtime.providers.medical_coding.medcoder_retriever import (
            MedCodERICD9CM3Retriever,
        )
        proc_ret = MedCodERICD9CM3Retriever(
            index_dir=str(tmp_icd9cm3_index_dir),
            embedder=_FakeEmbedder(),
        )

        s = strat_mod.MedCodERStrategy(procedure_retriever=proc_ret)
        result = asyncio.run(s.stage2_retrieve_procedure("结肠镜", top_k=3))
        assert not result.degraded
        assert result.error_code == strat_mod.STAGE2_OK
        assert len(result.candidates) == 3
        for c in result.candidates:
            assert c.source == "retrieve"
            assert c.code

    def test_stage2_retrieve_procedure_empty_input_ok(self):
        from icoder_runtime.providers.medical_coding import medcoder_strategy as strat_mod
        s = strat_mod.MedCodERStrategy()
        result = asyncio.run(s.stage2_retrieve_procedure(""))
        assert not result.degraded
        assert result.error_code == strat_mod.STAGE2_OK
        assert result.candidates == []

    def test_stage2_retrieve_procedure_no_retriever_degraded(self):
        from icoder_runtime.providers.medical_coding import medcoder_strategy as strat_mod
        s = strat_mod.MedCodERStrategy()
        # Force the retriever to be None (simulates "creation failed")
        s._proc_retriever = None
        s._proc_retriever_lazy = False
        result = asyncio.run(s.stage2_retrieve_procedure("结肠镜"))
        assert result.degraded
        assert result.error_code == strat_mod.STAGE2_RETRIEVER_UNAVAILABLE
        assert result.candidates == []


# ── E1.4: _populate_procedures (procedure RAG sidecar) ────────────


from official_agents.medical_coding.schema import MedicalCodingOutputSchema  # noqa: E402


class TestPopulateProcedures:
    """E1.4: ``MedCodERStrategy._populate_procedures`` consumes
    ``extraction.procedure_mentions`` and populates
    ``MedicalCodingOutputSchema.procedures`` from ICD-9-CM-3 RAG."""

    def _make_strategy_with_fake_proc_ret(self, tmp_icd9cm3_index_dir):
        from icoder_runtime.providers.medical_coding import medcoder_strategy as strat_mod
        from icoder_runtime.providers.medical_coding.medcoder_retriever import (
            MedCodERICD9CM3Retriever,
        )
        proc_ret = MedCodERICD9CM3Retriever(
            index_dir=str(tmp_icd9cm3_index_dir),
            embedder=_FakeEmbedder(),
        )
        s = strat_mod.MedCodERStrategy(procedure_retriever=proc_ret)
        return s

    def test_no_mentions_leaves_procedures_empty(self, tmp_icd9cm3_index_dir):
        s = self._make_strategy_with_fake_proc_ret(tmp_icd9cm3_index_dir)
        out = MedicalCodingOutputSchema()
        asyncio.run(s._populate_procedures(out, []))
        assert out.procedures == []

    def test_populates_one_procedure_per_mention(self, tmp_icd9cm3_index_dir):
        s = self._make_strategy_with_fake_proc_ret(tmp_icd9cm3_index_dir)
        out = MedicalCodingOutputSchema()
        asyncio.run(s._populate_procedures(out, ["结肠镜检查", "气管插管"]))
        # Random FAISS projections may map both mentions to the same
        # top-1 (deterministic hash → same vec → same nearest), so
        # dedup is on code. Verify each ProcedureEntry has the right shape.
        assert len(out.procedures) >= 1
        assert len(out.procedures) <= 2  # dedup
        for p in out.procedures:
            assert p.code
            assert p.description
            assert 0.0 <= p.confidence <= 1.0
            assert p.category == "therapeutic"
            assert p.evidence  # the mention is recorded

    def test_dedup_on_duplicate_codes(self, tmp_icd9cm3_index_dir):
        """Two mentions mapping to the same top-1 code → 1 ProcedureEntry."""
        s = self._make_strategy_with_fake_proc_ret(tmp_icd9cm3_index_dir)
        out = MedicalCodingOutputSchema()
        # Same mention twice — deterministic embedder will produce
        # identical vectors and identical top-1.
        asyncio.run(s._populate_procedures(out, ["结肠镜", "结肠镜"]))
        codes = [p.code for p in out.procedures]
        assert len(codes) == len(set(codes)), \
            f"duplicate codes survived: {codes}"

    def test_caps_at_10_mentions(self, tmp_icd9cm3_index_dir):
        s = self._make_strategy_with_fake_proc_ret(tmp_icd9cm3_index_dir)
        out = MedicalCodingOutputSchema()
        mentions = [f"procedure_{i}" for i in range(20)]
        asyncio.run(s._populate_procedures(out, mentions))
        # Cap is 10; with random projections + dedup, fewer entries.
        assert len(out.procedures) <= 10

    def test_failed_retriever_leaves_procedures_empty(self):
        """If procedure retriever raises, output.procedures stays empty."""
        from icoder_runtime.providers.medical_coding import medcoder_strategy as strat_mod

        class _BrokenProcRet:
            async def retrieve_async(self, text, top_k=None):
                raise RuntimeError("BGE-M3 cold load failure")

        s = strat_mod.MedCodERStrategy(procedure_retriever=_BrokenProcRet())
        out = MedicalCodingOutputSchema()
        asyncio.run(s._populate_procedures(out, ["结肠镜"]))
        assert out.procedures == []


# ── Subprocess wrapper smoke (deferred) ───────────────────────────
#
# Full subprocess test lives in
# ``test_medcoder_icd9cm3_subprocess.py`` (deferred to E1.4 — the
# wrapper is exercised by the existing test_medcoder_retriever_worker
# patterns; the factory injection is the only new surface and is
# unit-testable without spawning a process).
