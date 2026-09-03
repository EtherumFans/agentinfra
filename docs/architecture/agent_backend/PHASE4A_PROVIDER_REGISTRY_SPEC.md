# Phase 4-A — ProviderRegistry Specification

**Document type:** API / behavior spec
**Date:** 2026-07-07
**Author:** SONG Luhua
**Scope:** `icoder_runtime/backends/registry.py` — the process-wide registry of `AgentBackendProvider` instances.

---

## 1. Purpose

`ProviderRegistry` is the single source of truth for "which backend providers exist in this process". It maps `provider_id` (e.g. `icoder.rule-engine.v1`) → provider instance. The runtime executor (`AgentRunner` / `InboundHandler`) consults the registry on every agent run to resolve which backend to invoke.

The registry is **process-wide** (one default instance per Python interpreter) and **thread-safe** (single `RLock`). Initialization is **lazy** — module import costs nothing; the 3 Phase 4-A builtin providers register on first lookup so startup time is unaffected.

## 2. Public API

### 2.1 Class: `ProviderRegistry`

```python
class ProviderRegistry:
    def __init__(self, *, auto_register_builtins: bool = True) -> None: ...
    def register(self, provider: AgentBackendProvider) -> None: ...
    def unregister(self, provider_id: str) -> AgentBackendProvider | None: ...
    def get(self, provider_id: str) -> AgentBackendProvider: ...
    def get_or_default(self, provider_id: str | None) -> AgentBackendProvider: ...
    def list(self) -> list[str]: ...
    def list_by_type(self, backend_type: BackendType | str) -> list[AgentBackendProvider]: ...
    def list_capabilities(self) -> list[ProviderCapability]: ...
    async def health(self, provider_id: str) -> ProviderHealth: ...
    async def health_all(self) -> dict[str, ProviderHealth]: ...
    def resolve_from_agent_pack(self, agent_pack: dict[str, Any]) -> AgentBackendProvider: ...
    def get_backend_config(self, agent_pack: dict[str, Any]) -> dict[str, Any]: ...
    def _ensure_builtins(self) -> None: ...  # test hook — idempotent
```

### 2.2 Module-level functions

```python
def get_default_registry() -> ProviderRegistry: ...
def reset_default_registry() -> None: ...  # test hook
```

### 2.3 Constants

```python
DEFAULT_FALLBACK_PROVIDER_ID = "icoder.rule-engine.v1"
```

### 2.4 Exception

```python
class ProviderNotRegisteredError(RuntimeError):
    provider_id: str
    registered: list[str]
    # Message: "backend_provider {id!r} not registered. Registered: [...]. Did you forget..."
```

## 3. Behavior contract

### 3.1 `__init__(*, auto_register_builtins=True)`

- Creates an empty `dict[str, AgentBackendProvider]` and an `RLock`.
- `auto_register_builtins=True` (default): lazy registration of 3 builtins on first lookup. Production code uses this default.
- `auto_register_builtins=False`: registry stays empty until caller explicitly `register()`s. Used by unit tests for isolation.
- Cost: O(1), no I/O, no imports. Module import doesn't trigger this.

### 3.2 `register(provider)`

- Reads `provider.provider_id`. Empty string → `ValueError("provider has no provider_id")`.
- Acquires lock. Duplicate `provider_id` → `ValueError("already registered; call unregister first")`.
- Stores `provider_id → provider`.
- Logs at DEBUG level.
- **Does NOT trigger `_ensure_builtins()`** — registering a custom provider doesn't pull in the builtins.

### 3.3 `unregister(provider_id)`

- Acquires lock. Pops the entry. Returns the removed provider, or `None` if absent.
- No exception on unknown ID.

### 3.4 `get(provider_id)`

- Calls `_ensure_builtins()` first (idempotent).
- Acquires lock, looks up `provider_id`.
- Hit → returns the provider.
- Miss → raises `ProviderNotRegisteredError` with `provider_id` and the sorted list of registered IDs in the message. Actionable — tells the user what they typo'd.

### 3.5 `get_or_default(provider_id)`

- If `provider_id` is `None` or empty string: calls `_ensure_builtins()`, returns `self._providers[DEFAULT_FALLBACK_PROVIDER_ID]`.
- Otherwise: delegates to `get(provider_id)`.
- Used by `resolve_from_agent_pack` for legacy v1.0 packs that don't declare `backend_provider`.

### 3.6 `list()`

- Calls `_ensure_builtins()`. Returns sorted list of registered `provider_id` strings.
- Cheap — no instantiation, no health calls.

### 3.7 `list_by_type(backend_type)`

- Calls `_ensure_builtins()`. Returns list of providers whose `backend_type` attribute matches the argument.
- `backend_type` can be a `BackendType` enum value or a plain string.

### 3.8 `list_capabilities()`

- Calls `_ensure_builtins()`. Returns `ProviderCapability` for each registered provider.
- Defensive: if a provider's `capabilities()` raises, logs a warning and skips — never breaks listing.
- Used by `GET /api/v1/agent-runtime/providers/health` (Phase 4-B) and by `icoder pack validate` to check `tool_scope` validity.

### 3.9 `health(provider_id) -> ProviderHealth`

- Looks up the provider (via `get()`, which triggers `_ensure_builtins()`).
- `ProviderNotRegisteredError` → returns `ProviderHealth(state="down", details={"error": "not registered: ..."})`.
- Calls `provider.health()`:
  - Returns `ProviderHealth` if the provider returns one.
  - Wraps non-`ProviderHealth` returns into `ProviderHealth(state="degraded", details={"raw": ...})`.
  - `NotImplementedError` → `ProviderHealth(state="ok", details={"note": "health() not implemented"})`.
  - Any other exception → `ProviderHealth(state="down", details={"error": f"{type(e).__name__}: {str(e)[:200]}"})`.
- **Never raises.** Used by `health_all()` and the upcoming providers/health endpoint.

### 3.10 `health_all() -> dict[str, ProviderHealth]`

- Calls `_ensure_builtins()`. Iterates all registered IDs. Calls `health(id)` for each.
- Returns a dict `{provider_id: ProviderHealth}`.
- **Never raises** — `health()` already wraps all exceptions.

### 3.11 `resolve_from_agent_pack(agent_pack)`

- Extracts `backend_provider` from the pack via `_extract_backend_provider()`:
  - Top-level `pack["backend_provider"]` if it's a non-empty string.
  - Else `pack["agent"]["backend_provider"]` if `pack["agent"]` is a dict and the nested field is a non-empty string.
  - Else empty string.
- Returns `get_or_default(extracted_id)`:
  - Empty extracted → default fallback provider (`icoder.rule-engine.v1`).
  - Non-empty extracted → that provider (raises `ProviderNotRegisteredError` if missing).
- **This is the main entry point used by `AgentRunner` / `InboundHandler`.**

### 3.12 `get_backend_config(agent_pack)`

- Extracts `backend_config` from the pack via `_extract_backend_config()`:
  - Top-level `pack["backend_config"]` if it's a dict.
  - Else `pack["agent"]["backend_config"]` if `pack["agent"]` is a dict and the nested field is a dict.
  - Else `{}`.
- No provider lookup. Pure data extraction.

### 3.13 `_ensure_builtins()` (idempotent, internal)

- If `_initialized_builtins` is `True`, returns immediately.
- If `auto_register_builtins=False`, sets `_initialized_builtins=True` and returns (no registration).
- Otherwise: acquires lock, double-checks `_initialized_builtins`, sets it `True`, calls `_register_builtin_providers(self)`.
- Defensive: if `_register_builtin_providers` raises, logs at ERROR level and swallows — never breaks the registry.

### 3.14 `_register_builtin_providers(registry)` (module-level, internal)

Imports (locally, inside the function — so module import doesn't pay):
- `RuleEngineProvider` — always registers (no external deps).
- `PureLLMProvider` — registers if constructor succeeds (skeleton — should always succeed).
- `LLMWithToolsProvider` — registers if constructor succeeds (skeleton — should always succeed).

For each candidate, calls `registry.register(provider)`. `ValueError` (duplicate) is caught and logged at DEBUG — fine for the default registry when a test has already manually registered a builtin.

## 4. Module-level default registry

```python
_DEFAULT_REGISTRY: ProviderRegistry | None = None
_DEFAULT_REGISTRY_LOCK = threading.Lock()

def get_default_registry() -> ProviderRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        with _DEFAULT_REGISTRY_LOCK:
            if _DEFAULT_REGISTRY is None:
                _DEFAULT_REGISTRY = ProviderRegistry()
    return _DEFAULT_REGISTRY

def reset_default_registry() -> None:
    global _DEFAULT_REGISTRY
    with _DEFAULT_REGISTRY_LOCK:
        _DEFAULT_REGISTRY = None
```

- `get_default_registry()` double-checked-locking singleton. Tests can `reset_default_registry()` to start fresh.
- Production code calls `get_default_registry()` — never instantiates `ProviderRegistry()` directly.

## 5. Usage patterns

### 5.1 Production: agent run

```python
from icoder_runtime.backends.registry import get_default_registry

def run_agent(agent_pack: dict, req: BackendRequest, ctx: AgentRunContext):
    registry = get_default_registry()
    provider = registry.resolve_from_agent_pack(agent_pack)
    config = registry.get_backend_config(agent_pack)
    resp = await provider.invoke(req, ctx)
    ...
```

### 5.2 Production: Hub UI lists providers

```python
caps = get_default_registry().list_capabilities()
# Render caps as cards in Agent Hub
```

### 5.3 Production: health endpoint (Phase 4-B)

```python
@router.get("/api/v1/agent-runtime/providers/health")
async def providers_health():
    return await get_default_registry().health_all()
```

### 5.4 Test: isolated registry

```python
def test_something():
    r = ProviderRegistry(auto_register_builtins=False)
    r.register(_StubProvider("icoder.test.v1"))
    # r.list() returns ["icoder.test.v1"] only — no builtins leaked in.
```

### 5.5 Test: lazy registration verified

```python
def test_lazy_registration_on_first_get():
    reset_default_registry()
    r = get_default_registry()
    p = r.get("icoder.rule-engine.v1")  # triggers _ensure_builtins()
    assert p.backend_type == "rule_engine"
```

## 6. Thread safety

- Single `threading.RLock` guards all mutations and lookups.
- `_ensure_builtins()` uses double-checked locking on `_initialized_builtins` (a plain bool, not a lock — the lock guards the mutation, the bool is the fast-path check).
- `health()` and `health_all()` release the lock before awaiting `provider.health()` — no lock held across async calls.
- The registry is safe for concurrent `register()` / `get()` / `list()` from multiple threads. Async calls (`health`) are safe to run concurrently.

## 7. Performance characteristics

| Operation | Cost |
|-----------|------|
| `import icoder_runtime.backends.registry` | O(1), no I/O, no provider imports |
| `ProviderRegistry()` | O(1), empty dict + RLock |
| `get_default_registry()` (warm) | O(1), dict lookup |
| `get_default_registry()` (cold) | O(1) + lock + `ProviderRegistry()` |
| `register(provider)` | O(1) + lock |
| `get(provider_id)` (warm, builtins init'd) | O(1) + lock |
| `get(provider_id)` (cold, triggers lazy init) | O(N) where N = 3 builtin imports (one-time) |
| `list()` | O(N log N) sort |
| `list_by_type(t)` | O(N) filter |
| `list_capabilities()` | O(N) + N × `provider.capabilities()` |
| `health(id)` | O(1) + `await provider.health()` |
| `health_all()` | O(N) + Σ `await provider.health()` |
| `resolve_from_agent_pack(pack)` | O(1) + `get_or_default` |

Lazy init cost (one-time): ~3-5ms for the 3 builtin imports on a warm Python interpreter. After init, all lookups are O(1).

## 8. Extensibility

### 8.1 Adding a new builtin provider (Phase 4-D)

In `_register_builtin_providers()`:
```python
from .cascade_provider import CascadeProvider  # new in Phase 4-D
try:
    candidates.append(CascadeProvider())
except Exception as e:
    logger.debug("CascadeProvider init skipped: %s", e)
```

### 8.2 Registering a custom provider (e.g. tenant-specific)

```python
class TenantXProvider:
    provider_id = "tenant-x.backend.v1"
    backend_type = "rule_engine"
    ...

get_default_registry().register(TenantXProvider())
```

The next `resolve_from_agent_pack({"backend_provider": "tenant-x.backend.v1"})` will return it.

### 8.3 Replacing a builtin

```python
r = get_default_registry()
r.unregister("icoder.rule-engine.v1")
r.register(MyCustomRuleEngineProvider())  # must use the same provider_id
```

## 9. What this spec does NOT cover

- **Provider implementation** — see `PHASE4A_PROVIDER_FOUNDATION_IMPLEMENTATION_REPORT.md` §3.
- **Agent pack schema** — see `PHASE4A_AGENT_PACK_BACKEND_SCHEMA.md`.
- **Migration plan** — see `PHASE4A_NEXT_MIGRATION_PLAN.md`.
- **MCP dispatch wiring** — see `tool_mcp_compat_layer.py` + `app/main.py` `_handle_simple`.
- **RunTrace metadata emission** — see `run_trace.py::emit_backend_metadata_event`.
