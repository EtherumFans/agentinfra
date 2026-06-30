# Phase 1.3 Cycle 12.2 — Transcripts (STT) Delete align Corti §13.3

## Context

Phase 1.3 cycle 12.1 (`8805ca9`) shipped `GET /interactions/{id}/transcripts/{transcriptId}/status` (transcript processing status polling). Cycle 12.2 closes the **last endpoint of the entire STT family** — `DELETE /interactions/{id}/transcripts/{transcriptId}` (delete-transcript).

After cycle 12.2, **Phase 1.3 STT parity is COMPLETE**:
- Transcripts family: 5 of 5 endpoints closed
- Recordings family: 4 of 4 endpoints closed (closed in cycle 12)
- **Total STT family: 9 of 9 endpoints closed**

## Spec source

`docs/corti-reverse-engineered/stt-delete-transcript.md` (5,061 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/transcripts/delete-transcript.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_12_2_stt_delete_transcript/corti-stt-delete-transcript.md`.

## Endpoint surface

```
DELETE /api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}
Authorization: Bearer <jwt or oauth>

→ 204 No Content   (no body)
→ 400, 401, 403, 500, 504   RFC9457 ErrorResponse
→ 503            service_unavailable (hospital-pilot gate)
```

Note: delete-transcript spec does NOT include 404 (interesting difference from delete-recording which has 404). iCoDer stub honors this exactly.

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/api/v2_tools_stt.py` | MODIFIED | Added `delete_v2_tools_interaction_transcript` DELETE endpoint (204 No Content + hospital-pilot gate) |
| `backend/tests/test_api/test_v2_stt_delete_transcript_consistency.py` | NEW | 5 回环一致性测试 (incl. family-completeness check for ALL 9 STT endpoints) |
| `docs/PHASE_1_3_CYCLE12_2_STT_DELETE_TRANSCRIPT.md` | NEW | this file |
| `docs/phase_cycles/cycle_12_2_stt_delete_transcript/corti-stt-delete-transcript.md` | NEW | archive |

## Stub data

Stub does NOT actually delete anything (no DB). Default → 204 No Content.

## Hospital-pilot gate

Same 503 gate as cycles 1-12.1.

## 回环一致性测试 pattern

**Walker not used** — DELETE returns no body. Tests focus on:
- Spec sanity (204 + 400/401/403/500/504 — note: NO 404)
- 204 No Content body assertion (empty)
- Sentinel status sentinels (processing-/failed-) still deletable
- Empty path rejection
- **Family-completeness check** — the closing test for the entire STT family

5 tests cover:

```
test_stt_delete_transcript_spec_is_real_and_cached                  PASSED
test_v2_stt_delete_transcript_default_returns_204                   PASSED
test_v2_stt_delete_transcript_status_sentinels_still_deletable      PASSED
test_v2_stt_delete_transcript_empty_path_rejected                   PASSED
test_v2_stt_delete_transcript_completes_stt_family                 PASSED
5 passed in 1.22s
```

Full `tests/test_api` regression: **182/182 PASS** in 3:42 (was 177 pre-cycle-12.2, +5 for this cycle). tsc clean.

## Design decisions

1. **No 404 sentinel** (unlike delete-recording cycle-12). Spec only lists 400/401/403/500/504 for delete-transcript. iCoDer stub honors spec exactly — no missing- sentinel.
2. **Family-completeness test exercises ALL 9 STT endpoints**. This is the definitive close test for Phase 1.3 STT parity. If any of the 9 endpoints regress, this test catches it.
3. **`Response(status_code=204)`** — explicit empty body (no `null` serialization).
4. **No walker changes** — DELETE has no body.

## Out of scope (explicit, future phases)

- ❌ Real transcript deletion (no DB / no blob storage)
- ❌ Cascade: delete-transcript should NOT cascade-delete recordings (separate concern)
- ❌ Frontend delete button — out of scope: Phase 1.3 = backend wire parity only
- ❌ Other Corti §13 endpoints (Facts, Codes, Languages, etc.) — separate Phase

## Risk register

| Risk | Mitigation |
|---|---|
| 204 No Content might serialize as `null` body | Explicit `Response(status_code=204)` ensures empty body |
| Stub doesn't actually delete anything | Documented; real transcript deletion is separate task |

## Phase 1.3 STT parity — FINAL COMPLETION (cumulative)

| Family | Cycle | Endpoint | Method | Status code |
|---|---|---|---|---|
| Transcripts | 6 | `/interactions/{id}/transcripts/` | GET (LIST) | 200 |
| Transcripts | 7 | `/interactions/{id}/transcripts/{transcriptId}` | GET (single) | 200 |
| Transcripts | 8 | `/interactions/{id}/transcripts/` | POST (create) | 201 |
| Transcripts | 12.1 | `/interactions/{id}/transcripts/{transcriptId}/status` | GET | 200 |
| Transcripts | 12.2 | `/interactions/{id}/transcripts/{transcriptId}` | DELETE | 204 |
| Recordings | 9 | `/interactions/{id}/recordings/` | GET (LIST) | 200 |
| Recordings | 10 | `/interactions/{id}/recordings/` | POST (upload) | 201 |
| Recordings | 11 | `/interactions/{id}/recordings/{recordingId}` | GET (single) | 200 (text/plain binary) |
| Recordings | 12 | `/interactions/{id}/recordings/{recordingId}` | DELETE | 204 |

**STT family: 9 of 9 endpoints complete (100%). Phase 1.3 STT parity closed.**

## Phase 1.3 cumulative metrics

- **Cycles**: 6 + 7 + 8 + 9 + 10 + 11 + 12 + 12.1 + 12.2 = **9 cycles** for STT family
- **Total test count growth**: 126 (pre-STT) → 182 (post-STT) = **+56 tests**
- **Commits**: `729a2e6` → `e594dee` → `d8f852f` → `5bbb4e6` → `44219ad` → `8a37918` → `7504164` → `8805ca9` → (cycle 12.2 incoming)
- **Spec docs archived**: 9 (`docs/corti-reverse-engineered/stt-*.md` + `docs/phase_cycles/cycle_*_stt_*/`)
- **Walker fixes**: 1 (cycle 6's `$ref + parent-level metadata`); reused cycles 7/8/12.1

## Auto-advance: Phase 1.3 STT parity COMPLETE

Per the parity queue, the next Corti §13 family to align would be:
- **Facts** (Corti §13.5 — typically 3-4 endpoints: list, get, search)
- **Codes** (Corti §13.6 — typically 2-3 endpoints)
- **Languages** (Corti §13.7 — typically 1-2 endpoints: list)

Or wrap up Phase 1.3 entirely and move to Phase 1.4 (whatever's next per roadmap).

**Phase 1.3 STT parity: ✅ COMPLETE (9 of 9 endpoints).**