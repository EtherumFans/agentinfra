# DEPRECATED — `compliance_guardrail/` (legacy underscore-form Pack)

**Status**: LEGACY_CODE_ORPHAN per A1B-AE.2 §3 (architecture reconciliation).
**Filed**: A1B-AE.9 (2026-07-22).
**Superseded by**: `compliance-guardrail/` (dash-form canonical Pack).

## Why this is deprecated

A1B-AE.2 §3 identified three dual-named Pack pairs where the legacy
underscore-form had only Python code and no `agent_pack.json` manifest.
`compliance_guardrail/` is one of the three (alongside `code_validation/`
and `note_completeness/`).

The dash-form counterpart (`compliance-guardrail/`) is the canonical
name. A1B-AE.4 Migration 023 + AliasResolver handle alias resolution so
existing callers that reference `compliance_guardrail` continue to work.

## Why this dir is not deleted in A1B-AE.9

One call site still imports from this dir as of A1B-AE.9:

- `app/icoder/mcp/handlers/evaluate_compliance.py` — `from
  official_agents.compliance_guardrail.agent import run as _run`

Additionally `compliance_guardrail/agent.py` itself imports from
`code_validation/agent_legacy.py` (the other deprecated dir), so the
two are entangled.

Deleting the dir would break these call sites. A safe deletion requires
migrating the call sites to the dash-form path first — out-of-scope for
A1B-AE.9. The dir is marked DEPRECATED here so future readers know it
is on the deletion roadmap.

## Deletion roadmap

Target: a future A1B phase that explicitly migrates the call sites in
both `compliance_guardrail/` and `code_validation/` (the two are
entangled via the `_normalize_input` import). The roadmap item is
recorded in the A1B-AE.11 final reconciliation report.

## Charter §7 provenance

This file (DEPRECATED.md) is ICODER_INTERNAL provenance. It carries no
Corti-derived content.
