"""Early fail-closed guard for native Python builds known to crash this host.

Python exceptions cannot catch an access violation raised while a native
extension is being loaded.  Runtime call-site checks are therefore too late
when an optional dependency imports the same extension indirectly (for
example transformers -> sklearn -> pandas -> pyarrow).  This import finder is
installed by :mod:`app` before application modules load and rejects only exact
Windows package combinations observed to crash.  It reads distribution
metadata without importing the affected packages.
"""
from __future__ import annotations

import os
import sys
from importlib.abc import MetaPathFinder
from importlib.metadata import PackageNotFoundError, version
from importlib.machinery import ModuleSpec


_TRUTHY = {"1", "true", "yes", "on"}


def _enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in _TRUTHY


def _package_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def blocked_native_roots() -> dict[str, str]:
    """Return exact top-level packages that must not load in this process."""
    if os.name != "nt":
        return {}

    blocked: dict[str, str] = {}
    pyarrow_version = _package_version("pyarrow")
    if (
        pyarrow_version == "24.0.0"
        and not _enabled("ICODER_ALLOW_UNSAFE_WINDOWS_PYARROW")
    ):
        blocked["pyarrow"] = (
            "pyarrow 24.0.0 is disabled after observed arrow.dll access "
            "violations on Windows"
        )

    native_disabled = _enabled("ICODER_DISABLE_NATIVE_MEDCODER")
    unsafe_sentence_stack = (
        _package_version("torch") == "2.11.0"
        and _package_version("sentence-transformers") == "3.2.1"
    )
    sentence_override = (
        _enabled("ICODER_ALLOW_UNSAFE_WINDOWS_SENTENCE_TRANSFORMERS")
        or _enabled("MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE")
    )
    if native_disabled or (unsafe_sentence_stack and not sentence_override):
        blocked["sentence_transformers"] = (
            "the installed Windows sentence-transformers/Torch native stack "
            "is disabled by runtime safety policy"
        )
    return blocked


class KnownUnsafeNativeImportFinder(MetaPathFinder):
    """Reject imports before Python asks a known-unsafe extension to load."""

    marker = "icoder-known-unsafe-native-import-guard-v1"

    def __init__(self, blocked_roots: dict[str, str]) -> None:
        self.blocked_roots = dict(blocked_roots)

    def find_spec(
        self,
        fullname: str,
        path: object | None = None,
        target: object | None = None,
    ) -> ModuleSpec | None:
        del path, target
        root = fullname.split(".", 1)[0]
        reason = self.blocked_roots.get(root)
        if reason:
            raise ModuleNotFoundError(
                f"{fullname} is unavailable: {reason}",
                name=fullname,
            )
        return None


def install_known_unsafe_native_import_guard() -> KnownUnsafeNativeImportFinder | None:
    """Install one process-wide finder when an exact unsafe build is present."""
    for finder in sys.meta_path:
        if getattr(finder, "marker", None) == KnownUnsafeNativeImportFinder.marker:
            return finder  # type: ignore[return-value]
    blocked = blocked_native_roots()
    if not blocked:
        return None
    finder = KnownUnsafeNativeImportFinder(blocked)
    sys.meta_path.insert(0, finder)
    return finder


__all__ = [
    "KnownUnsafeNativeImportFinder",
    "blocked_native_roots",
    "install_known_unsafe_native_import_guard",
]
