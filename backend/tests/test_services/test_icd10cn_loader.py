"""Tests for icd10cn_loader — reads iCoDerA DataAsset (read-only)."""
from __future__ import annotations

import os
import sys
import pytest

# Make app.services importable regardless of cwd
_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app.services import icd10cn_loader as loader_mod
from app.services.icd10cn_loader import (
    DEFAULT_ASSET_DIR,
    ICD10CNLoader,
    get_loader,
    reset_singleton,
)


# ── Fixtures ──


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Each test starts with a fresh singleton so env var overrides take effect."""
    reset_singleton()
    yield
    reset_singleton()


@pytest.fixture(scope="module")
def loader() -> ICD10CNLoader:
    """Module-scoped loader — loads from disk once for the whole test module."""
    if not os.path.isdir(DEFAULT_ASSET_DIR):
        pytest.skip(f"iCoDerA asset dir not found: {DEFAULT_ASSET_DIR}")
    reset_singleton()
    return get_loader()


# ── Loading ──


class TestLoaderLoading:
    def test_singleton_returns_same_instance(self):
        a = get_loader()
        b = get_loader()
        assert a is b

    def test_singleton_can_be_reset(self):
        a = get_loader()
        reset_singleton()
        b = get_loader()
        assert a is not b

    def test_loader_loads_expected_counts(self, loader: ICD10CNLoader):
        stats = loader.stats()
        # Per iCoDerA _meta headers in DataAsset
        assert stats.catalog_codes == 37897
        assert stats.synonym_categories >= 20  # 21 nominal
        assert stats.term_index_size >= 50000  # 56,424 nominal
        assert stats.loaded_from == DEFAULT_ASSET_DIR

    def test_explicit_asset_dir_override(self, tmp_path, monkeypatch):
        # Write a tiny fake asset dir to verify path env override
        import json
        cat = {
            "_meta": {"total_codes": 2},
            "chapters": {"X00-Y99": {"chapter_no": "第X章"}},
            "codes": [
                {"code": "X00.000", "name_cn": "测试1", "name_en": "Test1",
                 "synonyms_cn": ["t1"], "synonyms_en": [],
                 "chapter_range": "X00-Y99", "chapter_no": "第X章", "chapter_name": "测试章",
                 "category_code": "X00", "clinical_category": "测试", "is_extended": False,
                 "is_dagger_asterisk": False, "is_generated_category": False,
                 "is_insurance_gray": False},
                {"code": "X01.000", "name_cn": "测试2", "name_en": "Test2",
                 "synonyms_cn": ["t2"], "synonyms_en": [],
                 "chapter_range": "X00-Y99", "chapter_no": "第X章", "chapter_name": "测试章",
                 "category_code": "X01", "clinical_category": "测试", "is_extended": False,
                 "is_dagger_asterisk": False, "is_generated_category": False,
                 "is_insurance_gray": False},
            ],
        }
        syn = {
            "_meta": {"total_synonyms": 2},
            "synonyms": {"测试": {
                "X00.000 测试1": {"code": "X00.000", "disease": "测试1", "synonyms": ["t1", "Test1"]},
            }},
            "term_index": {"t1": ["X00.000"], "测试2": ["X01.000"]},
        }
        (tmp_path / "icd10cn_code_catalog.json").write_text(json.dumps(cat), encoding="utf-8")
        (tmp_path / "icd10cn_synonym_map.json").write_text(json.dumps(syn), encoding="utf-8")

        # Use monkeypatch so the env var is reverted after the test.
        # Setting os.environ directly leaks the fake dir into later tests
        # (notably icd9cm3_loader tests, which also read ICODER_DATA_ASSET_DIR).
        monkeypatch.setenv("ICODER_DATA_ASSET_DIR", str(tmp_path))
        ldr = ICD10CNLoader()
        stats = ldr.load()
        assert stats.catalog_codes == 2
        assert stats.term_index_size == 2
        assert ldr.get("X00.000").name_cn == "测试1"
        assert ldr.codes_for_term("t1") == ["X00.000"]
        assert ldr.synonyms_for("t1") == ["测试1"]


# ── Accessors ──


class TestLoaderAccessors:
    def test_all_codes_returns_list_of_entries(self, loader: ICD10CNLoader):
        all_codes = loader.all_codes()
        assert len(all_codes) == 37897
        assert all(hasattr(e, "code") and hasattr(e, "name_cn") for e in all_codes)

    def test_code_dict_lookup(self, loader: ICD10CNLoader):
        d = loader.code_dict()
        assert "I50.900" in d
        entry = d["I50.900"]
        # Heart failure — name_cn may vary but chapter should be circulatory
        assert "循环" in entry.chapter_name or "循环" in (entry.clinical_category or "")

    def test_get_returns_none_for_unknown(self, loader: ICD10CNLoader):
        assert loader.get("ZZZ.999") is None
        assert loader.has("ZZZ.999") is False

    def test_chapter_for_known_code(self, loader: ICD10CNLoader):
        # I50 is heart failure — should be Chapter 9 (循环系统疾病)
        ch = loader.chapter_for("I50.900")
        assert "9" in ch or "循环" in ch

    def test_chapter_for_unknown_code_returns_empty(self, loader: ICD10CNLoader):
        assert loader.chapter_for("ZZZ.999") == ""

    def test_all_names_includes_synonyms(self, loader: ICD10CNLoader):
        # M80.900 (骨质疏松) has synonyms in evidence_anchoring_kb
        entry = loader.get("M80.900")
        assert entry is not None
        # all_names should include name_cn + synonyms_cn
        assert entry.name_cn in entry.all_names
        for s in entry.synonyms_cn:
            assert s in entry.all_names


# ── Term / synonym lookup ──


class TestTermLookup:
    def test_codes_for_term_returns_matching_codes(self, loader: ICD10CNLoader):
        # "霍乱" should map to A00 family
        codes = loader.codes_for_term("霍乱")
        assert codes
        assert all(c.startswith("A00") for c in codes)

    def test_codes_for_term_case_insensitive(self, loader: ICD10CNLoader):
        # "cholera" (English synonym) should map to A00
        codes = loader.codes_for_term("cholera")
        assert codes
        assert all(c.startswith("A00") for c in codes)

    def test_codes_for_empty_term_returns_empty(self, loader: ICD10CNLoader):
        assert loader.codes_for_term("") == []
        assert loader.codes_for_term("definitely_not_in_index_xyz") == []

    def test_synonyms_for_returns_canonical_names(self, loader: ICD10CNLoader):
        # 输入"霍乱" → 应返回同 code 下的其他 name（描述更长的优先）
        syns = loader.synonyms_for("霍乱", max_synonyms=2)
        assert isinstance(syns, list)
        # 不应包含输入本身
        assert "霍乱" not in syns

    def test_synonyms_for_zero_or_negative_max(self, loader: ICD10CNLoader):
        # 边界：max_synonyms=0 应返回空
        assert loader.synonyms_for("霍乱", max_synonyms=0) == []

    def test_codes_for_codes_filters_unknown(self, loader: ICD10CNLoader):
        entries = loader.codes_for_codes(["I50.900", "ZZZ.999", "J18.900"])
        codes = [e.code for e in entries]
        assert "I50.900" in codes
        assert "J18.900" in codes
        assert "ZZZ.999" not in codes


# ── Stats / introspection ──


class TestLoaderStats:
    def test_stats_returns_a_fresh_copy(self, loader: ICD10CNLoader):
        s1 = loader.stats()
        s1.catalog_codes = 0
        s2 = loader.stats()
        assert s2.catalog_codes == 37897  # original unchanged

    def test_chapters_dict_loaded(self, loader: ICD10CNLoader):
        chs = loader.chapters()
        assert isinstance(chs, dict)
        # 22 chapters in CN ICD-10 (第1章 through 第22章)
        assert len(chs) >= 20
