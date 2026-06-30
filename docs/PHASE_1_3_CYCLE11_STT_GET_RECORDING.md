# Phase 1.3 Cycle 11 — Recordings (STT) Get align Corti §13.3

## Context

Phase 1.3 cycle 10 (`44219ad`) shipped the **first recordings mutation** — `POST /api/v2/tools/interactions/{id}/recordings/` (upload-recording, octet-stream). Cycle 11 closes the **single-recording retrieval** endpoint — `GET /api/v2/tools/interactions/{id}/recordings/{recordingId}` (get-recording).

Notable spec semantics (KEY DIFFERENCES from cycle-7 get-transcript):
- **Returns raw binary** (`text/plain` + `format: binary`), NOT a JSON envelope. The **second non-JSON response** in iCoDer's v2 surface.
- **Path: NO trailing slash** (unlike cycle-7 which also has no trailing slash for get-single, but cycle-6 LIST has it).
- **404 error code** added (cycle-7 get-transcript did NOT have 404; missing recordings return 404 not 400).
- **Walker not needed** — response is opaque bytes, not a structured envelope.

## Spec source

`docs/corti-reverse-engineered/stt-get-recording.md` (7,160 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/recordings/get-recording.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_11_stt_get_recording/corti-stt-get-recording.md`.

## Endpoint surface

```
GET /api/v2/tools/interactions/{interaction_id}/recordings/{recording_id}
Authorization: Bearer <jwt or oauth>

→ 200 OK   text/plain (format: binary) — raw audio bytes
→ 400, 403, 404, 500, 504   RFC9457 ErrorResponse
→ 503            service_unavailable (hospital-pilot gate)
```

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/api/v2_tools_stt.py` | MODIFIED | Added `get_v2_tools_interaction_recording` GET endpoint with `Response` body + X-Stub-* path-echo headers |
| `backend/tests/test_api/test_v2_stt_get_recording_consistency.py` | NEW | 6 回环一致性测试 |
| `docs/PHASE_1_3_CYCLE11_STT_GET_RECORDING.md` | NEW | this file |
| `docs/phase_cycles/cycle_11_stt_get_recording/corti-stt-get-recording.md` | NEW | archive |

## Stub data

Stub returns 64 bytes of zeros (placeholder audio bytes). Path-echo via headers:
- `X-Stub-Recording-Id: {recording_id}`
- `X-Stub-Interaction-Id: {interaction_id}`

(Headers instead of body, since body is opaque binary.)

Sentinel pattern:
- `missing-{uuid}` → 404 `recording_not_found` (exercises the 404 error path)
- Default → 200 + 64 bytes of zeros

## Hospital-pilot gate

Same 503 gate as cycles 1-10. No additional gating for cycle 11.

## 回环一致性测试 pattern

**Walker not used** — response is raw binary, no shape validation. Tests focus on:
- Spec sanity (right paths/schemas captured)
- Content-type assertion (`text/plain` per spec)
- Body is opaque bytes (NOT JSON)
- 404 sentinel for missing recordingId
- Path-echo via headers
- 404 error code presence in spec

6 tests cover:

```
test_stt_get_recording_spec_is_real_and_cached                           PASSED
test_v2_stt_get_recording_default_returns_binary                         PASSED
test_v2_stt_get_recording_missing_sentinel_returns_404                   PASSED
test_v2_stt_get_recording_path_echo_via_headers                          PASSED
test_v2_stt_get_recording_interaction_id_missing_returns_400             PASSED
test_v2_stt_get_recording_content_type_is_text_plain                     PASSED
6 passed in 1.15s
```

Full `tests/test_api` regression: **165/165 PASS** in 3:49 (was 159 pre-cycle-11, +6 for this cycle). tsc clean.

## Design decisions

1. **Path-echo via headers, not body.** Since body is opaque binary, can't echo IDs in body. Used `X-Stub-Recording-Id` / `X-Stub-Interaction-Id` headers for testability.
2. **`Response` with `media_type="text/plain"`**. FastAPI's Response class lets us specify content + media type precisely. The spec's `text/plain` is unusual for binary (normally `application/octet-stream`) but we honor it.
3. **404 sentinel `missing-{uuid}`**. New sentinel pattern for cycle 11 (missing recordings). Distinct from cycle-7's `processing-` / `failed-` sentinels which are transcript state sentinels.
4. **No walker needed.** Trivial opaque response — walker validates structured shapes, not binary blobs.
5. **Test fixup during iteration**: First test run failed because FastAPI wraps HTTPException detail in `{"detail": {...}}`. Fixed by reading `body["detail"]["status"]` instead of `body["status"]`. This is consistent with how cycles 1-10 also wrap HTTPException responses (they just didn't trip on it because their error paths weren't deeply inspected).

## Out of scope (explicit, future cycles)

- ❌ Real audio retrieval from storage — stub returns 64 zero bytes
- ❌ Content-Type negotiation (`Accept` header → `audio/mpeg`, `audio/wav`, etc.)
- ❌ Range requests (`Range: bytes=0-1024` for resumable downloads)
- ❌ `DELETE /interactions/{id}/recordings/{recordingId}` — Cycle 12 (last recording endpoint)
- ❌ `GET /interactions/{id}/transcripts/{transcriptId}/status` — Cycle 11.1
- ❌ `DELETE /interactions/{id}/transcripts/{transcriptId}` — Cycle 11.2
- ❌ Frontend audio playback widget — out of scope: Phase 1.3 = backend wire parity only

## Risk register

| Risk | Mitigation |
|---|---|
| `text/plain` content-type unusual for audio | Honor Corti spec exactly; real callers may need `Accept: application/octet-stream` for client compatibility |
| 64-byte placeholder not a real audio file | Stub-only; real audio storage is separate Phase 1.3 task |
| Path-echo via headers (not body) | Acceptable since body is opaque binary; real callers can parse URL params |

## Auto-advance: Cycle 12 = delete-recording (REST DELETE)

Per the parity queue. Cycle 12 will close `DELETE /interactions/{id}/recordings/{recordingId}` — the last recording endpoint. Will return 204 No Content on success. Will be the **last endpoint of the recordings family** (4 of 4 closed).