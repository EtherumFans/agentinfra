# A1C.5 — DeepSeek Cloud Service + KMS Key Loop (SUBGATE INDEX)

**Date**: 2026-07-25
**Subgate**: A1C.5
**Charter ref**: docs/phase-a1c/A1C_CHARTER.md HG-05 (DeepSeek + KMS)
**Verdict**: `PARTIAL_A1C_5_DEEPSEEK_PRIOR_E2E_VERIFIED_KMS_ABSTRACTION_DESIGN_CLOUD_KMS_ADAPTER_DEFERRED_TO_PILOT`

## Deliverables (PDF §九 5 outputs)

| # | File | Status |
|---|------|--------|
| 1 | `KMS_INTEGRATION_REPORT.md` | AUTHORED — CredentialVault abstraction verified (6/9 "密钥不进入" PASS); KMS adapter abstraction designed |
| 2 | `SECRET_LEAK_SCAN_RESULTS.json` | AUTHORED + JSON VALIDATED — 8 scan paths, 6 PASS_NO_LEAK + 2 PASS_BY_DESIGN + 1 DEFERRED (HAR) |
| 3 | `DEEPSEEK_FAILURE_MODE_MATRIX.csv` | AUTHORED — 17 failure modes × mitigation × test × pilot action |
| 4 | `DEEPSEEK_LIVE_TEST_RESULTS.json` | AUTHORED + JSON VALIDATED — 17 scenarios; 3 prior-PASS + 13 DESIGN + 1 infrastructure |
| 5 | `AI_DISABLED_MODE_REPORT.md` | AUTHORED — 6/6 PDF §九 behaviors verified |

## Existing infrastructure reused

| 组件 | 状态 |
|------|------|
| `CredentialVault` (backend/app/services/credential_vault.py) | ✓ 实现完整 — env-backed,KMS-backed via adapter 抽象 |
| `LLMGateway` (icoder_runtime) | ✓ 实现完整 — httpx + tenacity retry + AI_DISABLED guard |
| `audit_detail_redactor` (A1A Gate 4) | ✓ 实现完整 — PHI redaction before log_action |
| Phase 7 Gate 3 `IdempotencyRecord` | ✓ 已用 |
| Phase 7 Gate 7 `trace_token` | ✓ 已用 |
| Phase 7 Gate 9 SSE | ✓ 已用 |
| Phase 5 A2 billing cost cap | ✓ 已用 |
| Charter §4 `ICODER_AI_ENABLED=false` default | ✓ 已用 |
| A1A Gate 1 fail-closed `Settings._validate_fail_closed_policy` | ✓ 已用 |

## Honest PARTIAL — deferred to Pilot

- **真实 KMS provider adapter 实现** (Aliyun KMS / HashiCorp Vault / 腾讯云 KMS / 华为云 KMS) — adapter 抽象已设计,具体 provider 实现需 Pilot 选择
- **KMS key rotation** + `CredentialVault.cache` invalidation signal — DESIGN
- **KMS access audit log** — DESIGN (provider 自带 audit log)
- **DeepSeek 真实 failure mode 注入测试** (11 个 DESIGN_ONLY scenarios via toxiproxy)
- **Circuit breaker** (pybreaker) — DESIGN
- **Fallback provider** (azure-openai / qwen / moonshot) — DESIGN
- **Response truncation detection** (finish_reason=length + max_tokens check) — DESIGN
- **HAR 文件 regex 扫描** (Pilot env e2e capture) — DEFERRED

## Charter §22 forbidden verdicts honoured

- ❌ Not emitted: DEEPSEEK_CLOUD_DEPLOYED / KMS_FULLY_VERIFIED / KMS_PILOT_DEPLOYED / SECRET_LEAK_ZERO_VERIFIED (HAR deferred) / PRODUCTION_READY

## State 5-tuple update

| Key | A1C.4 value | A1C.5 value |
|-----|-------------|-------------|
| A1C_5_KMS_DELIVERABLES | NOT_AUTHORED | AUTHORED_5_OF_5 |
| A1C_5_SECRET_LEAK_AUDIT | NOT_VERIFIED | 6/8 PASS + 2/8 BY_DESIGN + 1/8 DEFERRED (HAR) |
| A1C_5_DEEPSEEK_PRIOR_E2E | NOT_REVIEWED | REVIEWED (Phase 7 Gate 12 + RV.5 30/30) |
| A1C_5_DEEPSEEK_FAILURE_MODES | NOT_AUTHORED | AUTHORED (17 modes; 6 IMPLEMENTED + 11 DESIGN) |
| A1C_5_AI_DISABLED | NOT_VERIFIED | VERIFIED (6/6 PDF behaviors) |
| A1C_5_KMS_ADAPTER | NOT_DESIGN | DESIGNED (provider impl deferred) |
