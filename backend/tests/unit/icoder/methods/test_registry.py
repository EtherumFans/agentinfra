"""CodingMethodRegistry tests (~12 cases).

Covers:
  - register / unregister / get / require / list / filter / method_ids
  - duplicate registration (last-writer-wins)
  - empty method_id rejected
  - clear() empties state
  - __contains__ / __len__ / __iter__
  - get_registry() returns GLOBAL_REGISTRY singleton
  - builtin auto-registration populates 9 methods (4 MedCodER + 4 legacy + 1 noop)

Note: ``conftest.py`` provides autouse fixture for GLOBAL_REGISTRY
isolation — no per-file fixture needed.
"""

from __future__ import annotations

import pytest

from icoder_runtime.methods.base import (
    CodingMethod,
    MethodCapability,
    MethodFamily,
    MethodResult,
)
from icoder_runtime.methods.registry import (
    GLOBAL_REGISTRY,
    CodingMethodRegistry,
    get_registry,
)


# ── Fixtures ──


@pytest.fixture
def fresh_registry() -> CodingMethodRegistry:
    """Return an isolated registry (clears current registrations)."""
    GLOBAL_REGISTRY.clear()
    yield GLOBAL_REGISTRY


class _StubMethod(CodingMethod):
    """Minimal concrete method for registry tests."""

    method_id: str = "test.stub"
    method_name: str = "Stub"
    method_family: str = "legacy"
    stage_count: int = 1
    required_capabilities = (MethodCapability.LLM,)
    description: str = "stub"

    async def run(self, emr_text, ctx=None):
        return MethodResult(
            method_id=self.method_id,
            method_name=self.method_name,
            method_family=self.method_family,
        )


class _StubMethod2(CodingMethod):
    method_id = "test.stub2"
    method_name = "Stub 2"
    method_family = "medcoder"
    stage_count = 5
    required_capabilities = (MethodCapability.LLM, MethodCapability.RETRIEVER)
    description = "another stub"

    async def run(self, emr_text, ctx=None):
        return MethodResult(method_id=self.method_id)


# ── Basic CRUD ──


class TestRegistryCRUD:
    def test_register_and_get(self, fresh_registry):
        m = _StubMethod()
        fresh_registry.register(m)
        assert fresh_registry.get("test.stub") is m

    def test_get_missing_returns_none(self, fresh_registry):
        assert fresh_registry.get("nope") is None

    def test_require_missing_raises(self, fresh_registry):
        with pytest.raises(KeyError) as excinfo:
            fresh_registry.require("nope")
        assert "nope" in str(excinfo.value)
        assert "available" in str(excinfo.value)

    def test_require_present(self, fresh_registry):
        m = _StubMethod()
        fresh_registry.register(m)
        assert fresh_registry.require("test.stub") is m

    def test_register_empty_id_raises(self, fresh_registry):
        class _NoId(CodingMethod):
            method_id = ""
            method_name = "noid"

            async def run(self, emr_text, ctx=None):
                return MethodResult()

        with pytest.raises(ValueError) as excinfo:
            fresh_registry.register(_NoId())
        assert "empty method_id" in str(excinfo.value)

    def test_unregister_returns_bool(self, fresh_registry):
        fresh_registry.register(_StubMethod())
        assert fresh_registry.unregister("test.stub") is True
        assert fresh_registry.unregister("test.stub") is False

    def test_duplicate_register_replaces(self, fresh_registry):
        a = _StubMethod()
        b = _StubMethod()  # same method_id
        fresh_registry.register(a)
        fresh_registry.register(b)
        assert fresh_registry.get("test.stub") is b


# ── Listing & filtering ──


class TestRegistryListing:
    def test_list(self, fresh_registry):
        fresh_registry.register(_StubMethod())
        fresh_registry.register(_StubMethod2())
        assert len(fresh_registry.list()) == 2

    def test_method_ids_sorted(self, fresh_registry):
        fresh_registry.register(_StubMethod())    # "test.stub"
        fresh_registry.register(_StubMethod2())   # "test.stub2"
        ids = fresh_registry.method_ids()
        assert ids == ["test.stub", "test.stub2"]

    def test_filter_by_family(self, fresh_registry):
        fresh_registry.register(_StubMethod())    # legacy
        fresh_registry.register(_StubMethod2())   # medcoder
        legacy = fresh_registry.filter(family="legacy")
        medcoder = fresh_registry.filter(family="medcoder")
        assert len(legacy) == 1
        assert legacy[0].method_id == "test.stub"
        assert len(medcoder) == 1
        assert medcoder[0].method_id == "test.stub2"

    def test_filter_unknown_family(self, fresh_registry):
        fresh_registry.register(_StubMethod())
        assert fresh_registry.filter(family="noop") == []

    def test_filter_no_family_returns_instances(self, fresh_registry):
        """Regression: filter(family=None) must return CodingMethod instances,
        not raw id strings (Phase B bug — used to break /coding-methods/list)."""
        fresh_registry.register(_StubMethod())
        fresh_registry.register(_StubMethod2())
        result = fresh_registry.filter()
        assert all(hasattr(m, "required_capabilities") for m in result)
        assert all(hasattr(m, "method_id") for m in result)
        ids = {m.method_id for m in result}
        assert ids == {"test.stub", "test.stub2"}

    def test_clear(self, fresh_registry):
        fresh_registry.register(_StubMethod())
        assert len(fresh_registry) == 1
        fresh_registry.clear()
        assert len(fresh_registry) == 0


# ── Dunder methods ──


class TestRegistryDunder:
    def test_contains_present(self, fresh_registry):
        fresh_registry.register(_StubMethod())
        assert "test.stub" in fresh_registry

    def test_contains_missing(self, fresh_registry):
        assert "nope" not in fresh_registry

    def test_contains_non_string(self, fresh_registry):
        assert 42 not in fresh_registry
        assert None not in fresh_registry

    def test_len(self, fresh_registry):
        fresh_registry.register(_StubMethod())
        fresh_registry.register(_StubMethod2())
        assert len(fresh_registry) == 2

    def test_iter(self, fresh_registry):
        fresh_registry.register(_StubMethod())
        fresh_registry.register(_StubMethod2())
        ids = {m.method_id for m in fresh_registry}
        assert ids == {"test.stub", "test.stub2"}


# ── Singleton & global state ──


class TestRegistryGlobal:
    def test_get_registry_returns_global(self):
        assert get_registry() is GLOBAL_REGISTRY

    def test_builtin_auto_registered(self):
        """Importing the package populates 10 methods."""
        from icoder_runtime.methods import get_registry as gr
        from icoder_runtime.methods.builtin import register_builtin_methods

        # Idempotent — ensure registered at least once.
        register_builtin_methods()
        ids = gr().method_ids()
        assert "medcoder.full" in ids
        assert "medcoder.prompt" in ids
        assert "medcoder.retrieve" in ids
        assert "medcoder.prompt+retrieve" in ids
        assert "medcoder.code_like_humans" in ids
        assert "legacy.deepseek" in ids
        assert "legacy.prompt_llm" in ids
        assert "legacy.hybrid" in ids
        assert "legacy.no_repair" in ids
        assert "noop.unavailable" in ids
        assert len(ids) == 10