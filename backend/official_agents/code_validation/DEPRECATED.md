# DEPRECATED — `code_validation/` (legacy underscore-form Pack)

**Status**: LEGACY_CODE_ORPHAN per A1B-AE.2 §3 (architecture reconciliation).
**Filed**: A1B-AE.9 (2026-07-22).
**Superseded by**: `code-validation/` (dash-form canonical Pack).

## Why this is deprecated

A1B-AE.2 §3 identified three dual-named Pack pairs where the legacy
underscore-form had only Python code (`__init__.py`, `agent.py`,
`agent_legacy.py`) and no `agent_pack.json` manifest:

- `code_validation/` ← this dir
- `compliance_guardrail/`
- `note_completeness/`

The dash-form counterparts (`code-validation/`, etc.) are the canonical
names: they match Corti public convention and carry the Pack manifest.
A1B-AE.4 Migration 023 + AliasResolver (app/services/alias_resolver.py)
handle the application-layer alias resolution so existing callers that
reference `code_validation` continue to work.

## Why this dir is not deleted in A1B-AE.9

Two call sites still import from this dir as of A1B-AE.9:

- `app/icoder/mcp/handlers/validate_codes.py` — `from
  official_agents.code_validation.agent_legacy import run_legacy`
- `app/main.py:1145` — `from official_agents.code_validation.agent
  import run as _cv_run`

Deleting the dir would break these call sites. A safe deletion requires
either:
1. Migrating the call sites to the dash-form path first, OR
2. Re-implementing the legacy entry points inside the dash-form Pack.

Both are out-of-scope for A1B-AE.9. The dir is marked DEPRECATED here
so future readers know it is on the deletion roadmap.

## Deletion roadmap

Target: a future A1B phase that explicitly migrates the 2 call sites
above. The roadmap item is recorded in the A1B-AE.11 final
reconciliation report.

## Charter §7 provenance

This file (DEPRECATED.md) is ICODER_INTERNAL provenance. It carries no
Corti-derived content.
