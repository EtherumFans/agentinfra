# Phase 4-A — `agent_pack.json` Backend Provider Schema

**Document type:** Schema spec
**Date:** 2026-07-07
**Author:** SONG Luhua
**Scope:** `format_version: "1.2"` extension to `agent_pack.json`. Adds `backend_provider` + `backend_config` fields. Fully backward compatible — packs without these fields load via the legacy rule-engine path.

---

## 1. Motivation

Before Phase 4-A, every iCoDer agent implicitly used the rule-engine backend. There was no way to declare "this agent is a pure-LLM agent" or "this agent is an LLM-with-tools agent" in the pack. The runtime executor had to branch on agent_id or use heuristics.

Phase 4-A makes the backend form **declarative**. An agent pack says `backend_provider: "icoder.pure-llm.v1"` and the runtime knows to invoke `PureLLMProvider` — no branching, no heuristics.

## 2. Schema extension (format_version 1.2)

Two new optional fields:

| Field | Type | Default | Where it can live |
|-------|------|---------|-------------------|
| `backend_provider` | `string` | `""` (empty = legacy) | top-level OR `agent.backend_provider` |
| `backend_config` | `dict` | `{}` | top-level OR `agent.backend_config` |

Both fields can appear at the top level of the pack OR nested under the `agent` sub-object. The loader checks top-level first, then `agent.*`. This lets pack authors choose whichever placement fits their pack's existing structure.

### 2.1 Example: top-level placement

```json
{
  "format_version": "1.2",
  "agent_type": "certified",
  "agent_ref": "icoder/code-validation@1.0.0",
  "manifest": {"name": "Code Validation", "version": "1.0.0"},
  "system_prompt": "...",
  "requirements": {"min_runtime_version": "1.0.0"},
  "backend_provider": "icoder.llm-with-tools.v1",
  "backend_config": {
    "tools": {
      "scope": ["verify", "guidelines", "explore", "search"],
      "mandatory": ["verify", "guidelines"],
      "forbidden": []
    }
  }
}
```

### 2.2 Example: nested placement

```json
{
  "format_version": "1.2",
  "agent_type": "certified",
  "agent_ref": "icoder/note-completeness@1.0.0",
  "manifest": {"name": "Note Completeness", "version": "1.0.0"},
  "system_prompt": "...",
  "requirements": {"min_runtime_version": "1.0.0"},
  "agent": {
    "backend_provider": "icoder.pure-llm.v1",
    "backend_config": {
      "llm": {"model": "deepseek-v4-flash", "temperature": 0.0}
    }
  }
}
```

### 2.3 Example: legacy pack (no backend fields)

```json
{
  "format_version": "1.0",
  "agent_type": "certified",
  "agent_ref": "icoder/compliance-guardrail@1.0.0",
  "manifest": {"name": "Compliance Guardrail", "version": "1.0.0"},
  "system_prompt": "..."
}
```

Loads with `backend_provider=""` and `backend_config={}`. The runtime resolves to `DEFAULT_FALLBACK_PROVIDER_ID = "icoder.rule-engine.v1"` via `ProviderRegistry.get_or_default("")`.

## 3. `backend_provider` field

- **Type:** string
- **Allowed values:** any registered `provider_id` (e.g. `icoder.rule-engine.v1`, `icoder.pure-llm.v1`, `icoder.llm-with-tools.v1`, plus Phase 4-D meta-providers `icoder.cascade.v1`, `icoder.ensemble.v1`, etc.).
- **Empty string:** treated as "use default fallback" (legacy v1.0 packs).
- **Non-string value:** validation warning, falls back to empty (treated as legacy).
- **Unknown provider_id:** loads fine at pack-load time (deferred resolution). At run time, `ProviderRegistry.get(provider_id)` raises `ProviderNotRegisteredError` with an actionable message.

## 4. `backend_config` field

- **Type:** dict
- **Default:** `{}`
- **Non-dict value:** validation warning, falls back to `{}`.
- **Contents:** provider-specific. Each provider documents its own schema in its module docstring.

### 4.1 Common sub-field: `tools`

Used by `LLMWithToolsProvider` (and any future provider with `supports_tool_calling=True`):

```json
"backend_config": {
  "tools": {
    "scope": ["verify", "guidelines", "explore", "search"],
    "mandatory": ["verify", "guidelines"],
    "forbidden": []
  }
}
```

| Sub-field | Type | Required | Meaning |
|-----------|------|----------|---------|
| `scope` | `list[string]` | recommended | Tools this agent is allowed to call |
| `mandatory` | `list[string]` | optional | Tools that MUST be in `scope` (validated at pack load) |
| `forbidden` | `list[string]` | optional | Tools that MUST NOT be in `scope` (validated at pack load) |

**Validation rules** (errors written to `NormalizedPack.validation_errors`):

1. `set(mandatory) ⊆ set(scope)` — otherwise: `"backend_config.tools: mandatory must be subset of scope; missing: [...]"`.
2. `set(forbidden) ∩ set(scope) = ∅` — otherwise: `"backend_config.tools: forbidden must not intersect scope; overlap: [...]"`.

These two invariants encode the Corti 3-agent patterns:
- **Code Validation:** `mandatory = [verify, guidelines]`, `forbidden = []` → forces both verify and guidelines into scope.
- **Compliance Guardrail:** `mandatory = []`, `forbidden = [search]` → keeps search out of scope.
- **Note Completeness:** no `tools` sub-field (0 tools).

### 4.2 `pure_llm` provider config

```json
"backend_config": {
  "llm": {
    "model": "deepseek-v4-flash",
    "temperature": 0.0,
    "max_tokens": 4096,
    "timeout_seconds": 60
  }
}
```

Phase 4-B will wire `LLMGateway` to read these. Phase 4-A skeleton ignores them.

### 4.3 `rule_engine` provider config

```json
"backend_config": {
  "mode": "deterministic",
  "rule_sets": ["medical_coding", "drg_dip"]
}
```

`RuleEngineProvider` reads `mode` to switch between `deterministic` (R001-R012 only) and `kb_enhanced` (also calls `retrieve_rules`). Defaults to `deterministic`.

## 5. Loader behavior

`agent_pack_loader.py::_populate_backend_provider(p: NormalizedPack)` is invoked from `_populate_v12_extensions` (so it only runs for `format_version >= "1.2"`; older packs skip it entirely).

Pseudo-code:

```python
def _populate_backend_provider(p: NormalizedPack) -> None:
    raw = p._raw  # the raw JSON dict
    # 1. Extract backend_provider (top-level OR nested)
    bp = _extract_backend_provider(raw)  # string or ""
    if not isinstance(bp, str):
        p.validation_warnings.append("backend_provider must be a string; got {type}")
        bp = ""
    p.backend_provider = bp

    # 2. Extract backend_config (top-level OR nested)
    bc = _extract_backend_config(raw)  # dict or {}
    if not isinstance(bc, dict):
        p.validation_warnings.append("backend_config must be a dict; got {type}")
        bc = {}
    p.backend_config = bc

    # 3. Validate tool_scope invariants
    tools = bc.get("tools") if isinstance(bc, dict) else None
    if isinstance(tools, dict):
        scope = tools.get("scope") or []
        mandatory = tools.get("mandatory") or []
        forbidden = tools.get("forbidden") or []
        missing = set(mandatory) - set(scope)
        if missing:
            p.validation_errors.append(
                f"backend_config.tools: mandatory must be subset of scope; missing: {sorted(missing)}"
            )
        overlap = set(forbidden) & set(scope)
        if overlap:
            p.validation_errors.append(
                f"backend_config.tools: forbidden must not intersect scope; overlap: {sorted(overlap)}"
            )
```

### 5.1 `_extract_backend_provider(pack)`

```python
def _extract_backend_provider(pack: dict) -> str:
    if not isinstance(pack, dict):
        return ""
    top = pack.get("backend_provider")
    if isinstance(top, str) and top:
        return top
    agent_node = pack.get("agent")
    if isinstance(agent_node, dict):
        nested = agent_node.get("backend_provider")
        if isinstance(nested, str) and nested:
            return nested
    return ""
```

### 5.2 `_extract_backend_config(pack)`

```python
def _extract_backend_config(pack: dict) -> dict:
    if not isinstance(pack, dict):
        return {}
    top = pack.get("backend_config")
    if isinstance(top, dict):
        return top
    agent_node = pack.get("agent")
    if isinstance(agent_node, dict):
        nested = agent_node.get("backend_config")
        if isinstance(nested, dict):
            return nested
    return {}
```

## 6. `to_summary()` exposure

`NormalizedPack.to_summary()` (used by Agent Hub card UI and `/api/v1/agent-hub/agents` endpoint) now exposes:

```python
{
    "agent_ref": "icoder/code-validation@1.0.0",
    "name": "Code Validation",
    "status": "executable",
    ...
    "backend_provider": "icoder.llm-with-tools.v1",  # NEW
    "has_backend_config": True,                       # NEW
    ...
}
```

- `backend_provider` is the resolved string (may be empty for legacy packs).
- `has_backend_config` is `bool(backend_config)` — `True` if non-empty, `False` otherwise.

This lets the Hub card render a "Backend: LLM with tools" badge for packs that declare one, and stay silent for legacy packs.

## 7. Backward compatibility

Verified by `test_agent_pack_backend_schema.py`:

| Pack | `format_version` | `backend_provider` after load | `backend_config` after load | New validation errors? |
|------|------------------|-------------------------------|-----------------------------|------------------------|
| `compliance-guardrail` | 1.2 | `""` | `{}` | None |
| `code-validation` | 1.2 | `""` | `{}` | None |
| `note-completeness` | 1.2 | `""` | `{}` | None |
| `medical_coding` | 1.2 | `""` | `{}` | None |

All 4 packs load with `status=PackStatus.EXECUTABLE` and zero new validation errors. The legacy rule-engine path continues to work because `backend_provider=""` triggers `ProviderRegistry.get_or_default("")` → returns the default fallback (`icoder.rule-engine.v1`).

## 8. Migration path for existing packs

When migrating a pack to declare a backend (Phase 4-B+):

1. Add `backend_provider` to the pack JSON (top-level is preferred for new packs).
2. (Optional) Add `backend_config` with provider-specific config.
3. (For LLM-with-tools packs) Add `backend_config.tools.scope / mandatory / forbidden`.
4. Run `icoder pack validate path/to/agent_pack.json` — the loader emits validation errors if `mandatory ⊄ scope` or `forbidden ∩ scope ≠ ∅`.
5. Run `python -m pytest tests/unit/icoder_runtime/test_agent_pack_loader.py` — the 48-test regression suite catches schema regressions.

## 9. What this schema does NOT do

- **Does not** mandate a `backend_provider` for every pack. Legacy packs without it continue to work.
- **Does not** validate `provider_id` against the registry at pack-load time. Resolution is deferred to run time (so a pack can be installed before its provider is registered, e.g. for testing).
- **Does not** encode provider-specific config schemas (e.g. `backend_config.llm.model`). Each provider documents its own sub-schema; the loader only validates the `tools` sub-field (because the Corti invariants are provider-agnostic).
- **Does not** change `format_version` to 1.3. The extension is fully backward compatible, so it stays at 1.2.
