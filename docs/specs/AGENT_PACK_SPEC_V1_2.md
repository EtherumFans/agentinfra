# Agent Pack Spec v1.2 — Authoring + Compatibility Reference

**Date**: 2026-06-29
**Status**: Authoritative (P1.1)
**Audience**: Agent Pack authors + iCoDer Runtime maintainers

This document specifies the **v1.2** Agent Pack format (additive on v1.1)
and the loader-side compatibility rules. The implementation lives in
`backend/icoder_runtime/core/agent_pack_loader.py` and is the single
point of truth for "is this pack loadable?".

The older `AgentPackageV1.from_dict()` validator remains in place for
legacy v1.1-only callers but is no longer the runtime loader.

---

## 1. Why v1.2 exists

The pre-existing v1.1 schema (`AgentPackageV1`) was authored when only
two `agent_type` values existed (`certified` / `community`) and tools
were modeled as **string IDs with a `tier` field + `executor_file` for
community packs**.

Phase D (MedCodER Runtime Upgrade, 2026-06-22 … 2026-06-26) introduced
the **atomic-expert agent model**: instead of one "coding-expert"
umbrella, the MedCodER pipeline is composed of 4 atomic experts
(`evidence-extractor`, `index-navigator`, `code-reconciler`,
`tabular-validator`) plus one canonical reference implementation
(`medcoder-coding-review`). Each atomic expert:

* References real Python experts via MCP-style `tools[].ref` (e.g.
  `app.icoder.mcp.server:/mcp/v1/tools/call/search_icd`).
* Declares `system_prompt`, `tools`, `model`, `non_goals`,
  `output_contract` per expert (Q7 5件套 from `ICODER_V1_AGENT_CARD_SPEC.md`).
* Carries pipeline / non_goals / phi_redaction / human_review_required_when
  at the pack level.

These needs did not fit v1.1's tools[] shape, so v1.2 was introduced
as an **additive** schema — v1.1 packs continue to load.

The P1.0 baseline shipped with the **runtime validator rejecting v1.2**
(no expert-stub / reference agent types, no MCP refs) and a **Hub that
bypassed the validator** by reading `pack_data` raw. P1.1-A closes
this gap by introducing a single normalized loader that accepts both.

---

## 2. Format versions

| `format_version` | Status | Tool shape | Legal `agent_type` values |
|------------------|--------|------------|---------------------------|
| `1.1` | Legacy (still supported) | string IDs OR dict with `tier` + `executor_file` | `certified`, `community` |
| `1.2` | Current | string IDs OR dict with `type` (`mcp`/`guard`/`function`/`builtin`) + `ref` + `stage` | `certified`, `community`, `reference`, `expert-stub` |

Anything else → `INVALID` with `Unsupported format_version: 'X'. Expected one of ('1.1', '1.2').`

---

## 3. Agent types

| `agent_type` | Meaning | `production_ready` | `enabled_by_default` | Example |
|--------------|---------|--------------------|-----------------------|---------|
| `certified` | First-party iCoDer agents | `True` if has real experts OR tools; `False` if pure-prompt | `True` | `cdi-review`, `medical-coding-agent` |
| `community` | Third-party / ISV (Phase 4+) | `True` only if `code/` non-empty | `False` (tier 2 — sandbox) | (none shipped yet) |
| `reference` | Canonical reference impl — bypasses `hybrid_adapter` glue | `True` | `True` | `medcoder-coding-review-agent` |
| `expert-stub` | Atomic expert skeleton awaiting Phase D implementation | `False` | `True` | `evidence-extractor`, `index-navigator`, `code-reconciler`, `tabular-validator` |

**Authoring rule**: a pack marked `reference` MUST have at least one
expert with `system_prompt` + `tools[]` (a real Python impl, not just a
metadata card). A pack marked `expert-stub` MUST ship with the
`non_goals[]` and `output_contract` fields populated so the eventual
implementation can match the contract.

---

## 4. Required top-level fields

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `format_version` | ✅ | `"1.1"` or `"1.2"` | |
| `agent_type` | ✅ | string | see §3 |
| `agent_ref` | ✅ (loader warns + derives if missing) | `icoder/<slug>@<version>` | e.g. `icoder/cdi-review@1.0.0` |
| `manifest.name` | ✅ | string | display name |
| `manifest.version` | ✅ | semver string | |
| `manifest.description` | optional | string | |
| `manifest.category` | optional | string | default `"general"` |
| `manifest.icon` | optional | string (lucide icon name) | default `"Bot"` |
| `manifest.tags` | optional (v1.2) | list[string] | |
| `system_prompt` | ✅ | string | non-empty |
| `experts` | optional | list[dict] | empty list is legal (pure-prompt certified) |
| `tools` | optional | list[string \| dict] | mixed legacy + v1.2 entries tolerated |
| `code` | community only | dict<filename, source> | absent for certified / reference |
| `permissions` | optional | dict | see §6 |
| `requirements.min_runtime_version` | ✅ | semver string | |
| `llm_capabilities` | optional | dict | `required_models[]`, `supports_tool_calling`, `supports_json_mode`, `supports_mcp_tools` |
| `integrity.sha256` | optional | hex string | `AgentPackageV1` recomputes & verifies when present |

### v1.2-only optional fields

| Field | Type | Meaning |
|-------|------|---------|
| `model` | dict | `{primary, fallback, embedding, embedding_dim, temperature, max_tokens, json_mode}` |
| `pipeline` | dict | `{name, stages[], upstream_stage, downstream_stage}` |
| `non_goals` | list[string] | Hard rules this agent WILL NOT do |
| `output_contract` | dict | `{schema_ref, a2a_parts[], required_fields[], field_shapes{}, stage_trace_format{}}` |
| `phi_redaction` | `"required"` \| `"optional"` \| `"blocked"` | enforced by Context |
| `context_required` | bool | if true, A2A `contextId` is mandatory |
| `recorder_required` | bool | if true, M2aRecorder must persist every run |
| `metrics_required` | bool | if true, run metrics must be exported |
| `human_review_required_when` | list[string] | JEX-style conditions triggering manual review |
| `a2a` | dict | `{protocol_version, endpoint, discovery, agent_card_ref}` |

---

## 5. Tool formats (both versions)

The loader accepts **mixed** `tools[]` entries:

```jsonc
{
  "tools": [
    // v1.1 legacy string IDs
    "cdi_review",
    "check_documentation_gaps",

    // v1.1 dict with tier + executor_file (community packs)
    {"name": "do_thing", "tier": 1, "executor_file": "executor.py"},

    // v1.2 MCP-style ref
    {"name": "search_icd", "type": "mcp", "stage": "retrieval",
     "ref": "app.icoder.mcp.server:/mcp/v1/tools/call/search_icd",
     "input_schema": {...}, "output_schema": {...}},

    // v1.2 guard (pre/post pipeline hooks)
    {"name": "guard_input", "type": "guard", "stage": "pre-extraction",
     "ref": "app.icoder.guards.input_guard:guard_input"}
  ]
}
```

The loader normalizes each entry to `NormalizedTool` with a `kind` field
(`legacy` / `v1_1` / `v1_2_mcp` / `v1_2_guard` / `v1_2_function`).

---

## 6. Permissions

Both v1.1 and v1.2 use the same shape:

```jsonc
{
  "permissions": {
    "key": "medical-coding-default",
    "name": "医学编码默认权限",
    "description": "...",
    "tools": {
      "search_icd": "allowed",      // v1.2: string
      "writeback": "blocked",
      "guard_input": "allowed"
    },
    "production_writeback_blocked": true   // v1.2 (Phase D addition)
  }
}
```

v1.1 sometimes uses nested dicts instead of strings:

```jsonc
{
  "tools": {"cdi_review": {"allowed": true}}
}
```

The loader accepts both — it just records them on `permissions` and does
not validate the inner shape. The permissions action validation
(`allow` / `deny` / `require_human`) remains in `AgentPackageV1` for
strict v1.1 callers.

---

## 7. Output contract

v1.2 packs SHOULD declare:

```jsonc
{
  "output_contract": {
    "schema_ref": "icoder/MedicalCodingOutputSchema/v1",
    "a2a_parts": ["DataPart"],
    "required_fields": ["primary_diagnosis", "secondary_diagnoses", ...],
    "field_shapes": {"primary_diagnosis.code": "str", ...},
    "stage_trace_format": {
      "stage": "extraction|retrieval|merge|rerank|calibration",
      "status": "ok|failed|skipped",
      "latency_ms": "number",
      "input_count": "number",
      "output_count": "number",
      "summary": "string"
    }
  }
}
```

This is metadata — the loader records it on `NormalizedPack.output_contract`
but does not enforce it (no Pydantic round-trip).

---

## 8. Status classification rules

The loader assigns one of three statuses (see
`agent_pack_schema.PackStatus`):

| Status | Condition |
|--------|-----------|
| `INVALID` | At least one `validation_error` (missing required field, unsupported format_version, etc.) |
| `METADATA_ONLY` | No errors, but cannot be dispatched: `expert-stub` with no real expert, OR `community` with no `code/`, OR no experts + no tools |
| `EXECUTABLE` | No errors + at least one of: real experts, real tools, executable code |

`production_ready` is True only for:

* `certified` with real experts OR tools, AND
* `reference` (canonical reference impl, MedCodER family), AND
* `community` with `code/`

Expert-stub packs and pure-prompt certified packs are
`production_ready=False` by design (per P1.1 honest-classification
rule — "no experimental/metadata-only marked production-ready").

---

## 9. Migration guide (v1.1 → v1.2)

To port a v1.1 pack to v1.2:

1. Bump `format_version` from `"1.1"` to `"1.2"`.
2. Add `agent_ref: "icoder/<slug>@<version>"` if missing.
3. Convert any string tool IDs to dict form with `type: "function"` if
   you want stage / description metadata (otherwise keep them as
   strings — both shapes are legal in v1.2).
4. Add `model`, `pipeline`, `non_goals`, `output_contract`,
   `phi_redaction`, `permissions.production_writeback_blocked` if the
   pack dispatches to LLM / tools / external systems.
5. Keep `experts[]` flat unless you have multiple atomic experts.
6. Verify with:
   ```bash
   PYTHONIOENCODING=utf-8 python -c "
   from icoder_runtime.core.agent_pack_loader import load_pack
   import json, sys
   p = load_pack(json.load(open('agent_pack.json')))
   print(p.status.value, p.production_ready, p.validation_errors, p.validation_warnings)
   "
   ```

---

## 10. Example v1.2 pack (minimal)

```jsonc
{
  "format_version": "1.2",
  "agent_type": "expert-stub",
  "agent_ref": "icoder/my-expert@1.0.0",
  "manifest": {
    "name": "My Expert",
    "version": "1.0.0",
    "description": "...",
    "category": "general",
    "icon": "Bot",
    "tags": ["example"]
  },
  "system_prompt": "You are my expert. ...",
  "experts": [
    {
      "id": "my-expert",
      "name": "My Expert",
      "role": "primary",
      "description": "...",
      "system_prompt": "...",
      "tools": ["search_icd"],
      "model": "deepseek-v4",
      "non_goals": ["不写回 EMR/HIS"],
      "output_contract": {"schema_ref": "icoder/MyExpertOutput/v1"}
    }
  ],
  "tools": [
    {"name": "search_icd", "type": "mcp", "stage": "retrieval",
     "ref": "app.icoder.mcp.server:/mcp/v1/tools/call/search_icd"}
  ],
  "model": {"primary": "deepseek-v4", "temperature": 0.0, "json_mode": true},
  "permissions": {"key": "my-expert-default", "tools": {"writeback": "blocked"}, "production_writeback_blocked": true},
  "phi_redaction": "required",
  "context_required": true,
  "recorder_required": true,
  "requirements": {"min_runtime_version": "2.0.0"},
  "llm_capabilities": {"required_models": [{"name": "deepseek-v4"}], "supports_tool_calling": true, "supports_json_mode": true}
}
```

This pack would be classified: `metadata_only`, `production_ready=False`
(because `expert-stub` is not production-ready by definition).

---

## 11. What's NOT in the spec (out of scope)

* **Marketplace publishing** (Phase 4+, not in P1.1)
* **Visual pack editor** (P2+, not in P1.1)
* **Sandbox execution of `community.code/`** (tier 2 enforcement
  happens via the registry's `enabled_by_default=False`, not the loader)
* **Schema validation of `output_contract`** (metadata only — runtime
  contract enforcement lives in the agents themselves)
* **Pack signing beyond `integrity.sha256`** (the existing
  `AgentPackageV1` recomputes and verifies the hash when present; this
  is unchanged)

---

## 12. Cross-references

* `backend/icoder_runtime/core/agent_pack_schema.py` — `NormalizedPack`,
  `NormalizedTool`, `NormalizedExpert`, `PackStatus`, constants.
* `backend/icoder_runtime/core/agent_pack_loader.py` — `load_pack`,
  `load_packs_from_dir`, `summary_counts`, `why_not_executable`.
* `backend/icoder_runtime/core/agent_pack_v1.py` — legacy strict v1.1
  validator (kept for back-compat; not the runtime loader).
* `docs/productization/P1_1_BASELINE.md` — baseline audit (16 packs,
  6 failing under v1.1 validator, all 16 loadable via the new loader).
* `docs/specs/ICODER_V1_AGENT_CARD_SPEC.md` — Q7 5件套 (system_prompt /
  tools / model / non_goals / output_contract) rationale.