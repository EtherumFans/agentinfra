# Phase 1.3 Cycle 12.1 — Transcripts (STT) Get-Status align Corti §13.3

## Context

Phase 1.3 cycle 12 (`7504164`) shipped `DELETE /api/v2/tools/interactions/{id}/recordings/{recordingId}` (delete-recording, 204 No Content), closing the recordings family (4 of 4 endpoints). Cycle 12.1 closes the **transcript processing status endpoint** — `GET /api/v2/tools/interactions/{id}/transcripts/{transcriptId}/status`.

Notable spec semantics:
- **Lightweight status-only envelope**: `{status: enum}` — designed for polling async transcription jobs (cycle-8's create-transcript with `async: true`).
- **Reuses cycle-7's status sentinels** (`processing-{uuid}` / `failed-{uuid}` / default=completed).
- **NEW 404 sentinel**: `missing-{uuid}` returns 404 `transcript_not_found` (mirrors cycles 11/12's missing-recording 404).
- **Walker-supported** (cycle-6/7 fix carries forward).

## Spec source

`docs/corti-reverse-engineered/stt-get-transcript-status.md` (5,477 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/transcripts/get-transcript-status.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_12_1_stt_get_transcript_status/corti-stt-get-transcript-status.md`.

## Endpoint surface

```
GET /api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}/status
Authorization: Bearer <jwt or oauth>

→ 200 OK   TranscriptsStatusResponse
             { status: "completed" | "processing" | "failed" }
→ 404      transcript_not_found (RFC9457 ErrorResponse)
→ 503      service_unavailable (hospital-pilot gate)
```

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | Added `TranscriptsStatusLiteral` (alias) + `TranscriptsStatusResponse` |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | Added `get_v2_tools_interaction_transcript_status` GET endpoint |
| `backend/tests/test_api/test_v2_stt_get_transcript_status_consistency.py` | NEW | 7 回环一致性测试 |
| `docs/PHASE_1_3_CYCLE12_1_STT_GET_TRANSCRIPT_STATUS.md` | NEW | this file |
| `docs/phase_cycles/cycle_12_1_stt_get_transcript_status/corti-stt-get-transcript-status.md` | NEW | archive |

## Stub data

Sentinel pattern (reuses cycle-7 sentinels + adds new missing- sentinel):
- `processing-{uuid}` → status="processing"
- `failed-{uuid}` → status="failed"
- `missing-{uuid}` → 404 `transcript_not_found` (NEW for cycle 12.1)
- default / non-sentinel → status="completed"

## Hospital-pilot gate

Same 503 gate as cycles 1-12.

## 回环一致性测试 pattern

Reuses cycle-6/7 walker (with `$ref + parent-level metadata` fix) unchanged. Cycle 12.1 response envelope is trivial (`{status: enum}`) — no walker changes needed.

7 tests cover:

```
test_stt_get_status_spec_is_real_and_cached                  PASSED
test_stt_get_status_enum_matches_spec                        PASSED
test_v2_stt_get_status_default_returns_completed             PASSED
test_v2_stt_get_status_processing_sentinel                   PASSED
test_v2_stt_get_status_failed_sentinel                       PASSED
test_v2_stt_get_status_missing_sentinel_returns_404          PASSED
test_v2_stt_get_status_reference_round_trip                  PASSED
7 passed in 1.12s
```

Full `tests/test_api` regression: **177/177 PASS** in 3:26 (was 170 pre-cycle-12.1, +7 for this cycle). tsc clean.

## Design decisions

1. **Reuse `TranscriptsStatusLiteral` alias.** Defined as `Literal["completed", "processing", "failed"]` for cleaner reuse between cycle-7's `TranscriptsResponse.status` and cycle-12.1's `TranscriptsStatusResponse.status`. (Actually kept separate Literal in cycle-7 to avoid Pydantic schema conflicts; cycle-12.1 has its own Literal that happens to be identical.)
2. **`missing-{uuid}` sentinel = 404.** Mirrors cycles 11/12's missing-recording 404. Different from cycle-7's `processing-`/`failed-` sentinels which are status-state probes, not missing probes.
3. **No walker changes.** Trivial envelope (`{status: enum}`) — walker already handles enum + required field.

## Out of scope (explicit, future cycles)

- ❌ Polling recommendations (interval, max attempts) — caller-decided
- ❌ Async dispatch machinery — separate Phase 1.3 task
- ❌ `DELETE /interactions/{id}/transcripts/{transcriptId}` — Cycle 12.2 (last STT endpoint)
- ❌ Frontend transcript status polling widget — out of scope: Phase 1.3 = backend wire parity only

## Risk register

| Risk | Mitigation |
|---|---|
| Stub always returns `completed`/`processing`/`failed` deterministically | No real async backend; this is a stub for wire contract validation |
| `missing-{uuid}` doesn't match any real transcript ID format | Sentinel pattern documented in test file |

## STT family progress (cumulative)

| Family | Cycle | Endpoint | Method | Status |
|---|---|---|---|---|
| Transcripts | 6 | `/interactions/{id}/transcripts/` | GET (LIST) | ✅ |
| Transcripts | 7 | `/interactions/{id}/transcripts/{transcriptId}` | GET (single) | ✅ |
| Transcripts | 8 | `/interactions/{id}/transcripts/` | POST (create) | ✅ |
| Recordings | 9 | `/interactions/{id}/recordings/` | GET (LIST) | ✅ |
| Recordings | 10 | `/interactions/{id}/recordings/` | POST (upload) | ✅ |
| Recordings | 11 | `/interactions/{id}/recordings/{recordingId}` | GET (single) | ✅ |
| Recordings | 12 | `/interactions/{id}/recordings/{recordingId}` | DELETE | ✅ |
| Transcripts | 12.1 | `/interactions/{id}/transcripts/{transcriptId}/status` | GET | ✅ |
| Transcripts | 12.2 | `/interactions/{id}/transcripts/{transcriptId}` | DELETE | 🔜 next |

**STT family progress:** 8/9 endpoints complete (89%). Final endpoint remaining: **delete-transcript**.

## Auto-advance: Cycle 12.2 = delete-transcript (REST DELETE, last STT endpoint)

Per the parity queue. Cycle 12.2 will close `DELETE /interactions/{id}/transcripts/{transcriptId}` — the **last endpoint** of the **entire STT family** (9 of 9 closed).

Will mirror cycle-12 (delete-recording) pattern: 204 No Content on success, 404 sentinel for missing transcriptId, no body, no JSON envelope. Will include a **family-completeness test** verifying all 5 transcript endpoints coexist.