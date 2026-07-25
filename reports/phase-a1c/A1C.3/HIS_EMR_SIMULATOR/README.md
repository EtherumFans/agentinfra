# iCoDer A1C.3 — HIS/EMR Simulator

Pure-Python (no third-party deps) simulator that emits realistic HIS/EMR
requests against the iCoDer patient-context API + document ingestion API +
agent_run + result callback webhook. 16 scenarios per PDF A1C.3 §七.

## Modes

### DRY_RUN (default)
- No network calls
- Prints what would-be-sent + asserted expected outcome
- Used for schema/contract validation; runs in CI

### LIVE
- HTTP POST/GET/DELETE to `ICODER_PILOT_URL` via urllib
- Requires `ICODER_PILOT_JWT` env var for authentication
- Used in Pilot environment

## Usage

```bash
# List all 16 scenarios
python -m his_emr_simulator --list

# Run scenario 1 (smoke) in DRY mode
python -m his_emr_simulator --scenario 1

# Run all 16 scenarios in DRY mode
python -m his_emr_simulator --all

# Run all 16 scenarios in LIVE mode (requires Pilot env)
ICODER_PILOT_URL=http://localhost:8000 \
ICODER_PILOT_JWT=<pilot-test-jwt> \
python -m his_emr_simulator --all --live
```

## Scenarios (per PDF A1C.3 §七)

| # | 名称 | Expected Outcome | 关闭 RV.gap |
|---|------|------------------|------------|
| 1 | 正常病例 (smoke) | 201 created | RV.5 J8 |
| 2 | 缺字段 | 400 INVALID_REQUEST | — |
| 3 | 重复消息 | 200 cache hit (idempotency) | — |
| 4 | 乱序消息 | 404 NOT_FOUND | — |
| 5 | 延迟消息 | 201 created (after 90s wait) | — |
| 6 | 撤回文书 | 204 deleted | — |
| 7 | 文书版本更新 | 201 created (new version) | — |
| 8 | 患者合并 | 202 accepted (async) | — |
| 9 | 就诊号变更 | 200 updated | — |
| 10 | 跨机构错误 | 404 NOT_FOUND | A1A Gate 3 |
| 11 | 网络超时 | 504 UPSTREAM_TIMEOUT | — |
| 12 | 5xx upstream | 502 UPSTREAM_ERROR | — |
| 13 | 429 rate limit | 429 RATE_LIMITED | Phase 7 Gate 8 |
| 14 | 回调失败 | dead-letter queue populated | — |
| 15 | 重复回写 | 200 idempotent | — |
| 16 | consent 拒绝 | 422 BUSINESS_RULE_VIOLATION | — |

## Output

Each run emits a JSON summary:
```json
{
  "mode": "DRY",
  "base_url": "(dry-run)",
  "ran_at": "2026-07-25T...",
  "total_scenarios": 16,
  "pass": 16,
  "fail": 0,
  "partial": 0,
  "verdict": "HIS_EMR_SIMULATOR_DRY_VERIFIED",
  "scenario_outcomes": [...]
}
```

## Charter alignment

- **Charter §22 forbidden verdicts honoured**: simulator emits `HIS_EMR_SIMULATOR_DRY_VERIFIED` or `HIS_EMR_SIMULATOR_VERIFIED` (only after LIVE run). Never emits `HIS_EMR_PILOT_DEPLOYED` (Pilot 真实对接 is separate gate).
- **PDF §七 16 scenarios**: all enumerated in `scenarios.py` registry.
- **RV.5 BLOCKED_BY_NO_CONTEXT_CREATE_ENDPOINT**: closed by scenario 1 PASS (POST /api/v1/patient-context) + scenario 6 (DELETE document) + scenario 10 (cross-tenant deny).
