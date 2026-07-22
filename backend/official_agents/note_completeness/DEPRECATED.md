# DEPRECATED — `note_completeness/` (legacy underscore-form Pack)

**Status**: LEGACY_CODE_ORPHAN per A1B-AE.2 §3 (architecture reconciliation).
**Filed**: A1B-AE.9 (2026-07-22).
**Superseded by**: `note-completeness/` (dash-form canonical Pack).

## Why this is deprecated

A1B-AE.2 §3 identified three dual-named Pack pairs where the legacy
underscore-form had only Python code and no `agent_pack.json` manifest.
`note_completeness/` is one of the three (alongside `code_validation/`
and `compliance_guardrail/`).

The dash-form counterpart (`note-completeness/`) is the canonical name.
A1B-AE.4 Migration 023 + AliasResolver handle alias resolution so
existing callers that reference `note_completeness` continue to work.

## Why this dir is not deleted in A1B-AE.9

One call site still imports from this dir as of A1B-AE.9:

- `app/icoder/mcp/handlers/check_documentation_gaps.py` — `from
  official_agents.note_completeness.agent import run as _run`

Deleting the dir would break this call site. A safe deletion requires
migrating the call site to the dash-form path first — out-of-scope for
A1B-AE.9. The dir is marked DEPRECATED here so future readers know it
is on the deletion roadmap.

## Deletion roadmap

Target: a future A1B phase that explicitly migrates the
`check_documentation_gaps` call site. The roadmap item is recorded in
the A1B-AE.11 final reconciliation report.

## Charter §7 provenance

This file (DEPRECATED.md) is ICODER_INTERNAL provenance. It carries no
Corti-derived content.
