# A1D.4 — Cloud Resilience (KMS Rotation + LLM Fallback Provider)

**Subgate**: A1D.4 (closes Engineering-class blockers A1C-B-007 + A1C-B-008)
**Charter**: A1D_CHARTER.md v1.1 §A1D.4
**Predecessor state**: A1C.9 PARTIAL (9 Engineering-class blockers open)
**Verdict**: PASS_A1D_4_KMS_ROTATION_AND_LLM_FALLBACK_PROVIDER_FILED
**Test results**: 20/20 A1D.4 net-new tests PASS (10 KMS + 10 LLM fallback)
**Broader regression**: 764/765 service tests PASS (1 pre-existing MCP unicode failure — unrelated)

---

## §1 Scope

Two Engineering-class blockers from A1C.9 carry over:

| Blocker | Title | Severity |
|---------|-------|----------|
| **A1C-B-007** | Fallback LLM provider not implemented (DeepSeek sole provider; Azure-OpenAI / Qwen / Moonshot fallback DESIGN only) | P2 |
| **A1C-B-008** | KMS key rotation + cache invalidation not implemented (CredentialVault cache holds decrypted secrets indefinitely) | P2 |

Both blockers share a common shape: **the runtime lacks a resilience mechanism the cloud operator must be able to trigger without a redeploy**. A1D.4 ships the local / dev / CI infrastructure for both. Real cloud wiring (KMS hook + real fallback API keys) is deferred to Pilot env per Charter §五 environmental hard blockers.

---

## §2 A1C-B-008 — KMS Rotation

### 2.1 Design

The CredentialVault caches decrypted secrets in process memory after the first `resolve()`. When the cloud KMS rotates a key (operator-driven, scheduled, or compromise-response), the cached value is stale but the cache returns it indefinitely. A1D.4 introduces a monotonic version token the cache consults on every lookup:

```
                 ┌─────────────────────────┐
                 │   KMSVersionToken       │
                 │   (monotonic counter)   │
                 └────────┬────────────────┘
                          │ current / bump() / is_stale()
                          ▼
                 ┌─────────────────────────┐
                 │   CredentialVault       │
                 │   _cache: {svc: secret} │
                 │   _cache_stamps:        │
                 │     {svc: token_value}  │
                 └────────┬────────────────┘
                          │ on resolve(svc):
                          │   if token.is_stale(stamp):
                          │     re-read from env
                          │     restamp with token.current
                          ▼
                 ┌─────────────────────────┐
                 │   Cloud KMS Rotation    │
                 │   Hook (Pilot env)      │
                 │   calls token.bump()    │
                 │   post-rotation         │
                 └─────────────────────────┘
```

### 2.2 Implementation

**NEW file `backend/icoder_runtime/core/kms_version_token.py`** (62 LOC):
- `KMSVersionToken` class with thread-safe `bump()` / `current` / `is_stale(stamp)`
- Initial value 1; never decreases
- `bump()` is the only mutator; atomically increments and returns the new value

**MODIFIED `backend/app/services/credential_vault.py`**:
- `__init__` accepts optional `kms_version_token=None`
- `_cache_stamps: dict[str, int]` paralleling `_cache`
- `resolve(service)` checks `is_stale(stamp)` before cache hit; on stale, re-reads from env
- `invalidate(service=None)` — operator-initiated single-service flush (no-op for unknown service)
- `invalidate_all()` — alias for `invalidate()` (flush entire cache)

### 2.3 Operator runbook (Pilot env wiring)

```bash
# Step 1 — rotate the KMS key in the cloud console (AWS KMS / GCP KMS / Azure Key Vault)
# Step 2 — on each app instance, trigger the bump:
curl -X POST http://localhost:8000/admin/kms/rotate \
  -H "Authorization: Bearer $ADMIN_JWT"
# Server-side handler (Pilot deliverable):
#   kms_version_token.bump()
#   logger.info("KMS token advanced to %d", kms_version_token.current)
# Step 3 — verify:
curl http://localhost:8000/admin/kms/version
# {"current": 2, "previous": 1, "stamped_entries": 4}
# Step 4 — next vault.resolve("llm") on each instance re-reads from env/secrets manager
```

For **compromise-response rotation** (zero-downtime):
1. Operator pre-populates the new key under a NEW env var (e.g. `ICODER_CREDENTIAL_LLM_V2`)
2. Atomic swap: `ICODER_CREDENTIAL_LLM=$ICODER_CREDENTIAL_LLM_V2`
3. Trigger `kms_version_token.bump()` — every cache entry is now stale
4. Next `resolve()` re-reads from env (no race — bump() is atomic under the lock)

### 2.4 Tests

`backend/tests/test_api/test_a1d_4_kms_rotation.py` — 10 tests, all PASS:

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_kms_version_token_initial_value` | Token starts at 1 |
| 2 | `test_kms_version_token_bump_increments` | bump() returns new value, increments monotonically |
| 3 | `test_kms_version_token_is_stale_detects_old_entries` | is_stale() returns True for old stamps |
| 4 | `test_credential_vault_invalidate_flushes_single_service` | Single-service flush works |
| 5 | `test_credential_vault_invalidate_no_arg_flushes_all` | All-cache flush works |
| 6 | `test_credential_vault_invalidate_all_alias` | invalidate_all() == invalidate() |
| 7 | `test_credential_vault_invalidate_unknown_service_is_noop` | Unknown service flush is silent |
| 8 | `test_credential_vault_attaches_to_kms_version_token` | Vault uses the token when attached |
| 9 | `test_kms_token_bump_invalidates_stale_cache_entries` | bump() → next resolve() re-reads |
| 10 | `test_kms_token_bump_only_invalidates_stale_entries` | Only stale entries flushed; fresh entries survive |

---

## §3 A1C-B-007 — LLM Fallback Provider

### 3.1 Design

DeepSeek is the sole LLM provider. On unhealthy DeepSeek (circuit open, 429, network error, no API key), `DeepSeekProvider` returns a `degraded=True` mock response — and the caller has no automatic failover. Charter §4 PDF asks for ≥1 fallback provider so the runtime keeps serving. A1D.4 ships:

```
  caller
    │
    ▼
  LLMGateway.generate(messages)
    │
    ├─► primary.generate()
    │       │
    │       ▼
    │   degraded=True?  ──── NO ───►  return primary response
    │       │
    │      YES
    │       ▼
    │   walk fallback_chain in order:
    │       │
    │       ▼
    │   fb.generate().degraded?  ── NO ──► return fb response + provenance
    │       │                                 (fallback_from, fallback_reason, failover_trail)
    │      YES
    │       ▼
    │   next fallback ──► ... ──► all degraded? return last + full trail
    │
    ▼
  audit event records fallback_from / fallback_reason / failover_trail
```

### 3.2 Implementation

**NEW file `backend/icoder_runtime/core/fallback_provider.py`** (167 LOC):
- `make_openai_compatible_fallback(api_key, base_url, model, ...)` — generic factory
- `make_azure_openai_fallback(api_key, endpoint, deployment, api_version)` — Azure-specific (deployment-scoped URL + `api-key` header)
- `make_qwen_fallback(api_key, model, ...)` — Alibaba DashScope (OpenAI-compatible mode)
- `make_moonshot_fallback(api_key, model, ...)` — Moonshot AI Kimi

All four factories return a configured `OpenAICompatibleProvider` instance — provider-agnostic by design.

**MODIFIED `backend/icoder_runtime/core/llm_gateway.py`**:

1. `OpenAICompatibleProvider.__init__` accepts keyword-only `_name_override: str = ""` (so multiple fallbacks of the same class can coexist) and `auth_header: str = "Authorization"` (Azure uses `api-key`).
2. `OpenAICompatibleProvider.generate()` gains graceful degradation matching `DeepSeekProvider`: returns `_mock_fallback_response(reason)` on every error path (no API key, httpx.HTTPStatusError, httpx.HTTPError). Response now includes `"provider": self.name`.
3. `OpenAICompatibleProvider.health_check()` reports `status: "missing"` when no API key — so Pilot env health endpoint will flag unwired fallbacks.
4. `MockLLMProvider.__init__(*, name="")` accepts optional instance-level name override (needed for tests that register multiple mocks and tell them apart in the failover trail).
5. `LLMGateway.__init__` adds `self.fallback_chain: list[BaseLLMProvider] = []`.
6. `LLMGateway.register_fallback(provider)` appends and returns self (chainable).
7. `LLMGateway.generate()` auto-failover logic — when primary response has `degraded=True`, walks `fallback_chain` in order, stamps provenance (`fallback_from`, `fallback_reason`, `failover_trail`).

### 3.3 Failover provenance shape

When failover occurs, the returned dict gains three audit-friendly fields:

```python
{
    "content": "...",
    "provider": "qwen_fallback",          # who actually served
    "fallback_from": "deepseek",          # original degraded primary
    "fallback_reason": "circuit_open",    # primary's degraded_reason
    "failover_trail": [                   # every provider tried
        {"provider": "deepseek", "reason": "circuit_open"},
        {"provider": "azure_openai_fallback", "reason": "provider_network_error"},
        # qwen_fallback succeeded → no entry here
    ],
    "usage": {...},
    "degraded": False,
}
```

When ALL providers degraded:

```python
{
    "content": "<last mock response>",
    "provider": "mock",
    "degraded": True,
    "degraded_reason": "provider_network_error",
    "fallback_from": "deepseek",
    "fallback_reason": "no_api_key",
    "failover_trail": [
        {"provider": "deepseek", "reason": "no_api_key"},
        {"provider": "azure_openai_fallback", "reason": "circuit_open"},
        {"provider": "qwen_fallback", "reason": "provider_network_error"},
    ],
}
```

The trail is audit-event-ready — operators can post-mortem which fallbacks fired and why without scraping logs.

### 3.4 Pilot env wiring (example)

```python
# Production gateway construction (Pilot env)
from icoder_runtime.core.llm_gateway import LLMGateway, DeepSeekProvider
from icoder_runtime.core.fallback_provider import (
    make_azure_openai_fallback,
    make_qwen_fallback,
    make_moonshot_fallback,
)

gw = LLMGateway()
gw.register(DeepSeekProvider(api_key=vault.resolve("llm")), default=True)
gw.register_fallback(make_azure_openai_fallback(
    api_key=vault.resolve("azure_openai"),
    endpoint="https://icoder-prod.openai.azure.com",
    deployment="gpt-4o-cn",
))
gw.register_fallback(make_qwen_fallback(
    api_key=vault.resolve("qwen"),
    model="qwen-max",
))
gw.register_fallback(make_moonshot_fallback(
    api_key=vault.resolve("moonshot"),
    model="moonshot-v1-32k",
))
```

### 3.5 Tests

`backend/tests/test_api/test_a1d_4_llm_fallback.py` — 10 tests, all PASS:

| # | Test | Asserts |
|---|------|---------|
| 1 | `test_llm_gateway_register_fallback_returns_self` | register_fallback() chainable |
| 2 | `test_llm_gateway_register_fallback_accepts_multiple_providers` | Ordered chain, multiple providers |
| 3 | `test_gateway_generate_falls_back_when_primary_degraded` | Primary degraded → fallback called, fallback_from + fallback_reason stamped |
| 4 | `test_gateway_generate_skips_fallback_when_primary_healthy` | Primary healthy → fallback NOT called |
| 5 | `test_gateway_generate_falls_through_chain_to_second_fallback` | 1st fallback also degraded → 2nd tried |
| 6 | `test_gateway_generate_all_degraded_returns_last_degraded_with_provenance` | All degraded → last response + full failover_trail |
| 7 | `test_fallback_provider_module_exports_factory_functions` | All 4 factories exported |
| 8 | `test_make_openai_compatible_fallback_returns_provider` | Generic factory returns BaseLLMProvider with name |
| 9 | `test_make_azure_openai_fallback_returns_provider` | Azure factory returns BaseLLMProvider with name |
| 10 | `test_make_qwen_fallback_returns_provider` | Qwen factory returns BaseLLMProvider with name |

---

## §4 Explicit file list (this subgate)

```
NEW    backend/icoder_runtime/core/kms_version_token.py            (62 LOC)
NEW    backend/icoder_runtime/core/fallback_provider.py            (167 LOC)
NEW    backend/tests/test_api/test_a1d_4_kms_rotation.py           (10 tests)
NEW    backend/tests/test_api/test_a1d_4_llm_fallback.py           (10 tests)
MOD    backend/app/services/credential_vault.py                    (+44 LOC: token + invalidate)
MOD    backend/icoder_runtime/core/llm_gateway.py                  (+80 LOC: failover + provider upgrade)
NEW    reports/phase-a1d/A1D.4/CLOUD_RESILIENCE_REPORT.md          (this file)
NEW    reports/phase-a1d/A1D.4/FALLBACK_FAILOVER_TEST_RESULTS.json (verification artifact)
MOD    reports/phase-a1d/A1D.0/A1D_OPEN_BLOCKERS.csv               (B-007 + B-008 → CLOSED)
```

Total: 5 new + 3 modified = 8 files. No `git add -A`.

---

## §5 Charter governance — 5-tuple NOT mutated

| State | Value (carried from A1D.3) |
|-------|----------------------------|
| `A1C.9_VERDICT` | PARTIAL_A1C_PILOT_ENTRY_BLOCKERS_REMAIN |
| `CORTI_PARITY` | NOT_DEMONSTRATED (per A1A Gate 4R-I) |
| `PRODUCTION_READINESS` | NOT_VERIFIED |
| `GATE4_ACCEPTANCE` | REOPENED (per A1A Gate 4R-I) |
| `GATE4_9_FINAL_PASS` | SUPERSEDED (per A1A Gate 4R-I) |

The 5-tuple is informational state — A1D is a remediation phase, not a re-gate. Verdict for A1D.4 is `PASS_A1D_4_KMS_ROTATION_AND_LLM_FALLBACK_PROVIDER_FILED` (the only allowed verdict token per Charter §22).

## §6 Charter §22 — forbidden verdicts honoured

| Forbidden | Status |
|-----------|--------|
| PRODUCTION_READY | NOT emitted |
| CORTI_PARITY_VERIFIED | NOT emitted |
| CORTI_PARITY_DEMONSTRATED | NOT emitted |
| PILOT_READY | NOT emitted |
| COMMERCIAL_READY | NOT emitted |
| GATE4_FINAL_PASS | NOT emitted |
| GATE4_VERIFIED | NOT emitted |

## §7 Charter §23 — forbidden git ops honoured

| Forbidden | Status |
|-----------|--------|
| `git push` | NOT performed |
| `git push --force` | NOT performed |
| `git push --force-with-lease` | NOT performed |
| `git reset --hard` | NOT performed |
| `git checkout --` | NOT performed |
| `git restore .` | NOT performed |
| `git branch -D` | NOT performed |
| `git tag -d` (on tag in origin) | NOT performed |
| `git commit --amend` to history-rewrite | NOT performed |
| `git rebase -i` | NOT performed |
| `git merge --no-ff` to a protected branch | NOT performed |
| `git push --tags` to a protected ref | NOT performed |

All work is on `phase-a1a/emergency-containment` branch (local-only). Master untouched.

## §8 9 Engineering-class blockers — running tally

| Blocker | Severity | Status | Subgate |
|---------|----------|--------|---------|
| A1C-B-002 | P2 | **OPEN** | A1D.5 (next) |
| A1C-B-003 | P2 | CLOSED | A1D.1 |
| A1C-B-007 | P2 | **CLOSED** (this subgate) | A1D.4 |
| A1C-B-008 | P2 | **CLOSED** (this subgate) | A1D.4 |
| A1C-B-010 | P2 | CLOSED | A1D.3 |
| A1C-B-011 | P2 | CLOSED | A1D.3 |
| A1C-B-012 | P2 | CLOSED | A1D.2 |
| A1C-B-018 | P2 | CLOSED | A1D.2 |
| A1C-B-020 | P1 | CLOSED | A1D.3 |

**8/9 closed. 1 remaining (A1C-B-002 — 88 historical baseline failures) → A1D.5.**

## §9 Next subgate

**A1D.5** — Triage and remediate the 88 historical baseline failures (A1C-B-002). Per A1C.9 audit, these are spread across 4 suites:
- Spec/STT debt (subset of `test_services/test_mcp.py` + `test_services/test_stt_*.py`)
- OAuth/health_check debt (`test_api/test_oauth_*.py`)
- 30-pack official agents debt (`test_unit/icoder_runtime/test_agent_pack_loader.py` + `test_registry_status.py` — confirmed 11/11 in this subgate's regression sweep)
- Misc. (round-trip migration assertions, etc.)

A1D.5 will batch these into 4 per-suite fix batches and root-cause each before applying fixes.

---

**Verdict**: `PASS_A1D_4_KMS_ROTATION_AND_LLM_FALLBACK_PROVIDER_FILED`
**Next**: A1D.5 (88 baseline failures triage)
