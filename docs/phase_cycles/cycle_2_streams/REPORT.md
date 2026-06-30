# Cycle 2 — Streams WSS parity — Archive

## Status

PASS — all hard-gate回环一致性测试 5/5 PASS; full test_api regression green.

## Captures (real, not fabricated)

| File | Source | When | Size |
|---|---|---|---|
| `corti-stream-asyncapi.json` | `https://docs.corti.ai/api-reference/stream-asyncapi.json` | 2026-06-30 23:30 UTC | 17 104 bytes |
| `corti-streams.md` | `https://docs.corti.ai/stt/streams.md` | 2026-06-30 23:30 UTC | 6 445 bytes |

Both fetched with `curl -sL --max-time 15` and the spec archived at the
iCoDer repo root `docs/corti-reverse-engineered/stream-asyncapi.json`.

## 回环一致性测试 output

```
tests/test_api/test_v2_streams_consistency.py::test_asyncapi_spec_is_real_and_cached PASSED
tests/test_api/test_v2_streams_consistency.py::test_v2_streams_consistency_transcript_shape_matches_corti_spec PASSED
tests/test_api/test_v2_streams_consistency.py::test_v2_streams_consistency_facts_shape_matches_corti_spec PASSED
tests/test_api/test_v2_streams_consistency.py::test_v2_streams_consistency_end_sequence_matches_corti_spec PASSED
tests/test_api/test_v2_streams_consistency.py::test_v2_streams_consistency_corti_reference_round_trip PASSED
5 passed in 1.92s
```

## Diff summary (iCoDer ↔ Corti)

| Layer | Before | After |
|---|---|---|
| `app/schemas/v2_tools_streams.py` | absent | 17 Pydantic models, 1:1 with AsyncAPI |
| `app/api/v2_tools_streams.py` | absent | WSS router (15 s config window, audio loop, ENDED+usage close) |
| `app/main.py` | no mount | `app.include_router(v2_tools_streams_router)` |
| `tests/test_api/test_v2_streams_consistency.py` | absent | 5 tests, schema-driven回环 validation |
| Legacy `/ws/agent/{id}`, `/ws/speech-to-text` | unchanged | unchanged (out of scope) |
| `ws-streams.jsonl` | mislabelled Intercom noise | unchanged (research artefact) |

## Decision log

- **Cadence in CI vs prod**: 30-chunk / 100-chunk when `ICODER_TEST_MODE=1`
  (default in test), 3 s / 60 s otherwise. Mirrors Corti's documented
  cadence in spirit while keeping CI wall time sane.
- **Auth**: same hospital-pilot 503/close gate as REST v2 endpoints.
- **Tenant param**: accept both `tenant-name` (Corti) and `tenant_name`
  (FastAPI default) for SDK parity.
- **No deletion of legacy WSS** this cycle: legacy endpoints pre-date this
  cycle and are addressed in Phase 1.3 (STT) + A2A migration.