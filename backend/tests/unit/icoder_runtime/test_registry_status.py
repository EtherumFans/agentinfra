"""Tests for registry_status + builtin_pack_provider compat (P1.1-B).

Covers:
* compute_compatibility returns all 16 packs
* Per-pack status: 10 v1.1 executable + 2 v1.2 executable (medcoder-coding-review, medical-coding-agent) + 4 v1.2 metadata_only
* MedCodER Coding Review reports EXECUTABLE (per baseline §4 fix)
* Expert-stubs report METADATA_ONLY
* production_ready flag correct per agent_type
* why_not_executable populated for non-executable packs
* BuiltinAgentPackProvider.discover_all returns 16
* BuiltinAgentPackProvider.register_all uses loader classification
* /api/icoder/registry/compatibility endpoint shape
* /api/icoder/registry/compatibility?agent_ref=X filters + 404 on unknown
* /api/icoder/registry/compatibility/summary returns counts only
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from icoder_runtime.core.builtin_pack_provider import BuiltinAgentPackProvider
from icoder_runtime.core.registry_status import compute_compatibility
from icoder_runtime.core.agent_pack_schema import PackStatus


REPO_BACKEND = Path(__file__).resolve().parents[3]
OFFICIAL_AGENTS_DIR = REPO_BACKEND / "official_agents"


# ── compute_compatibility ──


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_compute_compatibility_returns_16_packs():
    report = compute_compatibility(OFFICIAL_AGENTS_DIR)
    # Phase A1D.5 — A1B-AE Phase added 14 net-new Corti-parity packs
    # (10 metadata-only stubs + claim-check marked metadata-only + 3 new
    # v1.2 exec packs). Previous baseline was 16; current is 30.
    assert report.total_discovered == 30


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_compute_compatibility_status_distribution():
    report = compute_compatibility(OFFICIAL_AGENTS_DIR)
    # Phase A1D.5 — post A1B-AE Phase distribution:
    #   11 executable (v1.2 certified + reference + internal_engine + community)
    #   19 metadata_only (4 v1.1 stubs + 10 v1.2 sys_prompt-empty stubs
    #                     + 3 v1.2 expert-stubs + claim-check + 1 more)
    #   0 invalid (metadata-only maturity short-circuits validation per
    #              A1D.5 loader fix)
    assert report.by_status["executable"] == 11
    assert report.by_status["metadata_only"] == 19
    assert report.by_status.get("invalid", 0) == 0


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_compute_compatibility_medcoder_coding_review_is_executable():
    report = compute_compatibility(OFFICIAL_AGENTS_DIR)
    medcoder = next(e for e in report.entries if "medcoder-coding-review" in e.agent_ref)
    assert medcoder.status == PackStatus.EXECUTABLE.value
    assert medcoder.production_ready is True
    assert medcoder.expert_count == 4
    assert medcoder.tool_count == 5
    # Critical: even though not registered in legacy registry (v1.1 validator rejects),
    # the loader view still reports it as executable
    assert medcoder.why_not_executable == []


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_compute_compatibility_expert_stubs_are_metadata_only():
    report = compute_compatibility(OFFICIAL_AGENTS_DIR)
    stubs = [e for e in report.entries if e.agent_type == "expert-stub"]
    # Phase A1D.5 — 3 expert-stub packs (code-reconciler, index-navigator,
    # tabular-validator). Previous baseline was 4.
    assert len(stubs) == 3
    for s in stubs:
        assert s.status == PackStatus.METADATA_ONLY.value
        assert s.production_ready is False
        assert s.why_not_executable  # populated


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_compute_compatibility_v11_packs_all_metadata_only():
    """Phase A1D.5 — the 4 remaining v1.1 packs are all metadata-only stubs.

    The v1.1 → v1.2 migration (Phase 3-D1 Task 5) ported all runnable
    packs to v1.2. The remaining v1.1 packs (claim-check, denial-appeals,
    diagnosis-extractor, evidence-ranker) are catalog placeholders for
    Corti-parity agents not yet ported.
    """
    report = compute_compatibility(OFFICIAL_AGENTS_DIR)
    v11 = [e for e in report.entries if e.format_version == "1.1"]
    assert len(v11) == 4
    for p in v11:
        assert p.status == PackStatus.METADATA_ONLY.value
        assert p.production_ready is False


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_compute_compatibility_cross_ref_registry():
    """When a fake registry provides 4 v1.1 refs, those entries should
    be marked ``registered=True``; the v1.2 packs stay registered=False.

    Phase A1D.5 — v1.1 count is now 4 (down from 7). All 4 are
    metadata-only stubs but still discoverable for registry cross-ref.
    """
    fake_registry = MagicMock()

    # Build fake records mirroring the 4 v1.1 packs
    v11_refs = [e.agent_ref for e in compute_compatibility(OFFICIAL_AGENTS_DIR).entries
                if e.format_version == "1.1"]
    assert len(v11_refs) == 4

    def _fake_list_all():
        for i, ref in enumerate(v11_refs):
            rec = MagicMock()
            rec.agent_id = f"id-{i}"
            rec.pack_data = {"agent_ref": ref}
            yield rec

    fake_registry.list_all.return_value = list(_fake_list_all())

    report = compute_compatibility(OFFICIAL_AGENTS_DIR, registry=fake_registry)
    assert report.total_registered == 4

    for entry in report.entries:
        if entry.format_version == "1.1":
            assert entry.registered is True
        else:
            assert entry.registered is False


def test_compute_compatibility_handles_missing_dir():
    report = compute_compatibility("/nonexistent/path/12345")
    assert report.total_discovered == 0
    assert report.entries == []
    assert report.by_status == {"executable": 0, "metadata_only": 0, "invalid": 0}


def test_compute_compatibility_handles_registry_none():
    """Registry=None must work (cross-ref disabled)."""
    tmp = Path(__file__).resolve().parent / "_tmp_compat"
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    try:
        tmp.mkdir()
        (tmp / "v11pack").mkdir()
        pack = {
            "format_version": "1.1", "agent_type": "certified",
            "agent_ref": "icoder/v11pack@1.0.0",
            "manifest": {"name": "V11", "version": "1.0.0"},
            "system_prompt": "x", "experts": [], "tools": ["t"],
            "requirements": {"min_runtime_version": "1.0.0"},
        }
        (tmp / "v11pack" / "agent_pack.json").write_text(json.dumps(pack))
        report = compute_compatibility(tmp, registry=None)
        assert report.total_discovered == 1
        assert report.entries[0].registered is False
        assert report.entries[0].registry_agent_id is None
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


# ── BuiltinAgentPackProvider ──


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_builtin_pack_provider_discover_all_returns_16():
    p = BuiltinAgentPackProvider(OFFICIAL_AGENTS_DIR)
    packs = p.discover_all()
    # Phase A1D.5 — 30 packs now (was 16). See compute_compatibility test
    # for the breakdown.
    assert len(packs) == 30


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_builtin_pack_provider_compatibility_report():
    p = BuiltinAgentPackProvider(OFFICIAL_AGENTS_DIR)
    report = p.compatibility_report(registry=None)
    # Phase A1D.5 — 30 total, 19 metadata-only.
    assert report.total_discovered == 30
    assert report.metadata_only == 19


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_builtin_pack_provider_register_all_skips_metadata_only():
    """register_all should not attempt to install metadata_only packs."""
    p = BuiltinAgentPackProvider(OFFICIAL_AGENTS_DIR)
    p.discover_all()

    fake_runtime = MagicMock()
    fake_runtime.install_agent = MagicMock()

    registered = p.register_all(fake_runtime)
    # Phase A1D.5 — 11 executable packs attempted (was 12).
    # install_agent is mocked so all 11 calls "succeed" at the mock level.
    assert fake_runtime.install_agent.call_count == 11
    # Every attempted install is for an EXECUTABLE pack
    for call in fake_runtime.install_agent.call_args_list:
        pack_arg = call.args[0]
        assert pack_arg.get("format_version") in ("1.1", "1.2")


@pytest.mark.skipif(not OFFICIAL_AGENTS_DIR.exists(), reason="official_agents dir missing")
def test_builtin_pack_provider_register_all_skips_invalid():
    """An INVALID pack is not passed to install_agent."""
    p = BuiltinAgentPackProvider(OFFICIAL_AGENTS_DIR)
    # Inject an invalid pack by monkey-patching _normalized
    from icoder_runtime.core.agent_pack_loader import load_pack
    fake_invalid = load_pack({"format_version": "9.9", "agent_type": "certified",
                              "agent_ref": "icoder/bad@1.0.0",
                              "manifest": {"name": "Bad", "version": "1.0.0"}})
    p._normalized = [fake_invalid]  # only one bad pack
    fake_runtime = MagicMock()
    registered = p.register_all(fake_runtime)
    assert registered == 0
    fake_runtime.install_agent.assert_not_called()


def test_builtin_pack_provider_discover_all_with_empty_dir():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = BuiltinAgentPackProvider(td)
        assert p.discover_all() == []
        assert p.compatibility_report().total_discovered == 0

