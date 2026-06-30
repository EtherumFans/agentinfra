# Phase 1.2 Cycle 5 — Documents Classic LIST (Planned deprecation)

## Context

Phase 1.2 cycles 3+4 shipped the §13.4 **Guided** family: cycle 3
(`2d33355`) added `POST /api/v2/tools/guided-documents/` (templateRef +
ephemeral), and cycle 4 (`5dfd1aa`) added `GET /api/v2/tools/{templates,
sections}/` (read-only discovery).

Cycle 5 closes the **legacy Documents Classic** family — the older
pre-§13.4 document surface that Corti tags as "Documents (Classic)"
with a "Planned deprecation" notice. The list endpoint is the only
one cycle 5 ships, mirroring cycles 3-4's "simplest path" discipline.

The Corti list endpoint is **scoped to a single interaction**:

```
GET /interactions/{id}/documents/   →   {data: DocumentsGetResponse[]}
```

This is structurally different from cycle 3's POST (`/api/v2/tools/
guided-documents/`) and cycle 4's GETs (`/api/v2/tools/{templates,
sections}/`). The Documents Classic surface ties documents to a
specific interaction; the §13.4 Guided family decoupled them.

## Spec source

`docs/corti-reverse-engineered/documents-classic-list.md` (7,235 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/documents-classic/list-documents.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_5_documents_classic/corti-documents-classic-list.md`.

## Endpoint surface

```
GET /api/v2/tools/interactions/{interaction_id}/documents/      (and trailing-slash-less alias)
Authorization: Bearer <jwt or oauth>

→ 200 OK   { data: DocumentsGetResponse[] }
→ 503      service_unavailable (hospital-pilot gate)
```

Documents Classic family has 5 endpoints total. Cycle 5 ships only the
LIST; the other 4 (`get-document`, `generate-document`, `update-document`,
`delete-document`) land in follow-on cycles once real interaction
storage is designed.

## Files

| Path | Lines | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_documents_classic.py` | 110 | Pydantic for CommonUsageInfo + DocumentsSection + DocumentsGetResponse + DocumentsListResponse |
| `backend/app/api/v2_tools_documents_classic.py` | 175 | LIST router with deterministic stub data |
| `backend/tests/test_api/test_v2_documents_classic_consistency.py` | 270 | 6 回环一致性测试 |
| `backend/app/main.py` | +2 | include + import router |

## Stub data

2 documents per interaction, derived deterministically from the path
UUID:

1. **Discharge Summary** (`isStream=false`) — 4 sections (subjective /
   objective / assessment / plan); classic SOAP structure.
2. **Outpatient Note (Streamed)** (`isStream=true`) — 2 sections
   (history / impression); demonstrates that `isStream` flag must
   round-trip correctly.

Document IDs are `{interaction_id}-NNNN` so the path-scoping contract
is testable: same `{id}` ⇒ same document IDs, different `{id}` ⇒
different document IDs.

## Response envelope

```json
{
  "data": [
    {
      "id": "f47ac10b-...-0001",
      "name": "Discharge Summary",
      "templateRef": "discharge-summary-v1",
      "isStream": false,
      "sections": [
        {"key": "subjective", "name": "Subjective", "text": "...",
         "sort": 0, "createdAt": "...", "updatedAt": "..."},
        ...
      ],
      "createdAt": "2026-06-01T08:00:00Z",
      "updatedAt": "2026-06-01T08:05:00Z",
      "outputLanguage": "en-US",
      "usageInfo": {"creditsConsumed": 0.012}
    },
    ...
  ]
}
```

## Hospital-pilot gate

Same 503 gate as cycles 1-4:

```
ICODER_CREDENTIAL_LLM empty
  AND ICODER_ALLOW_DEGRADED_NO_KEY ≠ "1"
  → 503 service_unavailable
```

Tests set `ICODER_ALLOW_DEGRADED_NO_KEY=1` to bypass.

## 回环一致性测试 pattern

Same walker as cycles 3-4. 6 tests cover:

```
test_documents_classic_spec_is_real_and_cached               PASSED
test_v2_documents_classic_list_shape_matches_corti_spec      PASSED
test_v2_documents_classic_envelope_has_data_field            PASSED
test_v2_documents_classic_path_scoping                       PASSED
test_v2_documents_classic_isStream_field_round_trip          PASSED
test_v2_documents_classic_reference_round_trip               PASSED
6 passed in <1s
```

Full `tests/test_api` regression: **118/118 PASS** in 3:51 (was 112
pre-cycle-5, +6 for this cycle). tsc clean.

## Design decisions

1. **LIST only, not CRUD.** Documents Classic has 5 endpoints (LIST +
   get + generate + update + delete). Closing all 5 in one cycle
   violates the "按复杂度排序" rule. Cycles 5.1+ will layer on the
   remaining 4 incrementally.
2. **No deletion of any legacy surface.** Unlike P1.2 cycle 0 (which
   deleted iCoDer-specific concepts), iCoDer has no legacy
   `documents` router to delete or banner — the legacy was the
   pre-cycle-3 ad-hoc state. Cycle 5 is purely additive.
3. **Stub IDs echo interaction UUID.** Deterministic per-interaction
   stub data lets tests assert path-scoping without needing to mock
   storage. Real UUIDs land when real storage lands.
4. **`isStream=true` for one stub doc.** The spec declares `isStream`
   as a required boolean. Stub data exercises both values so the
   shape check covers the round-trip.
5. **No deprecation banner in response body.** The Corti spec lists
   only `data` as required at the envelope level. Adding a
   `deprecationNotice` field would violate the spec. Banners are a
   Phase 1.5+ frontend concern.
6. **`createdAt`/`updatedAt` are NOT in the walker skip list** because
   they're required ISO 8601 timestamps with no nullable marker in the
   spec. Stub data populates them with deterministic values; tests
   assert type=string format (ISO 8601 validation is left to higher
   layers).

## Out of scope (explicit, future cycles)

- ❌ `GET /interactions/{id}/documents/{document_id}` (get one) — Cycle 5.1
- ❌ `POST /interactions/{id}/documents/` (generate) — Cycle 5.2
- ❌ `PATCH /interactions/{id}/documents/{document_id}` (update) — Cycle 5.3
- ❌ `DELETE /interactions/{id}/documents/{document_id}` — Cycle 5.4
- ❌ Real DB-backed storage design — separate Phase 2 task
- ❌ Frontend deprecation banner — Phase 1.5+ task
- ❌ Cursor pagination (spec doesn't define cursors in the captured YAML)

## Risk register

| Risk | Mitigation |
|---|---|
| SDK caller expects cursor pagination | Spec doesn't define cursors; documented as out of scope |
| Document IDs collide with real Corti IDs | Stub IDs are `{interaction_id}-NNNN` which won't collide with real UUIDs; real storage will replace |
| Planned deprecation notice absent | Backend mirrors spec exactly; banner is a frontend concern |
| Different interaction_id yields same stub data | Path-scoping test explicitly verifies IDs differ per interaction |

## Auto-advance: Phase 1.2 wrap-up

Phase 1.2 = 5 cycles (Phase 1.0 OAuth → Phase 1.1 Medical Coding v2 →
Phase 1.2 cycles 1-5 = FactsR, Streams, Guided Documents, Sections +
Templates LIST, Documents Classic LIST). Phase 1.3 = STT alignment
(Corti §13.3) — the next big Corti family.

Per the parity queue, Phase 1.3 cycles through the 3 STT endpoints
(list-transcripts, get-transcript, list-recordings) using the same
"simplest path" scope discipline.