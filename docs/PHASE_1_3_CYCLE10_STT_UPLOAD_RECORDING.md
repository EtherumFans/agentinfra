# Phase 1.3 Cycle 10 — Recordings (STT) Upload align Corti §13.3

## Context

Phase 1.3 cycle 9 (`5bbb4e6`) shipped the **first recordings endpoint** — `GET /api/v2/tools/interactions/{id}/recordings/` (list-recordings). Cycle 10 closes the **first recordings mutation endpoint** — `POST /api/v2/tools/interactions/{id}/recordings/` (upload-recording).

This is the **prerequisite for create-transcript to be a real wire**. Cycle 8's stub `recordingId` references a hypothetical upload. Cycle 10 makes the upload endpoint real (in stub form) — callers can now chain: upload-recording → create-transcript referencing the returned recordingId.

Notable spec semantics:
- **Content-Type: `application/octet-stream`** — raw binary body (audio file). NOT multipart, NOT JSON.
- **First non-JSON content-type** in iCoDer's v2 surface.
- **Size limit: 150 MB / 120 minutes audio** per spec. The stub enforces the 150 MB cap (returns 400) but does not enforce the 120-minute audio duration (would require parsing audio metadata).
- **Response 201**: `{recordingId: UUID}` — minimal envelope, just the new recording's ID.

## Spec source

`docs/corti-reverse-engineered/stt-upload-recording.md` (6,386 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/recordings/upload-recording.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_10_stt_upload_recording/corti-stt-upload-recording.md`.

## Endpoint surface

```
POST /api/v2/tools/interactions/{interaction_id}/recordings/
Authorization: Bearer <jwt or oauth>
Content-Type: application/octet-stream

Body: raw binary audio (max 150 MB / 120 min)

→ 201 Created  RecordingsCreateResponse
                 { recordingId: UUID }
→ 400, 403, 500, 504   RFC9457 ErrorResponse
→ 503            service_unavailable (hospital-pilot gate)
```

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | Added `RecordingsCreateResponse` |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | Added `upload_v2_tools_interaction_recording` POST endpoint with `Request` body reader + 150 MB cap enforcement |
| `backend/tests/test_api/test_v2_stt_upload_recording_consistency.py` | NEW | 7 回环一致性测试 |
| `docs/PHASE_1_3_CYCLE10_STT_UPLOAD_RECORDING.md` | NEW | this file |
| `docs/phase_cycles/cycle_10_stt_upload_recording/corti-stt-upload-recording.md` | NEW | archive |

## Stub data

Stub returns deterministic recordingId derived from interaction_id:
- `recordingId = f"{interaction_id}-rec-stub"`

Empty body → 400 (rejected). Body > 150 MB → 400 (rejected).

## Hospital-pilot gate

Same 503 gate as cycles 1-9. No additional gating for cycle 10.

## 回环一致性测试 pattern

Reuses cycle-6/7/8/9 walker (with `$ref + parent-level metadata` fix) unchanged. Cycle 10 response envelope is trivial (`{recordingId: UUID}`) — no walker changes needed.

7 tests cover:

```
test_stt_upload_spec_is_real_and_cached                       PASSED
test_stt_upload_response_required_field                       PASSED
test_v2_stt_upload_binary_body_returns_201                    PASSED
test_v2_stt_upload_empty_body_rejected                        PASSED
test_v2_stt_upload_path_echoes_interaction_id                 PASSED
test_v2_stt_upload_trailing_slash_alias                       PASSED
test_v2_stt_upload_reference_round_trip                       PASSED
7 passed in 1.16s
```

Full `tests/test_api` regression: **159/159 PASS** in 3:54 (was 152 pre-cycle-10, +7 for this cycle). tsc clean.

## Design decisions

1. **`application/octet-stream` body via `Request`**. Used `await request.body()` to read raw binary. FastAPI's `body: bytes` parameter type also works, but `Request` is more explicit and lets us return 400 for empty body cleanly.
2. **150 MB cap enforced** (per spec). Stub does NOT enforce 120-minute audio duration (would require audio parsing — separate task).
3. **Path-echo via deterministic UUID.** Stub returns `f"{interaction_id}-rec-stub"` so tests can verify path-scoping. Real recordingId would be a fresh server-assigned UUID.
4. **Trailing-slash dual registration.** Both `/recordings/` (matches Corti spec) and `/recordings` (REST convention) registered — consistent with cycle-6/8/9 LIST/POST patterns.
5. **No new walker changes.** Trivial envelope (`{recordingId: UUID}`) — walker already handles `type: string` + `$ref: UUID`.

## Out of scope (explicit, future cycles)

- ❌ Real audio storage (S3, blob store) — Cycle 10 stub does NOT persist the binary body
- ❌ Real audio metadata parsing (duration, sample rate) — would require ffmpeg or similar
- ❌ Multipart form upload — Corti spec uses raw octet-stream, not multipart
- ❌ `GET /interactions/{id}/recordings/{recordingId}` (get-recording) — Cycle 11
- ❌ `DELETE /interactions/{id}/recordings/{recordingId}` (delete-recording) — Cycle 12
- ❌ `GET /interactions/{id}/transcripts/{transcriptId}/status` — Cycle 10.1
- ❌ `DELETE /interactions/{id}/transcripts/{transcriptId}` — Cycle 10.2
- ❌ Frontend recording upload widget — out of scope: Phase 1.3 = backend wire parity only

## Risk register

| Risk | Mitigation |
|---|---|
| Stub does NOT persist binary body | Documented as out-of-scope; real audio storage is separate Phase 1.3 task |
| 150 MB cap checked via len() not actual size limit | FastAPI/Starlette auto-rejects payloads exceeding uvicorn's max body size; explicit check is belt-and-suspenders |
| 120-minute audio duration not enforced | Documented as out-of-scope; would require audio parsing |
| Octet-stream body could be misinterpreted as UTF-8 | We treat body as raw bytes; never decode to string |

## Auto-advance: Cycle 11 = get-recording (REST GET single)

Per the parity queue. Cycle 11 will close `GET /interactions/{id}/recordings/{recordingId}` — the single-recording retrieval endpoint. Will mirror cycle-7 get-transcript pattern: full payload, no `?full=` toggle, sentinel for "not found" state.