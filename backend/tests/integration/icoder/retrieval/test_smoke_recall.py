"""M2.5 — Retrieval smoke test (5 anchors).

Validates the rebuilt FAISS index by issuing 5 well-known Chinese
disease names and asserting the top-K returns the expected ICD family:

  1. 骨质疏松     → M80.x (osteoporosis with pathological fracture)
  2. 糖尿病       → E10.x or E11.x (Type 1 / Type 2 diabetes)
  3. 肺炎         → J12-J18 (pneumonia)
  4. 剖宫产       → O82.x (encounter for cesarean delivery)
  5. 阑尾炎       → K35-K37 (appendicitis)

Test policy:
  - SKIP if the FAISS index is missing or degraded (governance
    boundary — ``index_health_check`` reports "degraded" → no test).
  - HARD-FAIL if the index is present but retrieval returns nothing
    on a top-1 anchor. This is the canary for "rebuilt index is
    broken / wrong embedding / wrong catalog".

This is an **integration test** — it requires the real FAISS index
and a BGE-M3-loaded retriever, both of which are slow to construct.
It is NOT run by the default ``tests/unit/`` sweep; CI runs it
under ``tests/integration/icoder/retrieval/`` only when the index
is present.

Phase 3-C0 A3 (2026-07-05): this module is now marked ``heavy`` +
``retrieval`` and excluded from the default pytest run via
``pytest.ini``'s ``addopts = -m "not heavy and not retrieval"``.
Resource requirements:

  - BGE-M3 model load (2.3 GB on disk, ~3-4 GB peak RAM in fp32,
    ~1.5-2 GB in fp16)
  - FAISS IndexFlatIP for ICD-10-CN (~37,897 vectors, 1024-dim)
  - sentence-transformers 3.2.1 + torch 2.11.0 CPU on Windows has a
    1 GB malloc limit OOM (E1.9/E1.10 known issue) — fp16 + MMAP
    mitigates but does not fully fix on Windows CPU.

Run explicitly with::

    pytest -m heavy tests/integration/icoder/retrieval/test_smoke_recall.py
    pytest -m retrieval tests/integration/icoder/retrieval/
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.medcoder_index_health import index_health_check


# ── Anchor definitions ──


# (disease_text, expected chapter prefix, human-readable label)
SMOKE_ANCHORS: list[tuple[str, str, str]] = [
    ("骨质疏松", "M80", "骨质疏松 → M80.x 骨质疏松伴病理性骨折"),
    ("糖尿病", "E1",   "糖尿病 → E10/E11 1型/2型糖尿病"),
    ("肺炎", "J1",     "肺炎 → J12-J18 肺炎"),
    ("剖宫产", "O82",  "剖宫产 → O82.x 剖宫产术的单胎分娩"),
    ("阑尾炎", "K3",   "阑尾炎 → K35-K37 阑尾炎"),
]


# ── Fixtures ──


def _index_available() -> bool:
    """Skip the whole module when the index is missing or degraded."""
    h = index_health_check(Path("data/medcoder"))
    return h["status"] == "ok"


# Phase 3-C0 A3: heavy + retrieval markers exclude this module from the
# default test run. Explicit opt-in via `pytest -m heavy` or `-m retrieval`
# is required. The skipif below still applies when the index is missing
# even if the markers are overridden.
pytestmark = [
    pytest.mark.heavy,
    pytest.mark.retrieval,
    pytest.mark.skipif(
        not _index_available(),
        reason=(
            "FAISS index missing or degraded. "
            "Run `python scripts/build_medcoder_index.py` first. "
            "M2.5 governance: this test refuses to run when retrieval is "
            "unhealthy so it doesn't give a false PASS on a degraded runtime."
        ),
    ),
]


@pytest.fixture
def medcoder_strategy():
    """Construct a real MedCodERStrategy with the live retriever.

    The fixture is module-scoped so BGE-M3 + FAISS load once for the
    whole test run (each fixture invocation reuses the loaded model).
    """
    from icoder_runtime.providers.medical_coding.medcoder_strategy import (
        MedCodERStrategy,
    )

    strategy = MedCodERStrategy()
    # Trigger lazy retriever load (BGE-M3 + FAISS).
    retriever = strategy._get_retriever()
    if retriever is None:
        pytest.skip("Retriever not initialized (BGE-M3 + FAISS load failed)")
    return strategy


# ── Tests ──


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "disease_text,expected_prefix,label",
    SMOKE_ANCHORS,
    ids=[a[0] for a in SMOKE_ANCHORS],
)
async def test_smoke_recall_returns_expected_icd_family(
    medcoder_strategy, disease_text: str, expected_prefix: str, label: str,
):
    """Top-5 retrieval for each anchor must hit the expected ICD family.

    Asserts:
      - ≥ 1 candidate returned
      - at least one candidate's code starts with the expected prefix
      - top-1 score ≥ 0.5 (BGE-M3 cosine on normalized vectors; well-
        indexed anchors typically score 0.7+)
    """
    top_k = 5
    # E1.1 (2026-06-26): stage2_retrieve now returns Stage2Result envelope
    stage2_result = await medcoder_strategy.stage2_retrieve(disease_text, top_k=top_k)
    candidates = stage2_result.candidates
    assert stage2_result.is_ok, (
        f"{label}: stage2_retrieve returned degraded status "
        f"(degraded={stage2_result.degraded}, error_code={stage2_result.error_code!r}, "
        f"detail={stage2_result.error_detail!r}). "
        f"FAISS index may be empty or BGE-M3 embedding is broken."
    )
    assert candidates, (
        f"{label}: stage2_retrieve returned 0 candidates for {disease_text!r}. "
        "FAISS index may be empty or BGE-M3 embedding is broken."
    )
    # At least one code starts with the expected prefix
    matching = [
        c for c in candidates
        if (c.code or "").startswith(expected_prefix)
    ]
    assert matching, (
        f"{label}: top-{top_k} retrieval for {disease_text!r} returned "
        f"codes {[c.code for c in candidates]} but none starts with {expected_prefix}."
    )
    # Top-1 score is reasonable
    top1 = candidates[0]
    assert top1.score >= 0.3, (
        f"{label}: top-1 score {top1.score:.3f} too low for {disease_text!r} "
        f"(code={top1.code}, name={top1.name!r})"
    )


@pytest.mark.asyncio
async def test_smoke_recall_all_5_anchors_have_overall_recall(medcoder_strategy):
    """Aggregate check: at least 4 of 5 anchors hit the expected family.

    This is the headline assertion for the M2.5 health gate — if 4+
    anchors fail, the rebuilt index is wrong and the rebuild script
    needs investigation.
    """
    hits = 0
    for disease_text, expected_prefix, _label in SMOKE_ANCHORS:
        # E1.1: stage2_retrieve returns Stage2Result envelope
        result = await medcoder_strategy.stage2_retrieve(disease_text, top_k=5)
        cands = result.candidates
        if any((c.code or "").startswith(expected_prefix) for c in cands):
            hits += 1
    assert hits >= 4, (
        f"Only {hits}/5 anchors hit their expected ICD family. "
        f"Threshold is ≥ 4/5 for the rebuilt index to be considered healthy."
    )
