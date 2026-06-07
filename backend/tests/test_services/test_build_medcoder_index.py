"""Tests for build_medcoder_index.py — FAISS index build for MedCodER.

Mocks the BGE-M3 embedder and FAISS so the test runs without 2.3 GB
model download. Verifies the orchestration: catalog load → embed →
shape check → index build → metadata write.
"""
from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Make backend root importable
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

import scripts.build_medcoder_index as build_mod  # noqa: E402


# ── Text builder ──


class TestBuildTextForEmbedding:
    def test_includes_code_name_and_synonyms(self):
        entry = SimpleNamespace(
            code="I50.900",
            name_cn="心力衰竭",
            name_en="Heart failure",
            synonyms_cn=["心衰", "充血性心力衰竭", "CHF"],
            synonyms_en=["heart failure", "cardiac failure"],
        )
        text = build_mod._build_text_for_embedding(entry)
        assert text.startswith("I50.900")
        assert "心力衰竭" in text
        assert "Heart failure" in text
        assert "心衰" in text
        # Caps cn at 3, en at 2
        assert "充血性心力衰竭" in text
        assert "CHF" in text
        assert "cardiac failure" in text

    def test_handles_empty_synonyms(self):
        entry = SimpleNamespace(
            code="X00.000",
            name_cn="测试",
            name_en="",
            synonyms_cn=[],
            synonyms_en=[],
        )
        text = build_mod._build_text_for_embedding(entry)
        assert text == "X00.000 测试"

    def test_dedupes_against_name(self):
        entry = SimpleNamespace(
            code="X01",
            name_cn="疾病名",
            name_en="Disease",
            synonyms_cn=["疾病名", "另一个"],  # "疾病名" == name_cn
            synonyms_en=[],
        )
        text = build_mod._build_text_for_embedding(entry)
        # "疾病名" should appear only once
        assert text.count("疾病名") == 1


# ── End-to-end (mocked) ─


class _FakeEmbedder:
    """Stand-in for BGEEmbedder: returns random unit vectors of fixed dim."""

    dim = 1024

    def __init__(self, model_dir: str = ""):
        self._calls = []

    def ensure_loaded(self):
        return None

    def embed(self, texts):
        self._calls.append(list(texts))
        n = len(texts)
        rng = np.random.default_rng(seed=42)
        v = rng.standard_normal((n, self.dim)).astype("float32")
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
        return v.tolist()


def _fake_faiss_module(fake_index):
    """Return a fake faiss module whose IndexFlatIP() yields ``fake_index``."""
    fake = MagicMock()
    fake.IndexFlatIP = MagicMock(return_value=fake_index)

    def _write_index(index, path):
        # Actually write a stub file so .stat() works downstream
        Path(path).write_bytes(b"FAISS_FAKE_INDEX")

    fake.write_index = MagicMock(side_effect=_write_index)
    return fake


def test_end_to_end_with_mocks(tmp_path, monkeypatch):
    """Full pipeline: load → embed (mocked) → write index + metadata."""
    # Tiny fake asset dir with 3 codes
    import json
    asset = tmp_path / "asset"
    asset.mkdir()
    cat = {
        "_meta": {"total_codes": 3},
        "chapters": {"I00-I99": {"chapter_no": "第9章", "chapter_name": "循环系统疾病"}},
        "codes": [
            {"code": "I50.900", "name_cn": "心力衰竭", "name_en": "Heart failure",
             "synonyms_cn": ["心衰"], "synonyms_en": [],
             "chapter_range": "I00-I99", "chapter_no": "第9章", "chapter_name": "循环系统疾病",
             "category_code": "I50", "clinical_category": "心衰", "is_extended": False,
             "is_dagger_asterisk": False, "is_generated_category": False,
             "is_insurance_gray": False},
            {"code": "J18.900", "name_cn": "肺炎", "name_en": "Pneumonia",
             "synonyms_cn": [], "synonyms_en": [],
             "chapter_range": "J00-J99", "chapter_no": "第10章", "chapter_name": "呼吸系统疾病",
             "category_code": "J18", "clinical_category": "肺炎", "is_extended": False,
             "is_dagger_asterisk": False, "is_generated_category": False,
             "is_insurance_gray": False},
            {"code": "E11.900", "name_cn": "糖尿病", "name_en": "Diabetes",
             "synonyms_cn": ["DM"], "synonyms_en": [],
             "chapter_range": "E00-E90", "chapter_no": "第4章", "chapter_name": "内分泌",
             "category_code": "E11", "clinical_category": "糖尿病", "is_extended": False,
             "is_dagger_asterisk": False, "is_generated_category": False,
             "is_insurance_gray": False},
        ],
    }
    syn = {
        "_meta": {"total_synonyms": 0},
        "synonyms": {},
        "term_index": {},
    }
    (asset / "icd10cn_code_catalog.json").write_text(json.dumps(cat), encoding="utf-8")
    (asset / "icd10cn_synonym_map.json").write_text(json.dumps(syn), encoding="utf-8")

    out = tmp_path / "out"
    out.mkdir()

    # Mock the embedder
    fake_embedder = _FakeEmbedder()

    # Mock faiss: capture ntotal, dim on add
    fake_index = MagicMock()
    fake_index.ntotal = 0

    def _add(arr):
        fake_index.ntotal = arr.shape[0]
        fake_index.dim = arr.shape[1]
    fake_index.add = MagicMock(side_effect=_add)

    fake_faiss = _fake_faiss_module(fake_index)

    # Patch BGEEmbedder + faiss + ICD10CNLoader to use the fake asset dir
    from app.services import icd10cn_loader as loader_mod
    real_cls = loader_mod.ICD10CNLoader

    class _PatchedLoader(real_cls):
        def __init__(self, asset_dir=None):
            super().__init__(asset_dir=str(asset))

    with patch("icoder_runtime.providers.medical_coding.embedding_bge_m3.BGEEmbedder", return_value=fake_embedder), \
         patch("app.services.icd10cn_loader.ICD10CNLoader", _PatchedLoader), \
         patch.dict("sys.modules", {"faiss": fake_faiss}):
        import scripts.build_medcoder_index as bm
        bm.faiss = fake_faiss

        rc = bm.main([
            "--asset-dir", str(asset),
            "--out", str(out),
            "--model-dir", str(tmp_path / "models"),
        ])

    assert rc == 0, f"build_medcoder_index failed: rc={rc}"
    assert (out / "faiss.index").exists()
    assert (out / "metadata.pkl").exists()

    with open(out / "metadata.pkl", "rb") as f:
        meta = pickle.load(f)
    assert len(meta) == 3
    assert meta[0]["code"] == "I50.900"
    assert meta[0]["name_cn"] == "心力衰竭"
    # All expected keys present
    for k in ("code", "name_cn", "name_en", "chapter_no", "chapter_name",
              "chapter_range", "category_code", "clinical_category"):
        assert k in meta[0], f"missing key {k}"


def test_limit_truncates_catalog(tmp_path, monkeypatch):
    """--limit N should only embed the first N codes."""
    import json
    asset = tmp_path / "asset"
    asset.mkdir()
    codes = [
        {"code": f"I50.{i:03d}", "name_cn": f"测试{i}", "name_en": f"Test{i}",
         "synonyms_cn": [], "synonyms_en": [],
         "chapter_range": "I00-I99", "chapter_no": "第9章", "chapter_name": "循环",
         "category_code": "I50", "clinical_category": "测试", "is_extended": False,
         "is_dagger_asterisk": False, "is_generated_category": False,
         "is_insurance_gray": False}
        for i in range(5)
    ]
    cat = {"_meta": {"total_codes": 5}, "chapters": {"I00-I99": {}}, "codes": codes}
    syn = {"_meta": {}, "synonyms": {}, "term_index": {}}
    (asset / "icd10cn_code_catalog.json").write_text(json.dumps(cat), encoding="utf-8")
    (asset / "icd10cn_synonym_map.json").write_text(json.dumps(syn), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()

    fake_embedder = _FakeEmbedder()
    fake_index = MagicMock()
    fake_index.ntotal = 0
    fake_index.add = MagicMock(side_effect=lambda arr: setattr(fake_index, "ntotal", arr.shape[0]))
    fake_faiss = _fake_faiss_module(fake_index)

    from app.services import icd10cn_loader as loader_mod
    real_cls = loader_mod.ICD10CNLoader

    class _PatchedLoader(real_cls):
        def __init__(self, asset_dir=None):
            super().__init__(asset_dir=str(asset))

    with patch("icoder_runtime.providers.medical_coding.embedding_bge_m3.BGEEmbedder", return_value=fake_embedder), \
         patch("app.services.icd10cn_loader.ICD10CNLoader", _PatchedLoader), \
         patch.dict("sys.modules", {"faiss": fake_faiss}):
        import scripts.build_medcoder_index as bm
        bm.faiss = fake_faiss
        rc = bm.main([
            "--asset-dir", str(asset),
            "--out", str(out),
            "--limit", "2",
        ])

    assert rc == 0
    # The embedder should have been called with exactly 2 texts
    assert len(fake_embedder._calls[0]) == 2
    assert fake_index.ntotal == 2
