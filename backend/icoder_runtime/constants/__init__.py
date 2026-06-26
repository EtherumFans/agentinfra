"""iCoDer Runtime — shared constants (SSOT).

Phase D3 (2026-06-26): consolidate the legacy ``homepage-coding-review``
14-stage constants into a single source of truth. The new values reflect
the canonical MedCodER 5-stage pipeline; the values here are imported
by report generators, API handlers, and tests.

Convention: every constant is named and documented in this package
only. Callers import from ``icoder_runtime.constants.coding_review_constants``
— never from ``official_agents.homepage_coding_review`` (the deprecated
shim was removed in Phase D3).
"""
