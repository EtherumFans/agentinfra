"""Phase 3 — real coding-asset binding + the BGE-M3/FAISS retrieval seam.

The loader + overlay are tested against a tiny real-schema fixture (NOT the live 37,897-code
file) so the suite stays offline, fast, and independent of the asset dir existing. One live
test runs only when the real asset dir is present on this machine. The retrieval seam is
tested for graceful *unavailability* — it must raise (and degrade) without importing the
heavy deps or downloading the 2.3GB BGE-M3 model when the FAISS index is absent.
"""
from pathlib import Path

import pytest

from icoder.experts import real_catalog
from icoder.runtime.retrieval import (
    BgeM3FaissRetriever,
    RetrievalUnavailable,
    Retriever,
    retriever_from_env,
)

FIXTURE = str(Path(__file__).parent / "fixtures" / "mini_assets")
REAL_DIR = real_catalog.asset_dir() or r"E:\iCoDerA\DataAsset"


# ---- loader / availability (offline fixture) ----

def test_available_requires_both_catalog_files():
    assert real_catalog.available(FIXTURE) is True
    assert real_catalog.available(None) is False
    assert real_catalog.available("definitely-not-a-dir") is False


def test_load_shapes_real_records_into_entry_contract():
    cat = real_catalog.load(FIXTURE)
    assert {"I50.900", "A00", "I63.900", "45.1600x001", "00.0100"} <= set(cat)
    a00 = cat["A00"]
    assert a00["display"] == "霍乱"            # name_cn -> display
    assert a00["system"] == "ICD-10-CN"
    assert a00["code_type"] == "diagnosis"
    assert "霍乱" in a00["synonyms"]
    # icd9cm3 records are tagged as procedures under ICD-9-CM-3
    proc = cat["45.1600x001"]
    assert proc["system"] == "ICD-9-CM-3"
    assert proc["code_type"] == "procedure"
    # real records carry no curated enrichment — that stays the sample overlay's job
    assert a00["high_risk"] is False
    assert a00["notes"] == [] and a00["differentiation"] == [] and a00["guideline"] == ""


def test_load_without_dir_is_empty():
    assert real_catalog.load(None) == {}


def test_overlay_curated_wins_and_real_widens_membership():
    real = real_catalog.load(FIXTURE)
    curated = {
        # same code as a real record, but curated carries the high-risk routing + display
        "45.1600x001": {
            "display": "经胃镜食管十二指肠活检", "system": "ICD-9-CM-3", "code_type": "procedure",
            "synonyms": ["胃镜活检"], "high_risk": True, "notes": [], "guideline": "",
            "parent": "45.16", "siblings": [], "children": [], "differentiation": [],
        },
        # curated-only code (not in the real fixture) must survive the merge
        "N18.500": {
            "display": "慢性肾脏病5期", "system": "ICD-10-CN", "code_type": "diagnosis",
            "synonyms": [], "high_risk": False, "notes": [], "guideline": "",
            "parent": "N18", "siblings": [], "children": [], "differentiation": [],
        },
    }
    merged = real_catalog.overlay(real, curated)
    # curated wins on the shared code
    assert merged["45.1600x001"]["high_risk"] is True
    assert merged["45.1600x001"]["display"] == "经胃镜食管十二指肠活检"
    # real-only code is now a member (national breadth feeds R003 / search / verify)
    assert "A00" in merged and "I63.900" in merged
    # curated-only code preserved
    assert "N18.500" in merged


def test_lexicon_stays_pinned_to_curated_sample():
    # The deterministic extractor's vocabulary must never balloon to the 75k national
    # synonyms, even with the real catalog overlaid — extraction stays precise offline.
    from icoder.experts.catalog import lexicon

    lx = lexicon()
    assert "慢性心衰" in lx
    assert len(lx) < 200


# ---- BGE-M3/FAISS retrieval seam (graceful degradation, no model download) ----

def test_retriever_unavailable_when_index_missing(tmp_path):
    r = BgeM3FaissRetriever(str(tmp_path))  # empty dir: no faiss.index / metadata.pkl
    with pytest.raises(RetrievalUnavailable):
        r.retrieve("心衰")  # raises on the cheap path check, before any heavy import


def test_retriever_from_env_is_none_by_default(monkeypatch):
    monkeypatch.delenv("ICODER_MEDCODER_INDEX_DIR", raising=False)
    assert retriever_from_env() is None


def test_retriever_from_env_returns_degrade_safe_seam(monkeypatch, tmp_path):
    monkeypatch.setenv("ICODER_MEDCODER_INDEX_DIR", str(tmp_path))
    r = retriever_from_env()
    assert isinstance(r, BgeM3FaissRetriever)
    assert isinstance(r, Retriever)  # runtime-checkable protocol conformance
    with pytest.raises(RetrievalUnavailable):
        r.retrieve("心衰")


# ---- live (only when the read-only national catalog is present on this machine) ----

@pytest.mark.skipif(
    not real_catalog.available(REAL_DIR),
    reason="real ICD asset dir not present on this machine",
)
def test_live_real_catalog_has_demo_codes_and_full_breadth():
    cat = real_catalog.load(REAL_DIR)
    assert len(cat) > 45000  # 37,897 ICD-10-CN + 13,617 ICD-9-CM-3
    for code in ("I50.900", "I10.x00", "M80.900", "I66.901", "J98.414", "Z51.102"):
        assert code in cat, f"{code} missing from real catalog"
    for code in ("45.1600x001", "45.1300x001"):
        assert code in cat and cat[code]["system"] == "ICD-9-CM-3"
