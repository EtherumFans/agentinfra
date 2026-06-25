"""CodingMethodRegistry — singleton SSOT for all registered methods.

The global instance is auto-populated by :func:`register_builtin_methods`
on package import. External ISV methods (Phase D — platform Agent Hub)
can be added at runtime via :meth:`CodingMethodRegistry.register`.
"""

from __future__ import annotations

from .base import CodingMethod


class CodingMethodRegistry:
    """Thread-unsafe in-memory registry (sufficient for FastAPI sync request handling).

    Methods are keyed by ``method_id``. Re-registering with the same
    ``method_id`` replaces the previous instance (last-writer-wins) —
    intentional for hot-reload during development and for ISV overrides
    (Phase D).
    """

    def __init__(self) -> None:
        self._methods: dict[str, CodingMethod] = {}

    def register(self, method: CodingMethod) -> None:
        if not method.method_id:
            raise ValueError(f"CodingMethod {method!r} has empty method_id")
        self._methods[method.method_id] = method

    def unregister(self, method_id: str) -> bool:
        return self._methods.pop(method_id, None) is not None

    def get(self, method_id: str) -> CodingMethod | None:
        return self._methods.get(method_id)

    def require(self, method_id: str) -> CodingMethod:
        """Get a method by id or raise KeyError. Use when absence is a bug."""
        m = self._methods.get(method_id)
        if m is None:
            raise KeyError(
                f"unknown coding method_id={method_id!r}; "
                f"available: {sorted(self._methods.keys())}"
            )
        return m

    def list(self) -> list[CodingMethod]:
        return list(self._methods.values())

    def filter(self, family: str | None = None) -> list[CodingMethod]:
        """List methods optionally filtered by family.

        Always returns :class:`CodingMethod` instances (never raw id
        strings), regardless of whether ``family`` is specified.
        """
        if family is None:
            return list(self._methods.values())
        return [m for m in self._methods.values() if m.method_family == family]

    def method_ids(self) -> list[str]:
        return sorted(self._methods.keys())

    def clear(self) -> None:
        """Remove all registered methods. Intended for test isolation."""
        self._methods.clear()

    def __contains__(self, method_id: object) -> bool:
        return isinstance(method_id, str) and method_id in self._methods

    def __len__(self) -> int:
        return len(self._methods)

    def __iter__(self):
        return iter(self._methods.values())


# Global singleton — import this everywhere.
GLOBAL_REGISTRY = CodingMethodRegistry()


def get_registry() -> CodingMethodRegistry:
    """Return the global registry. Convenience for callers that prefer
    function-style access."""
    return GLOBAL_REGISTRY


__all__ = ["CodingMethodRegistry", "GLOBAL_REGISTRY", "get_registry"]
