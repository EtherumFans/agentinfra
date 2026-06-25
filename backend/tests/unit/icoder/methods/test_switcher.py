"""MethodSwitcher + probe_capabilities tests (~16 cases).

Covers:
  - probe_capabilities returns correct shape and reflects env state
  - mode_to_method_id mapping (legacy + MedCodER modes)
  - MethodSwitcher.run: unknown method_id, empty emr, missing caps, ok path
  - MethodSwitcher.compare: ordering, error attribution
  - MethodSwitcher.describe: metadata + availability
  - Exception inside method.run is caught and reported (status="error")

Note: ``conftest.py`` provides autouse fixture for GLOBAL_REGISTRY
isolation — no per-file fixture needed.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from icoder_runtime.methods.base import (
    CodingMethod,
    MethodCapability,
    MethodFamily,
    MethodResult,
)
from icoder_runtime.methods.registry import GLOBAL_REGISTRY
from icoder_runtime.methods.switcher import (
    GLOBAL_SWITCHER,
    MethodSwitcher,
    mode_to_method_id,
    probe_capabilities,
)


class _OkMethod(CodingMethod):
    method_id = "test.ok"
    method_name = "OK Method"
    method_family = "legacy"
    stage_count = 1
    required_capabilities = ()
    description = "always-ok method"

    async def run(self, emr_text, ctx=None):
        return MethodResult(
            method_id=self.method_id,
            method_name=self.method_name,
            method_family=self.method_family,
            status="ok",
            primary_code="I50.900",
            primary_name="心力衰竭",
            confidence=0.9,
            stage_trace=[],
            processing_time_ms=10,
        )


class _CrashMethod(CodingMethod):
    method_id = "test.crash"
    method_name = "Crash"
    method_family = "legacy"
    stage_count = 1
    required_capabilities = ()
    description = "always crashes"

    async def run(self, emr_text, ctx=None):
        raise RuntimeError("intentional crash")


class _NeedsRetriever(CodingMethod):
    method_id = "test.needs_retriever"
    method_name = "Needs Retriever"
    method_family = "medcoder"
    stage_count = 2
    required_capabilities = (MethodCapability.RETRIEVER,)
    description = "requires FAISS"

    async def run(self, emr_text, ctx=None):
        return MethodResult(method_id=self.method_id, status="ok")


# ── probe_capabilities ──


class TestProbeCapabilities:
    def test_returns_expected_keys(self):
        caps = probe_capabilities()
        assert set(caps.keys()) == {"llm", "retriever", "rule_set"}

    def test_rule_set_always_true(self):
        caps = probe_capabilities()
        assert caps["rule_set"] is True

    def test_llm_true_when_env_set(self, monkeypatch):
        monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "sk-test")
        caps = probe_capabilities()
        assert caps["llm"] is True

    def test_llm_false_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
        caps = probe_capabilities()
        assert caps["llm"] is False

    def test_llm_false_when_env_whitespace_only(self, monkeypatch):
        monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "   ")
        caps = probe_capabilities()
        assert caps["llm"] is False

    def test_retriever_propagates_health_check(self, monkeypatch):
        # Healthy
        fake_health = {"status": "ok", "ntotal": 37897, "dim": 1024}
        with patch(
            "app.services.medcoder_index_health.index_health_check",
            return_value=fake_health,
        ):
            caps = probe_capabilities()
            assert caps["retriever"] is True

        # Degraded
        with patch(
            "app.services.medcoder_index_health.index_health_check",
            return_value={"status": "degraded", "reason": "missing faiss.index"},
        ):
            caps = probe_capabilities()
            assert caps["retriever"] is False

    def test_retriever_handles_exception(self):
        # Probe is defensive — if the module crashes, retriever = False, no raise.
        with patch(
            "app.services.medcoder_index_health.index_health_check",
            side_effect=ImportError("module missing"),
        ):
            caps = probe_capabilities()
            assert caps["retriever"] is False


# ── mode_to_method_id ──


class TestModeToMethodId:
    def test_legacy_modes(self):
        assert mode_to_method_id("deepseek") == "legacy.deepseek"
        assert mode_to_method_id("prompt_llm") == "legacy.prompt_llm"
        assert mode_to_method_id("hybrid") == "legacy.hybrid"
        assert mode_to_method_id("no_repair") == "legacy.no_repair"

    def test_medcoder_modes(self):
        assert mode_to_method_id("medcoder") == "medcoder.full"
        assert mode_to_method_id("medcoder_full") == "medcoder.full"
        assert mode_to_method_id("medcoder_prompt") == "medcoder.prompt"
        assert mode_to_method_id("medcoder_retrieve") == "medcoder.retrieve"
        assert mode_to_method_id("medcoder_prompt+retrieve") == "medcoder.prompt+retrieve"

    def test_code_like_humans_mode(self):
        # Phase C: CLH is a MedCodER-family mode but its own method_id
        assert mode_to_method_id("code_like_humans") == "medcoder.code_like_humans"

    def test_unknown_mode_returns_none(self):
        assert mode_to_method_id("bogus") is None
        assert mode_to_method_id("") is None


# ── MethodSwitcher.run ──


class TestSwitcherRun:
    @pytest.mark.asyncio
    async def test_unknown_method(self):
        result = await GLOBAL_SWITCHER.run("nope.method", "some emr text")
        assert result.status == "unavailable"
        assert "unknown method_id" in result.reason
        assert "available:" in result.reason

    @pytest.mark.asyncio
    async def test_empty_emr(self):
        GLOBAL_REGISTRY.register(_OkMethod())
        result = await GLOBAL_SWITCHER.run("test.ok", "")
        assert result.status == "unavailable"
        assert "empty emr_text" in result.reason

    @pytest.mark.asyncio
    async def test_whitespace_emr(self):
        GLOBAL_REGISTRY.register(_OkMethod())
        result = await GLOBAL_SWITCHER.run("test.ok", "   \n  ")
        assert result.status == "unavailable"

    @pytest.mark.asyncio
    async def test_missing_capability(self, monkeypatch):
        monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
        with patch(
            "app.services.medcoder_index_health.index_health_check",
            return_value={"status": "degraded", "reason": "missing"},
        ):
            GLOBAL_REGISTRY.register(_NeedsRetriever())
            result = await GLOBAL_SWITCHER.run("test.needs_retriever", "some emr")
            assert result.status == "unavailable"
            assert "missing required capabilities" in result.reason
            assert "retriever" in result.reason

    @pytest.mark.asyncio
    async def test_happy_path(self):
        GLOBAL_REGISTRY.register(_OkMethod())
        result = await GLOBAL_SWITCHER.run("test.ok", "心力衰竭病历")
        assert result.status == "ok"
        assert result.primary_code == "I50.900"
        assert result.method_id == "test.ok"

    @pytest.mark.asyncio
    async def test_method_crash_caught(self):
        GLOBAL_REGISTRY.register(_CrashMethod())
        result = await GLOBAL_SWITCHER.run("test.crash", "some emr")
        assert result.status == "error"
        assert "method crashed" in result.reason
        assert "intentional crash" in result.reason


# ── MethodSwitcher.compare ──


class TestSwitcherCompare:
    @pytest.mark.asyncio
    async def test_preserves_order(self):
        GLOBAL_REGISTRY.register(_OkMethod())
        GLOBAL_REGISTRY.register(_CrashMethod())
        results = await GLOBAL_SWITCHER.compare(
            ["test.crash", "test.ok", "test.crash"],
            "some emr",
        )
        assert len(results) == 3
        assert [r.method_id for r in results] == [
            "test.crash", "test.ok", "test.crash"
        ]
        assert results[0].status == "error"
        assert results[1].status == "ok"
        assert results[2].status == "error"

    @pytest.mark.asyncio
    async def test_compare_with_empty_emr(self):
        GLOBAL_REGISTRY.register(_OkMethod())
        results = await GLOBAL_SWITCHER.compare(["test.ok"], "")
        assert results[0].status == "unavailable"


# ── MethodSwitcher.describe ──


class TestSwitcherDescribe:
    def test_describe_present(self):
        GLOBAL_REGISTRY.register(_OkMethod())
        meta = GLOBAL_SWITCHER.describe("test.ok")
        assert meta is not None
        assert meta["method_id"] == "test.ok"
        assert meta["method_family"] == "legacy"
        assert meta["available"] is True  # no required caps

    def test_describe_missing(self):
        assert GLOBAL_SWITCHER.describe("nope") is None

    def test_describe_unavailable_when_caps_missing(self, monkeypatch):
        monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
        with patch(
            "app.services.medcoder_index_health.index_health_check",
            return_value={"status": "degraded"},
        ):
            GLOBAL_REGISTRY.register(_NeedsRetriever())
            meta = GLOBAL_SWITCHER.describe("test.needs_retriever")
            assert meta["available"] is False