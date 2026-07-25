# `code_validation/` — Python implementation module (retained)

**Status**: RETAINED_AS_PYTHON_IMPLEMENTATION per A1B-AE-R.2 §2 (2026-07-23).
**Former status**: LEGACY_CODE_ORPHAN per A1B-AE.9 (2026-07-22) — **refrained**.
**Pack metadata**: `code-validation/agent_pack.json` (dash-form canonical).

## What this dir is

This dir (`code_validation/`, underscore) is the **Python implementation
module** that backs the `icoder/code-validation-agent@2.0.0` Pack whose
metadata lives in the dash-form sibling `code-validation/agent_pack.json`.

It is NOT a duplicate Pack directory. The Python / Pack split is forced
by Python's identifier rule (module names cannot contain `-`), so the
canonical Corti-style Pack name `code-validation-agent` maps to:

- `code-validation/agent_pack.json` — Corti §6 manifest (dash-form, canonical)
- `code_validation/agent.py` — Python entry point imported by app + tests

## Why the dir is NOT deleted in A1B-AE-R.2

A1B-AE-R.2 §2 verified by grep that deletion is not possible without
breaking 4 active app importers + 7+ test files:

**App importers** (4):

- `app/main.py:1145` — `from official_agents.code_validation.agent import run as _cv_run`
- `app/icoder/mcp/handlers/validate_codes.py:44` — `from official_agents.code_validation.agent_legacy import run_legacy`
- `app/icoder/markdown_generator.py:248` — `generate_code_validation_markdown()`
- `app/icoder/mcp/tool_registry.py:466` — wraps `agent.py::run()` as MCP tool

**Test files** (7+):

- `tests/unit/icoder/agent_runtime/test_code_validation_v2.py`
- `tests/unit/icoder/agent_runtime/test_three_runnable_agents.py`
- `tests/integration/icoder/test_phase3d1_three_agents_a2a_smoke.py`
- `tests/integration/icoder/test_mcp_agent_tools_lifecycle.py`
- `tests/test_api/test_a1b_ae_9_tech_debt_liquidation.py`
- `tests/test_api/test_a1b_ae_4_agent_crud.py`
- `tests/test_services/test_agent_display_status.py`

Migration to a dash-form Python path is not achievable without renaming
to a Python-valid implementation module (e.g. `code_validation_impl/`),
which would touch all 11+ files above and is out-of-scope for R.2's
preset-materialization gate.

## What R.2 DID do instead

- Set `delegates_to_pack` on `icoder-cdi-preset`, `icoder-drg-dip-preset`,
  `icoder-claim-check-preset` in `icoder_preset_agents.json`
- Created `official_agents/claim-check/agent_pack.json` (new slim Pack)
- Added `POST /api/v1/agents/quick?from_preset=...` endpoint (Journey 7 fix)
- Reframed DEPRECATED.md notices in all 3 underscore dirs as
  RETAINED_AS_PYTHON_IMPLEMENTATION (this file + 2 siblings)

## Future migration path

If a future phase wants to unify naming, the cleanest path is:

1. Create `official_agents/_impl/` (single Python-valid namespace)
2. Move all underscore-form Python modules into `_impl/`
3. Update all 11+ import sites to the new path
4. Delete the 3 underscore dirs
5. Keep dash-form dirs as Pack metadata only

Estimated blast radius: 11+ files modified, 7+ test files rewritten.
NOT worth the churn for the preset-materialization gate.

## Charter §7 provenance

This file (DEPRECATED.md) is ICODER_INTERNAL provenance. It carries no
Corti-derived content.
