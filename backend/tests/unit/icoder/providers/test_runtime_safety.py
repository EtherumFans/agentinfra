"""Native dependency safety gates for local BGE-M3 retrieval."""

from __future__ import annotations

from icoder_runtime.providers.medical_coding import runtime_safety


def test_explicit_native_medcoder_disable_wins_on_every_host(monkeypatch):
    monkeypatch.setattr(runtime_safety.os, "name", "posix")
    monkeypatch.setattr(runtime_safety, "_package_version", lambda _name: "safe")
    monkeypatch.setenv("ICODER_DISABLE_NATIVE_MEDCODER", "true")
    monkeypatch.setenv("MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE", "1")

    verdict = runtime_safety.assess_bge_runtime_safety()

    assert verdict.safe is False
    assert verdict.reason == "operator_disabled_native_medcoder"


def test_known_windows_torch_stack_fails_closed(monkeypatch):
    monkeypatch.setattr(runtime_safety.os, "name", "nt")
    versions = {
        "torch": "2.11.0",
        "sentence-transformers": "3.2.1",
    }
    monkeypatch.setattr(runtime_safety, "_package_version", versions.get)
    monkeypatch.delenv("MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE", raising=False)
    monkeypatch.delenv("ICODER_DISABLE_NATIVE_MEDCODER", raising=False)

    verdict = runtime_safety.assess_bge_runtime_safety()
    assert verdict.safe is False
    assert "torch_cpu.dll" in verdict.reason


def test_operator_override_is_explicit_and_auditable(monkeypatch):
    monkeypatch.setattr(runtime_safety.os, "name", "nt")
    monkeypatch.setattr(runtime_safety, "_package_version", lambda _name: "unsafe")
    monkeypatch.setenv("MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE", "1")
    monkeypatch.delenv("ICODER_DISABLE_NATIVE_MEDCODER", raising=False)

    verdict = runtime_safety.assess_bge_runtime_safety()
    assert verdict.safe is True
    assert verdict.reason == "operator_override"


def test_posix_runtime_is_not_blocked_by_windows_rule(monkeypatch):
    monkeypatch.setattr(runtime_safety.os, "name", "posix")
    monkeypatch.setattr(runtime_safety, "_package_version", lambda _name: "2.11.0")
    monkeypatch.delenv("MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE", raising=False)
    monkeypatch.delenv("ICODER_DISABLE_NATIVE_MEDCODER", raising=False)

    assert runtime_safety.assess_bge_runtime_safety().safe is True


def test_generic_sentence_transformer_gate_uses_separate_override(monkeypatch):
    monkeypatch.setattr(runtime_safety.os, "name", "nt")
    versions = {"torch": "2.11.0", "sentence-transformers": "3.2.1"}
    monkeypatch.setattr(runtime_safety, "_package_version", versions.get)
    monkeypatch.setenv("MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE", "1")
    monkeypatch.delenv(
        "ICODER_ALLOW_UNSAFE_WINDOWS_SENTENCE_TRANSFORMERS", raising=False
    )

    verdict = runtime_safety.assess_sentence_transformer_runtime_safety()

    assert verdict.safe is False
    assert "torch_cpu.dll" in verdict.reason


def test_observed_windows_pyarrow_build_fails_closed_without_import(monkeypatch):
    monkeypatch.setattr(runtime_safety.os, "name", "nt")
    monkeypatch.setattr(
        runtime_safety, "_package_version",
        lambda name: "24.0.0" if name == "pyarrow" else None,
    )
    monkeypatch.delenv("ICODER_ALLOW_UNSAFE_WINDOWS_PYARROW", raising=False)

    verdict = runtime_safety.assess_pyarrow_runtime_safety()

    assert verdict.safe is False
    assert verdict.pyarrow_version == "24.0.0"
    assert "arrow.dll" in verdict.reason
    assert "read" in verdict.reason and "write" in verdict.reason


def test_pyarrow_guard_is_narrow_and_override_is_explicit(monkeypatch):
    monkeypatch.setattr(runtime_safety.os, "name", "nt")
    monkeypatch.setattr(runtime_safety, "_package_version", lambda _name: "23.0.0")
    assert runtime_safety.assess_pyarrow_runtime_safety().safe is True

    monkeypatch.setattr(runtime_safety, "_package_version", lambda _name: "24.0.0")
    monkeypatch.setenv("ICODER_ALLOW_UNSAFE_WINDOWS_PYARROW", "1")
    verdict = runtime_safety.assess_pyarrow_runtime_safety()
    assert verdict.safe is True
    assert verdict.reason == "operator_override"
