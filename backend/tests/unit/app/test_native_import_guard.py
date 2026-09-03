from __future__ import annotations

import importlib

import pytest

import app.native_import_guard as guard


def test_finder_rejects_only_configured_top_level_package() -> None:
    finder = guard.KnownUnsafeNativeImportFinder({
        "pyarrow": "synthetic known-unsafe build",
    })

    with pytest.raises(ModuleNotFoundError, match="synthetic known-unsafe build"):
        finder.find_spec("pyarrow.lib")
    assert finder.find_spec("pandas") is None


def test_windows_exact_builds_fail_closed_without_importing_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = {
        "pyarrow": "24.0.0",
        "torch": "2.11.0",
        "sentence-transformers": "3.2.1",
    }
    monkeypatch.setattr(guard.os, "name", "nt")
    monkeypatch.setattr(guard, "_package_version", versions.get)
    for name in (
        "ICODER_ALLOW_UNSAFE_WINDOWS_PYARROW",
        "ICODER_ALLOW_UNSAFE_WINDOWS_SENTENCE_TRANSFORMERS",
        "MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE",
        "ICODER_DISABLE_NATIVE_MEDCODER",
    ):
        monkeypatch.delenv(name, raising=False)

    assert set(guard.blocked_native_roots()) == {
        "pyarrow",
        "sentence_transformers",
    }


def test_explicit_overrides_are_narrow_and_native_disable_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    versions = {
        "pyarrow": "24.0.0",
        "torch": "2.11.0",
        "sentence-transformers": "3.2.1",
    }
    monkeypatch.setattr(guard.os, "name", "nt")
    monkeypatch.setattr(guard, "_package_version", versions.get)
    monkeypatch.setenv("ICODER_ALLOW_UNSAFE_WINDOWS_PYARROW", "1")
    monkeypatch.setenv("MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE", "1")
    monkeypatch.delenv("ICODER_DISABLE_NATIVE_MEDCODER", raising=False)
    assert guard.blocked_native_roots() == {}

    monkeypatch.setenv("ICODER_DISABLE_NATIVE_MEDCODER", "true")
    assert set(guard.blocked_native_roots()) == {"sentence_transformers"}


def test_real_app_installation_is_idempotent() -> None:
    first = guard.install_known_unsafe_native_import_guard()
    second = guard.install_known_unsafe_native_import_guard()
    assert first is second
    if first is not None:
        assert first in importlib.import_module("sys").meta_path
