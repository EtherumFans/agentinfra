"""Tests for ICD9CM3Loader — E1.5 catalog loader for procedure codes.

Mirrors ``test_icd10cn_loader.py`` shape. Uses a tiny synthetic catalog
(tmp_path) so tests run without the 2.5 MB real DataAsset file. The real
catalog is exercised by smoke tests (deferred).
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


# ── Fixtures ──


@pytest.fixture
def fake_catalog_dir(tmp_path, monkeypatch):
    """Build a 3-row ICD-9-CM-3 catalog fixture under tmp_path and point
    ``ICODER_DATA_ASSET_DIR`` at it. Loader picks up the env var on
    construction.
    """
    catalog = {
        "_meta": {"name": "fake-catalog", "version": "0.0.1"},
        "chapters": {"42": "操作与介入"},
        "v2_to_v3": {},
        "codes": [
            {
                "code": "45.2301",
                "name_cn": "结肠镜检查",
                "name_en": "Colonoscopy",
                "category": "诊断性操作",
                "entry_option": "选择项",
                "synonyms_cn": ["肠镜"],
                "synonyms_en": ["colonoscopy"],
                "chapter_range": "42",
                "chapter_no": "第1章",
                "chapter_name": "操作与介入",
                "is_extended": False,
                "insurance_code": "45.2301",
                "is_insurance_gray": False,
            },
            {
                "code": "45.4100",
                "name_cn": "结肠息肉切除术",
                "name_en": "Polypectomy of colon",
                "category": "治疗性操作",
                "entry_option": "选择项",
                "synonyms_cn": [],
                "synonyms_en": [],
                "chapter_range": "42",
                "chapter_no": "第1章",
                "chapter_name": "操作与介入",
                "is_extended": True,
                "insurance_code": "45.4100",
                "is_insurance_gray": False,
            },
            {
                "code": "88.0101",
                "name_cn": "腹部CT",
                "name_en": "Abdominal CT",
                "category": "诊断性操作",
                "entry_option": "选择项",
                "synonyms_cn": [],
                "synonyms_en": ["abdominal CT"],
                "chapter_range": "42",
                "chapter_no": "第1章",
                "chapter_name": "操作与介入",
                "is_extended": False,
                "insurance_code": "",
                "is_insurance_gray": True,
            },
        ],
    }
    (tmp_path / "icd9cm3_code_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setenv("ICODER_DATA_ASSET_DIR", str(tmp_path))
    # Drop the cached singleton so it reloads from our fixture.
    from app.services import icd9cm3_loader as loader_mod
    loader_mod.reset_singleton()
    yield tmp_path
    loader_mod.reset_singleton()


# ── Loading ──


class TestIcd9cm3LoaderLoading:
    def test_loads_catalog_and_chapters(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        stats = loader.ensure_loaded()
        assert stats.catalog_codes == 3
        assert stats.chapters == 1
        assert "45.2301" in loader.code_dict()
        assert loader.chapters() == {"42": "操作与介入"}

    def test_loads_missing_catalog_raises(self, tmp_path, monkeypatch):
        from app.services import icd9cm3_loader as loader_mod
        monkeypatch.setenv("ICODER_DATA_ASSET_DIR", str(tmp_path))
        loader_mod.reset_singleton()
        loader = loader_mod.ICD9CM3Loader(asset_dir=str(tmp_path))
        with pytest.raises(FileNotFoundError):
            loader.load()

    def test_load_is_idempotent(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        s1 = loader.load()
        s2 = loader.load()
        assert s1.catalog_codes == s2.catalog_codes == 3


# ── Accessors ──


class TestIcd9cm3LoaderAccessors:
    def test_code_dict_returns_copy(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        d = loader.code_dict()
        assert set(d.keys()) == {"45.2301", "45.4100", "88.0101"}
        # mutating the returned dict shouldn't affect the loader
        d["XX.0000"] = None
        assert "XX.0000" not in loader.code_dict()

    def test_get_returns_entry(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        entry = loader.get("45.2301")
        assert entry is not None
        assert entry.name_cn == "结肠镜检查"
        assert entry.category == "诊断性操作"
        assert "肠镜" in entry.synonyms_cn

    def test_get_missing_returns_none(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        assert loader.get("ZZ.9999") is None

    def test_has_returns_bool(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        assert loader.has("45.2301") is True
        assert loader.has("45.4100") is True
        assert loader.has("88.0101") is True
        assert loader.has("ZZ.9999") is False
        assert loader.has("") is False

    def test_all_codes_returns_entries(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        codes = loader.all_codes()
        assert len(codes) == 3
        assert all(c.code for c in codes)

    def test_chapter_for_returns_human_label(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        assert loader.chapter_for("45.2301") == "第1章 操作与介入"
        assert loader.chapter_for("ZZ.9999") == ""

    def test_all_names_includes_synonyms(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        entry = loader.get("45.2301")
        names = entry.all_names
        assert "结肠镜检查" in names
        assert "Colonoscopy" in names
        assert "肠镜" in names
        # dedup
        assert len(names) == len(set(names))

    def test_stats_returns_snapshot(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        loader = get_loader()
        s = loader.stats()
        assert s.catalog_codes == 3
        assert s.chapters == 1


# ── Singleton lifecycle ──


class TestIcd9cm3LoaderSingleton:
    def test_get_loader_returns_singleton(self, fake_catalog_dir):
        from app.services.icd9cm3_loader import get_loader
        a = get_loader()
        b = get_loader()
        assert a is b

    def test_reset_singleton_forces_reload(self, fake_catalog_dir):
        from app.services import icd9cm3_loader as loader_mod
        a = loader_mod.get_loader()
        loader_mod.reset_singleton()
        b = loader_mod.get_loader()
        assert a is not b