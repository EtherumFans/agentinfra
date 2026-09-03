# `compliance_guardrail/` — Python implementation module (retained)

**Status**: RETAINED_AS_PYTHON_IMPLEMENTATION per A1B-AE-R.2 §2 (2026-07-23).
**Former status**: LEGACY_CODE_ORPHAN per A1B-AE.9 (2026-07-22) — **refrained**.
**Pack metadata**: `compliance-guardrail/agent_pack.json` (dash-form canonical).

## What this dir is

This dir (`compliance_guardrail/`, underscore) is the **Python implementation
module** that backs the `icoder/compliance-guardrail-agent@1.0.0` Pack whose
metadata lives in the dash-form sibling `compliance-guardrail/agent_pack.json`.

It is NOT a duplicate Pack directory. The Python / Pack split is forced
by Python's identifier rule (module names cannot contain `-`), so the
canonical Corti-style Pack name `compliance-guardrail-agent` maps to:

- `compliance-guardrail/agent_pack.json` — Corti §6 manifest (dash-form, canonical)
- `compliance_guardrail/agent.py` — Python entry point imported by app + tests

## Why the dir is NOT deleted in A1B-AE-R.2

A1B-AE-R.2 §2 verified by grep that deletion is not possible without
breaking active app importers + test files:

**App importers**:

- `app/icoder/mcp/handlers/evaluate_compliance.py:32` — `from official_agents.compliance_guardrail.agent import run as _run`
- `app/icoder/markdown_generator.py:343` — `generate_compliance_guardrail_markdown()`
- `app/icoder/mcp/tool_registry.py:466` — wraps `agent.py::run()` as MCP tool

**Test files**:

- `tests/unit/icoder/agent_runtime/test_three_runnable_agents.py`
- `tests/integration/icoder/test_phase3d1_three_agents_a2a_smoke.py`
- `tests/test_api/test_a1b_ae_9_tech_debt_liquidation.py`

Additionally `compliance_guardrail/agent.py` itself imports from
`code_validation/agent_legacy.py` (the sibling underscore dir), so the
two are entangled — both must be migrated together or neither.

## What R.2 DID do instead

See `../code_validation/DEPRECATED.md` for the full list. R.2 retained
both entangled dirs and updated their DEPRECATED.md notices to reflect
the retention rationale.

## Future migration path

Same as `../code_validation/DEPRECATED.md` §Future migration path.

## Charter §7 provenance

This file (DEPRECATED.md) is ICODER_INTERNAL provenance. It carries no
Corti-derived content.
