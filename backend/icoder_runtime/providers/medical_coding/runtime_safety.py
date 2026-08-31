"""Fail-closed runtime checks for native dependencies seen crashing on Windows.

Native access violations cannot be caught by Python.  Keep known-crashing
Windows dependency combinations out of the process unless an operator has
explicitly accepted that risk after validating a replacement build.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version


@dataclass(frozen=True)
class BGERuntimeSafety:
    safe: bool
    reason: str
    torch_version: str | None = None
    sentence_transformers_version: str | None = None


@dataclass(frozen=True)
class PyArrowRuntimeSafety:
    safe: bool
    reason: str
    pyarrow_version: str | None = None
    python_version: str = ""


def _package_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def assess_sentence_transformer_runtime_safety(
    *,
    override_env: str = "ICODER_ALLOW_UNSAFE_WINDOWS_SENTENCE_TRANSFORMERS",
) -> BGERuntimeSafety:
    """Return whether loading sentence-transformers is safe in this process.

    The access violation was observed in ``torch_cpu.dll`` during a local
    sentence-transformers workload, so the protection applies to every local
    model using that native stack, not only BGE-M3.
    """
    torch_version = _package_version("torch")
    sentence_version = _package_version("sentence-transformers")

    if os.environ.get(override_env) == "1":
        return BGERuntimeSafety(
            safe=True,
            reason="operator_override",
            torch_version=torch_version,
            sentence_transformers_version=sentence_version,
        )

    if os.name == "nt" and torch_version == "2.11.0" and sentence_version == "3.2.1":
        return BGERuntimeSafety(
            safe=False,
            reason=(
                "known_unsafe_windows_native_stack: torch 2.11.0 + "
                "sentence-transformers 3.2.1 has produced torch_cpu.dll "
                "access violations; use a validated dependency build or an "
                "isolated Linux retrieval service"
            ),
            torch_version=torch_version,
            sentence_transformers_version=sentence_version,
        )

    return BGERuntimeSafety(
        safe=True,
        reason="no_known_native_conflict",
        torch_version=torch_version,
        sentence_transformers_version=sentence_version,
    )


def assess_bge_runtime_safety() -> BGERuntimeSafety:
    """Return whether loading local BGE-M3 is safe in this interpreter.

    ``MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE=1`` is deliberately separate from
    ``MEDCODER_SUBPROCESS=1``: choosing process isolation does not mean an
    operator accepted a dependency combination already observed crashing
    inside ``torch_cpu.dll``.
    """
    if os.environ.get("ICODER_DISABLE_NATIVE_MEDCODER", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }:
        return BGERuntimeSafety(
            safe=False,
            reason="operator_disabled_native_medcoder",
            torch_version=_package_version("torch"),
            sentence_transformers_version=_package_version("sentence-transformers"),
        )
    return assess_sentence_transformer_runtime_safety(
        override_env="MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE"
    )


def assess_pyarrow_runtime_safety(
    *, override_env: str = "ICODER_ALLOW_UNSAFE_WINDOWS_PYARROW",
) -> PyArrowRuntimeSafety:
    """Fail closed for the exact PyArrow build observed crashing this host.

    This function reads distribution metadata only and never imports PyArrow.
    The guard is intentionally narrow: it records an observed unsafe Windows
    build rather than claiming that every PyArrow version is unsafe.
    """
    pyarrow_version = _package_version("pyarrow")
    python_version = platform.python_version()
    if os.environ.get(override_env) == "1":
        return PyArrowRuntimeSafety(
            safe=True,
            reason="operator_override",
            pyarrow_version=pyarrow_version,
            python_version=python_version,
        )
    if os.name == "nt" and pyarrow_version == "24.0.0":
        return PyArrowRuntimeSafety(
            safe=False,
            reason=(
                "known_unsafe_windows_native_stack: pyarrow 24.0.0 has "
                "produced both write and read access violations in arrow.dll "
                "on this development host; use an isolated disposable process "
                "or a separately validated build"
            ),
            pyarrow_version=pyarrow_version,
            python_version=python_version,
        )
    return PyArrowRuntimeSafety(
        safe=True,
        reason="no_known_native_conflict",
        pyarrow_version=pyarrow_version,
        python_version=python_version,
    )


__all__ = [
    "BGERuntimeSafety",
    "PyArrowRuntimeSafety",
    "assess_bge_runtime_safety",
    "assess_pyarrow_runtime_safety",
    "assess_sentence_transformer_runtime_safety",
]
