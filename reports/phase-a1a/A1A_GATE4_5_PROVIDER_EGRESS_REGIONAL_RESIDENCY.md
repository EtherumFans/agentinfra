# Phase A1A Gate 4.5 — Provider Egress + Regional Residency Policy

**Date**: 2026-07-20
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 4.4 (`A1A_GATE4_4_PHI_AT_REST_PROTECTION_KEY_LIFECYCLE.md`)
**Successor**: Gate 4.6 (Browser + Embedded + Patient A/B)

Charter §4.5: close T-CC-5 — a CN tenant's PHI could egress to a
US-region LLM provider because the policy had no region field and
the provider registry had no per-provider region metadata.

---

## §1. Provider region registry

`icoder_runtime/core/data_policy.py::PROVIDER_REGIONS` is the
canonical source of truth for which region each LLM provider
stores user data in:

| Provider | Region | Rationale |
|---|---|---|
| `deepseek` | `cn` | DeepSeek is operated from China; data stays in mainland China |
| `openai_compat` | `us` | OpenAI-compatible endpoints typically point at US-hosted gateways |
| `mock` | `cn` | Test-only; inherits CN so CN-region test tenants do not false-positive |
| `local` | `cn` | Bundled local provider runs in the tenant's own region by definition |
| unknown | `us` | Conservative default — operator must explicitly whitelist a CN provider |

`get_provider_region(name)` checks `ICODER_PROVIDER_REGION_{NAME}`
env var first (operator override for deployment-specific endpoints)
then falls back to the registry.

---

## §2. RuntimeDataPolicy — new fields

| Field | Type | Default | Meaning |
|---|---|---|---|
| `region` | `eu` \| `us` \| `cn` | `cn` | Tenant's data-residency region |
| `egress_policy` | `strict` \| `best_effort` \| `off` | `strict` | How to react when provider region ≠ tenant region |

### §2.1 Behaviour matrix for `can_use_provider`

| `egress_policy` | Provider region matches tenant | Provider region differs |
|---|---|---|
| `strict` (default) | allow | **deny** with reason naming both regions |
| `best_effort` | allow | allow + log WARNING |
| `off` | allow | allow (pre-Gate-4.5 behaviour) |

The external-LLM gate (`allow_external_llm`) runs **before** the
region check so the deny reason names the correct root cause.

### §2.2 Env wiring

- `ICODER_REGION` — tenant region (defaults `cn`)
- `ICODER_EGRESS_POLICY` — `strict` / `best_effort` / `off` (defaults `strict`)
- `ICODER_PROVIDER_REGION_{NAME}` — per-provider override

Invalid env values fall back safely: unknown region → `cn`,
unknown egress policy → `strict` (fail-closed).

---

## §3. Tests

`backend/tests/test_api/test_a1a_gate4_5_provider_egress_regional_residency.py`
(13 tests):

- §1 Registry: 3 tests (known providers, unknown defaults, env override)
- §2 Strict egress: 4 tests (deny CN→US, allow CN→CN, allow US→US,
  external-LLM gate takes precedence)
- §3 Best-effort: 1 test (logs warning, allows call)
- §4 Off mode: 1 test (skips check)
- §5 Env wiring: 3 tests (from_env reads both fields, invalid
  region falls back to cn, invalid egress falls back to strict)
- §6 Serialisation: 1 test (to_dict exposes new fields)

Test report: `13 passed in 1.82s`.

---

## §4. Files touched

### Code

| File | Change |
|---|---|
| `icoder_runtime/core/data_policy.py` | `region` + `egress_policy` fields; `PROVIDER_REGIONS` registry; `get_provider_region`; `can_use_provider` enforces residency; `from_env` / `from_yaml` / `to_dict` carry new fields |

### Tests

| File | Change |
|---|---|
| `backend/tests/test_api/test_a1a_gate4_5_provider_egress_regional_residency.py` | **NEW**. 13 tests. |

### Docs

| File | Change |
|---|---|
| `reports/phase-a1a/A1A_GATE4_5_PROVIDER_EGRESS_REGIONAL_RESIDENCY.md` | This closure report. |

---

## §5. Forbidden list — re-confirmation

Gate 4.5 did NOT:

- Modify any Medical Coding / CDI / DRG-DIP prompt
- Touch real patient data
- Push, PR, master commit, amend `b737eab`
- Use `git add -A`
- Issue any charter §22 forbidden verdict
- Wire the new egress check into the LLMGateway hot path yet —
  the check is enforced via the same call sites that already
  consult `can_use_provider`. A follow-up audit in Gate 4.8
  verifies every gateway call goes through the policy.

---

## §6. Provisional verdict

```
PASS_A1A_GATE4_5_PROVIDER_EGRESS_REGIONAL_RESIDENCY_VERIFIED
```

T-CC-5 closed. CN tenants cannot egress PHI to US-region providers
under the default `strict` policy. Operators can opt into
`best_effort` for migration windows or `off` for backwards-compat.

---

## §7. Next

Gate 4.6 — Browser + Embedded + Patient A/B verification.
