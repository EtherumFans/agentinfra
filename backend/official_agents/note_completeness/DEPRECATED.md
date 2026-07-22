# `note_completeness/` — Python implementation module (retained)

**Status**: RETAINED_AS_PYTHON_IMPLEMENTATION per A1B-AE-R.2 §2 (2026-07-23).
**Former status**: LEGACY_CODE_ORPHAN per A1B-AE.9 (2026-07-22) — **refrained**.
**Pack metadata**: `note-completeness/agent_pack.json` (dash-form canonical).

## What this dir is

This dir (`note_completeness/`, underscore) is the **Python implementation
module** that backs the `icoder/note-completeness-agent@1.0.0` Pack whose
metadata lives in the dash-form sibling `note-completeness/agent_pack.json`.

It is NOT a duplicate Pack directory. The Python / Pack split is forced
by Python's identifier rule (module names cannot contain `-`), so the
canonical Corti-style Pack name `note-completeness-agent` maps to:

- `note-completeness/agent_pack.json` — Corti §6 manifest (dash-form, canonical)
- `note_completeness/agent.py` — Python entry point imported by app + tests

## Why the dir is NOT deleted in A1B-AE-R.2

A1B-AE-R.2 §2 verified by grep that deletion is not possible without
breaking active app importers + test files:

**App importers**:

- `app/icoder/mcp/handlers/check_documentation_gaps.py:30` — `from official_agents.note_completeness.agent import run as _run`
- `app/icoder/markdown_generator.py:455` — `generate_note_completeness_markdown()`
- `app/icoder/mcp/tool_registry.py:466` — wraps `agent.py::run()` as MCP tool
- `app/icoder/agent_runtime/orchestrator/coding_compliance_orchestrator.py:389` — references `note_completeness:score` label

**Test files**:

- `tests/unit/icoder/agent_runtime/test_three_runnable_agents.py`
- `tests/integration/icoder/test_phase3d1_three_agents_a2a_smoke.py`
- `tests/test_api/test_a1b_ae_9_tech_debt_liquidation.py`

## What R.2 DID do instead

See `../code_validation/DEPRECATED.md` for the full list.

## Future migration path

Same as `../code_validation/DEPRECATED.md` §Future migration path.

## Charter §7 provenance

This file (DEPRECATED.md) is ICODER_INTERNAL provenance. It carries no
Corti-derived content.
