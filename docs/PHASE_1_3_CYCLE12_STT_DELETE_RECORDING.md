# Phase 1.3 Cycle 12 — Recordings (STT) Delete align Corti §13.3

## Context

Phase 1.3 cycle 11 (`8a37918`) shipped `GET /api/v2/tools/interactions/{id}/recordings/{recordingId}` (get-recording, raw binary). Cycle 12 closes the **last endpoint of the recordings family** — `DELETE /api/v2/tools/interactions/{id}/recordings/{recordingId}` (delete-recording).

After cycle 12, the **recordings family is complete** (4 of 4 endpoints):
- Cycle 9: `GET /recordings/` (list)
- Cycle 10: `POST /recordings/` (upload)
- Cycle 11: `GET /recordings/{recordingId}` (get)
- **Cycle 12: `DELETE /recordings/{recordingId}`** ← this cycle

Notable spec semantics:
- **204 No Content** on success — empty body (no JSON envelope).
- **404** for missing recordingId (mirrors cycle-11's `missing-{uuid}` sentinel).
- **No body / no schema** — simplest cycle yet.

## Spec source

`docs/corti-reverse-engineered/stt-delete-recording.md` (4,853 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/recordings/delete-recording.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_12_stt_delete_recording/corti-stt-delete-recording.md`.

## Endpoint surface

```
DELETE /api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}
Authorization: Bearer <jwt or oauth>

→ 204 No Content   (no body)
→ 403, 404, 500, 504   RFC9457 ErrorResponse
→ 503            service_unavailable (hospital-pilot gate)
```

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/api/v2_tools_stt.py` | MODIFIED | Added `delete_v2_tools_interaction_recording` DELETE endpoint (204 No Content + 404 sentinel + hospital-pilot gate) |
| `backend/tests/test_api/test_v2_stt_delete_recording_consistency.py` | NEW | 5 回环一致性测试 |
| `docs/PHASE_1_3_CYCLE12_STT_DELETE_RECORDING.md` | NEW | this file |
| `docs/phase_cycles/cycle_12_stt_delete_recording/corti-stt-delete-recording.md` | NEW | archive |

## Stub data

Stub does NOT actually delete anything (no DB). Sentinel pattern:
- `missing-{uuid}` → 404 `recording_not_found` (mirrors cycle-11)
- Default → 204 No Content

## Hospital-pilot gate

Same 503 gate as cycles 1-11. No additional gating for cycle 12.

## 回环一致性测试 pattern

**Walker not used** — DELETE returns no body. Tests focus on:
- Spec sanity (correct operation + 204 + 404)
- 204 No Content body assertion (empty)
- 404 sentinel for missing recordingId
- **Family-completeness check** (cycle 12 closes the recordings family — verify all 4 endpoints work)

5 tests cover:

```
test_stt_delete_recording_spec_is_real_and_cached                       PASSED
test_v2_stt_delete_recording_default_returns_204                        PASSED
test_v2_stt_delete_recording_missing_sentinel_returns_404               PASSED
test_v2_stt_delete_recording_missing_interaction_id_rejected            PASSED
test_v2_stt_delete_recording_completes_recordings_family                PASSED
5 passed in 1.13s
```

Full `tests/test_api` regression: **170/170 PASS** in 3:55 (was 165 pre-cycle-12, +5 for this cycle). tsc clean.

## Design decisions

1. **`Response(status_code=204)`**. FastAPI's idiom for 204 No Content (no body). Without an explicit Response, FastAPI might try to serialize `None` as `null` which would be a 200 with body.
2. **404 sentinel `missing-{uuid}`**. Mirrors cycle-11's sentinel exactly — consistent missing-recording error across the family.
3. **Family-completeness test** is new for cycle 12. Verifies all 4 recording endpoints (list / upload / get / delete) coexist and respond with their canonical codes. Defensive against future regressions where one endpoint accidentally shadows another.
4. **No walker needed.** No body to validate.

## Out of scope (explicit, future cycles)

- ❌ Real audio deletion (no DB / no blob storage)
- ❌ Soft-delete vs hard-delete semantics
- ❌ Cascade: delete-recording should NOT cascade-delete transcripts (separate concern)
- ❌ `GET /interactions/{id}/transcripts/{transcriptId}/status` — Cycle 12.1 (transcript get-status)
- ❌ `DELETE /interactions/{id}/transcripts/{transcriptId}` — Cycle 12.2 (transcript delete)
- ❌ Frontend delete button — out of scope: Phase 1.3 = backend wire parity only

## Risk register

| Risk | Mitigation |
|---|---|
| 204 No Content might serialize as `null` body | Explicit `Response(status_code=204)` ensures empty body |
| Stub doesn't actually delete anything | Documented; real audio deletion is separate Phase 1.3 task |

## Phase 1.3 progress (cumulative)

| Family | Cycle | Endpoint | Method | Status |
|---|---|---|---|---|
| Transcripts | 6 | `/interactions/{id}/transcripts/` | GET (LIST) | ✅ |
| Transcripts | 7 | `/interactions/{id}/transcripts/{transcriptId}` | GET (single) | ✅ |
| Transcripts | 8 | `/interactions/{id}/transcripts/` | POST (create) | ✅ |
| Recordings | 9 | `/interactions/{id}/recordings/` | GET (LIST) | ✅ |
| Recordings | 10 | `/interactions/{id}/recordings/` | POST (upload) | ✅ |
| Recordings | 11 | `/interactions/{id}/recordings/{recordingId}` | GET (single) | ✅ |
| Recordings | 12 | `/interactions/{id}/recordings/{recordingId}` | DELETE | ✅ |
| Transcripts | 12.1 | `/interactions/{id}/transcripts/{transcriptId}/status` | GET | 🔜 next |
| Transcripts | 12.2 | `/interactions/{id}/transcripts/{transcriptId}` | DELETE | pending |

**STT family progress:** 7/9 endpoints complete (78%). 2 transcript endpoints remain (get-status, delete).

## Auto-advance: Cycle 12.1 = get-transcript-status (REST GET)

Per the parity queue. Cycle 12.1 will close `GET /interactions/{id}/transcripts/{transcriptId}/status` — the transcript processing status endpoint. Mirrors cycle-7 get-transcript pattern but only returns `status` (not the full transcript body). Designed for polling transcript creation jobs (especially async from cycle-8).

After cycle 12.1: 8/9 STT endpoints complete.
Final cycle 12.2: delete-transcript closes the STT family.