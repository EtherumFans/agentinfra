"""A1B-AE-RV.4 — PubMed + ClinicalTrials live capture + VCR replay shape.

Verifies:
§1  Live capture envelope file exists (PUBMED_LIVE_CAPTURE.json)
§2  Live capture envelope file exists (CLINICAL_TRIALS_LIVE_CAPTURE.json)
§3  Live capture envelope has LIVE_CAPTURE tag (not RECORDED_FIXTURE)
§4  Live envelope reports status=OK (not BLOCKED_BY_*)
§5  Live envelope contains ≥1 article/trial (real data returned)
§6  VCR fixture seeded by the live capture (fixture file exists)
§7  VCR replay path returns the fixture (search_async without allow_live_capture)
§8  Replay shape matches live shape (no field drift)
§9  Replay is tagged RECORDED_FIXTURE (NOT LIVE_CAPTURE — no network)
§10 Live capture manifest exists (MANIFEST.json)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = (
    REPO_ROOT
    / "reports"
    / "phase-a1b"
    / "agent-expert-reverification"
    / "evidence"
    / "public-expert-live"
)


def _load(name: str) -> dict:
    p = EVIDENCE / name
    if not p.exists():
        pytest.skip(
            f"RV.4 evidence not present at {p}. Run "
            f"`python scripts/rv4_live_capture.py` from repo root first."
        )
    return json.loads(p.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────
# §1, §3, §4, §5 — PubMed live envelope
# ─────────────────────────────────────────────────────────────────────


def test_rv4_1_pubmed_live_envelope_present():
    """§1 PUBMED_LIVE_CAPTURE.json exists."""
    pm = _load("PUBMED_LIVE_CAPTURE.json")
    assert pm["expert"] == "pubmed"


def test_rv4_3_pubmed_envelope_tagged_live_capture():
    """§3 Live envelope must be tagged LIVE_CAPTURE (not RECORDED_FIXTURE)."""
    pm = _load("PUBMED_LIVE_CAPTURE.json")
    assert pm["capture_mode"] == "LIVE_CAPTURE", (
        f"live envelope must be LIVE_CAPTURE, got {pm['capture_mode']!r}"
    )


def test_rv4_4_pubmed_live_status_ok():
    """§4 Live capture returned OK (not BLOCKED_BY_NETWORK or similar)."""
    pm = _load("PUBMED_LIVE_CAPTURE.json")
    assert pm["status"] == "OK", (
        f"live capture did not return OK: status={pm['status']}, "
        f"notes={pm.get('notes')}"
    )


def test_rv4_5_pubmed_live_returned_articles():
    """§5 Live capture returned ≥1 article."""
    pm = _load("PUBMED_LIVE_CAPTURE.json")
    assert pm.get("total", 0) >= 1, (
        f"live capture returned 0 articles; query={pm.get('query')!r}"
    )
    articles = pm.get("articles", [])
    assert len(articles) >= 1
    # Real-world sanity: every article has a PMID + title
    for art in articles:
        assert art.get("pmid"), f"article missing pmid: {art}"
        assert art.get("title"), f"article missing title: {art}"


# ─────────────────────────────────────────────────────────────────────
# §2 — ClinicalTrials live envelope
# ─────────────────────────────────────────────────────────────────────


def test_rv4_2_clinical_trials_live_envelope_present():
    """§2 CLINICAL_TRIALS_LIVE_CAPTURE.json exists."""
    ct = _load("CLINICAL_TRIALS_LIVE_CAPTURE.json")
    assert ct["expert"] == "clinical-trials"


def test_rv4_3b_clinical_trials_envelope_tagged_live_capture():
    """§3 ClinicalTrials envelope tagged LIVE_CAPTURE."""
    ct = _load("CLINICAL_TRIALS_LIVE_CAPTURE.json")
    assert ct["capture_mode"] == "LIVE_CAPTURE"


def test_rv4_4b_clinical_trials_live_status_ok():
    """§4 ClinicalTrials live capture returned OK."""
    ct = _load("CLINICAL_TRIALS_LIVE_CAPTURE.json")
    assert ct["status"] == "OK", (
        f"clinical trials live capture did not return OK: "
        f"status={ct['status']}, notes={ct.get('notes')}"
    )


def test_rv4_5b_clinical_trials_live_returned_trials():
    """§5 Live capture returned ≥1 trial."""
    ct = _load("CLINICAL_TRIALS_LIVE_CAPTURE.json")
    assert ct.get("total", 0) >= 1
    trials = ct.get("trials", [])
    assert len(trials) >= 1
    for t in trials:
        assert t.get("nct_id"), f"trial missing nct_id: {t}"


# ─────────────────────────────────────────────────────────────────────
# §6 — VCR fixture seeded
# ─────────────────────────────────────────────────────────────────────


def test_rv4_6_pubmed_vcr_fixture_seeded():
    """§6 PubMed VCR fixture exists after live capture."""
    from app.agents.experts.pubmed_expert import _fixture_path

    pm = _load("PUBMED_LIVE_CAPTURE.json")
    p = _fixture_path(pm["query"])
    assert p.exists(), (
        f"PubMed VCR fixture not seeded at {p}; live capture did not "
        f"flow through search_async(allow_live_capture=True)"
    )


def test_rv4_6b_clinical_trials_vcr_fixture_seeded():
    """§6 ClinicalTrials VCR fixture exists after live capture."""
    from app.agents.experts.clinical_trials_expert import _fixture_path

    ct = _load("CLINICAL_TRIALS_LIVE_CAPTURE.json")
    p = _fixture_path(ct["query"])
    assert p.exists(), f"ClinicalTrials VCR fixture not seeded at {p}"


# ─────────────────────────────────────────────────────────────────────
# §7, §8, §9 — Replay path
# ─────────────────────────────────────────────────────────────────────


def test_rv4_7_pubmed_replay_returns_fixture_without_network():
    """§7 search_async WITHOUT allow_live_capture returns the fixture.
    §9 Notes string must say VCR fixture replay (NOT live capture)."""
    import asyncio

    from app.agents.experts.pubmed_expert import search_async as pm_search

    pm = _load("PUBMED_LIVE_CAPTURE.json")

    async def _go():
        return await pm_search(
            pm["query"],
            max_results=5,
            egress_enabled=True,
            region="EU",
            allow_live_capture=False,  # replay mode
        )

    r = asyncio.run(_go())
    assert r.live_search_performed is True
    assert "VCR fixture replay" in r.notes, (
        f"replay notes must mark RECORDED_FIXTURE; got {r.notes!r}"
    )
    assert "live capture" not in r.notes.lower(), (
        f"replay must NOT claim live capture; got {r.notes!r}"
    )
    assert r.total >= 1


def test_rv4_7b_clinical_trials_replay_returns_fixture_without_network():
    """§7 ClinicalTrials search_async replay returns fixture."""
    import asyncio

    from app.agents.experts.clinical_trials_expert import (
        search_async as ct_search,
    )

    ct = _load("CLINICAL_TRIALS_LIVE_CAPTURE.json")

    async def _go():
        return await ct_search(
            ct["query"],
            max_results=5,
            egress_enabled=True,
            region="EU",
            allow_live_capture=False,
        )

    r = asyncio.run(_go())
    assert r.live_search_performed is True
    assert "VCR fixture replay" in r.notes
    assert r.total >= 1


def test_rv4_8_replay_shape_matches_live_shape_pubmed():
    """§8 PubMed — replay articles have the same key set as live articles.

    Drift would surface as new keys in either direction. Live capture
    shape was set by pubmed_expert._format_articles; replay reads from
    a fixture written by the same function, so keys should match
    exactly unless the formatter was edited between capture and replay.
    """
    import asyncio

    from app.agents.experts.pubmed_expert import search_async as pm_search

    pm = _load("PUBMED_LIVE_CAPTURE.json")

    async def _go():
        return await pm_search(
            pm["query"],
            max_results=5,
            egress_enabled=True,
            region="EU",
            allow_live_capture=False,
        )

    r = asyncio.run(_go())
    live_keys = {tuple(sorted(a.keys())) for a in pm.get("articles", [])}
    replay_keys = {tuple(sorted(a.keys())) for a in r.articles}
    assert live_keys == replay_keys, (
        f"shape drift: live={live_keys}, replay={replay_keys}"
    )


def test_rv4_8b_replay_shape_matches_live_shape_clinical_trials():
    """§8 ClinicalTrials — replay trials have the same key set as live."""
    import asyncio

    from app.agents.experts.clinical_trials_expert import (
        search_async as ct_search,
    )

    ct = _load("CLINICAL_TRIALS_LIVE_CAPTURE.json")

    async def _go():
        return await ct_search(
            ct["query"],
            max_results=5,
            egress_enabled=True,
            region="EU",
            allow_live_capture=False,
        )

    r = asyncio.run(_go())
    live_keys = {tuple(sorted(t.keys())) for t in ct.get("trials", [])}
    replay_keys = {tuple(sorted(t.keys())) for t in r.trials}
    assert live_keys == replay_keys, (
        f"shape drift: live={live_keys}, replay={replay_keys}"
    )


# ─────────────────────────────────────────────────────────────────────
# §10 — Manifest
# ─────────────────────────────────────────────────────────────────────


def test_rv4_10_manifest_present():
    """§10 MANIFEST.json exists and records both captures."""
    m = _load("MANIFEST.json")
    assert m["sub_gate"] == "RV.4"
    assert m["pubmed_status"] == "OK"
    assert m["clinical_trials_status"] == "OK"
    assert m["pubmed_articles"] >= 1
    assert m["clinical_trials_trials"] >= 1


# ─────────────────────────────────────────────────────────────────────
# Marker scan — synthetic marker must NOT bleed into the VCR fixture
# ─────────────────────────────────────────────────────────────────────


def test_rv4_marker_does_not_leak_into_fixture():
    """The RV4MARKER prefix in the query itself is the *query*, not PHI.
    The fixture records the query as the lookup key. This test asserts
    the fixture body (articles/trials) does NOT contain the marker —
    the marker stays in the query envelope only.
    """
    from app.agents.experts.clinical_trials_expert import (
        _fixture_path as ct_path,
    )
    from app.agents.experts.pubmed_expert import _fixture_path as pm_path

    pm = _load("PUBMED_LIVE_CAPTURE.json")
    ct = _load("CLINICAL_TRIALS_LIVE_CAPTURE.json")

    pm_fixture = json.loads(pm_path(pm["query"]).read_text(encoding="utf-8"))
    ct_fixture = json.loads(ct_path(ct["query"]).read_text(encoding="utf-8"))

    pm_blob = json.dumps(pm_fixture.get("payload", {}))
    ct_blob = json.dumps(ct_fixture.get("payload", {}))

    # PubMed query has RV4MARKER; fixture payload must not echo it into
    # article titles, journals, or authors.
    assert "RV4MARKER" not in pm_blob.replace(
        pm["query"], ""
    ), "PubMed fixture echoes synthetic marker outside the query field"

    # CT query has no marker — entire fixture must be marker-free.
    assert "RV4MARKER" not in ct_blob
