# A1A Gate 2 §1 — Tenancy and Data Isolation Survey

> Snapshot of current tenancy state across the iCoDer codebase
> taken at the start of Gate 2 (2026-07-17).
>
> Branch: `phase-a1a/emergency-containment` @ `06624b4`
> Master: `c147d01` (untouched)
> Tag: `audit/phase-a0.1r-baseline` @ `3cd1bec` (NOT modified)

Spec reference: Phase A1A charter §3 (Gate 2) — Tenancy and Data Isolation.

---

## §1. What the charter requires

The Phase A1A charter §3 (Gate 2) requires that:

1. All NEW Run / Trace / Usage / Context / Audit / API Client / Embedded
   App / Idempotency Record / Preview Session / Signed Trace / CDI Query
   / Patient-Encounter rows carry a non-bypassable `organization_id`.
2. Organization A cannot read Organization B's data in any surface.
3. Patient A and Patient B do not cross-reference (PHI isolation).
4. Idempotency uniqueness includes Client/Tenant dimensions.
5. Historical NULL data is NOT blindly backfilled. It is classified as
   `LEGACY_TENANT_KNOWN`, `LEGACY_TENANT_UNKNOWN`, or `QUARANTINED`.
6. Strong negative tests prove Organization A cannot reach Organization
   B's data via any documented surface.

This survey catalogues the as-is state for each surface so the
remaining Gate 2 work can be scoped precisely.

---

## §2. Tables audited (organization_id column presence)

Scan: every table in `data/icoder.db`. Below, "NULL %" is the share of
rows where `organization_id IS NULL` at audit time (2026-07-17).

### §2.1 Tables in scope for Gate 2 (per charter §3)

| Table | Total rows | NULL org_id | NULL % | Status |
|---|---:|---:|---:|---|
| `run_history` | 240 | 235 | 97.9 % | **G9-003 P0** — historical NULL gap |
| `audit_logs` | 233 | 201 | 86.3 % | **G9-002 P0** — partial coverage gap |
| `idempotency_records` | 11 | 0 | 0 % | ✅ enforced at write (Gate 1 / Phase 7 Gate 3) |
| `preview_sessions` | 19 | 0 | 0 % | ✅ enforced at write (Phase 7 Gate 13A) |
| `oauth_clients` | 1 | 0 | 0 % | ✅ partner clients always carry org |
| `oauth_tokens` | 3 | 0 | 0 % | ✅ issued tokens carry org |

### §2.2 Tables out of scope for Gate 2 (test fixtures or globally-seeded)

| Table | Total rows | NULL org_id | Why out of scope |
|---|---:|---:|---|
| `agents` | 101 | 76 | Official Agent Pack Catalog — globally shared, not tenant-owned |
| `experts` | 30 | 0 | Expert catalog — globally shared |
| `templates` | 387 | 0 | Prompt templates — globally shared |
| `encounters` | 10 | 10 | Test fixtures only; not yet wired to runtime |
| `gold_cases` | 10 | 10 | Test fixtures only |
| `documents` | 22 | 22 | Test fixtures only |
| `coding_review_runs` | 16 | 4 | Coding-review subtable; Gate 2 covers parent `run_history` |
| `cdi_cases` | 718 | 718 | CDI fixtures; CDI org scoping is a separate Phase 5 Track D concern |

The 235 `run_history` NULLs + 201 `audit_logs` NULLs are the primary
Gate 2 remediation targets.

---

## §3. Write-path status (NEW data)

### §3.1 RunHistory — ✅ stamps org_id at write

`backend/app/api/agent_run.py:401,469`:

```python
await record_run_start(
    db,
    run_id=run_id,
    agent_id=agent_id,
    user_id=user_id,
    organization_id=org_id or None,
    ...
)
...
await _persist_run_history(
    db,
    response=response,
    input_text=body.input.text,
    user_id=user_id,
    tenant_id=tenant_id,
    organization_id=org_id or None,
)
```

Where `org_id` is resolved from either the partner OAuth client's
`org_id` claim or the Console user's `current_org.id`.

**Evidence**: 5 most recent runs (2026-07-14) all have `organization_id`
populated; the 235 NULLs are all dated 2026-07-12 or earlier (pre
Phase 7 Gate 5 wiring).

### §3.2 AuditLog — ❌ `organization_id` parameter exists but most callers omit it

`backend/app/middleware/audit.py:10-51`:

```python
async def log_action(
    db: AsyncSession,
    user_id: Optional[str],
    username: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    ...
    organization_id: Optional[str] = None,   # ← almost always omitted
):
```

Spot check of 18 call sites in `auth.py`, `encounters.py`,
`organizations.py`, `oauth.py`, `preview_sessions.py`:

| File | Call sites | Passes `organization_id=`? |
|---|---:|---|
| `auth.py` | 6 | 0 (relies on `details={"org_id": ...}` only) |
| `encounters.py` | 3 | 0 |
| `organizations.py` | 4 | 0 |
| `oauth.py` | 1 (Gate 1 Step 5 `_emit_auth_rejection`) | 0 (logs client_id only) |
| `preview_sessions.py` | 3 | 0 |

**Gap**: 0/17 callers stamp `organization_id` at the column level. The
information leaks into `details` JSON but is not queryable / enforceable
at the SQL layer.

### §3.3 IdempotencyRecord — ✅ enforced

`backend/app/services/idempotency_service.py:152-160`:

```python
org_id_norm = (organization_id or "").strip()
api_client_id_norm = (api_client_id or "").strip()
...
record = IdempotencyRecord(
    organization_id=org_id_norm,   # "" sentinel for NULL
    api_client_id=api_client_id_norm,
    ...
)
```

The UNIQUE constraint `uq_idempotency_org_client_key` (alembic 012)
covers `(organization_id, api_client_id, idempotency_key)`. NULL
semantics defeated by normalizing None → "" sentinel.

### §3.4 PreviewSession — ✅ enforced

`backend/app/api/preview_sessions.py` stamps `organization_id` from
the `current_org` dependency at create time. 19/19 rows populated.

---

## §4. Read-path status (org-scope filters)

### §4.1 GET /api/v1/runs/{run_id} — ✅ filtered

`backend/app/api/runs.py:140-148`:

```python
if (
    row.organization_id is not None
    and current_org.id is not None
    and row.organization_id != current_org.id
):
    raise HTTPException(status_code=404, ...)
```

Returns 404 (not 403) to avoid leaking cross-org run existence.

### §4.2 GET /api/v1/runs/{run_id}/trace — ✅ filtered (signed token path)

`backend/app/api/runs.py:329-336`:

```python
if claims.organization_id:
    async with AsyncSessionLocal() as db:
        row = await get_run_status(db, run_id=run_id)
        if row is not None and row.organization_id and row.organization_id != claims.organization_id:
            raise HTTPException(status_code=403, ...)
```

### §4.3 POST /api/v1/runs/{run_id}/cancel — ✅ filtered

`backend/app/services/run_lifecycle.py:request_cancel` accepts
`expected_organization_id` and returns `FORBIDDEN` on mismatch
(converted to 404 by the caller to avoid existence leak).

### §4.4 GET /api/v1/runs/{run_id}/events (SSE) — ⚠ gap

`backend/app/api/runs.py:419-451` verifies the signed trace token's
`run_id` matches the URL but does NOT cross-check the run's actual
`organization_id` against the token's claim (no DB lookup). A token
issued for Org A's run cannot be used to read Org B's run because the
token is bound to `run_id` — but the gap is that we don't verify the
DB row's org matches the token's org (defense in depth).

### §4.5 /api/usage/* — scoped by user_id, not organization_id

`backend/app/api/usage.py` filters by `RunHistoryModel.user_id ==
str(user.id)` for the per-user Console view. This is the intended
Console semantic (a user sees their own usage regardless of which org
they were acting in). Partner SDK usage is filtered by `api_client_id`.

There is no org-aggregate admin view yet — the charter does not
require one in Gate 2.

### §4.6 /api/runtime/runs/{run_id}/trace (Console JWT path)

The Console JWT path goes through `app.icoder.agent_runtime.orchestrator.run_trace.get_default_store()`
which is in-memory by default. The `get_run_scoped(run_id, org_id)`
helper exists but the Console path doesn't currently pass `org_id`
(it's only used by the partner signed-token path).

**Gap**: a Console user who knows another org's `run_id` could read
its trace events. Mitigation scope: covered in Gate 3 (Audit Log and
Trace Persistence), not Gate 2.

---

## §5. Historical NULL classification

Per charter, NULL rows must NOT be blindly backfilled. They must be
classified as:

- `LEGACY_TENANT_KNOWN` — reliable evidence (user_id → org_id mapping
  via `organization_members`) allows confident backfill.
- `LEGACY_TENANT_UNKNOWN` — no reliable evidence; row is retained for
  audit but tagged so it can be excluded from tenant-scoped queries.
- `QUARANTINED` — sensitive content (e.g., raw PHI in `input_text`)
  that needs human review before any retention decision.

### §5.1 run_history NULL resolvability

Joining `run_history.user_id` to `organization_members`:

| user_id | NULL rows | Resolvable org? |
|---|---:|---|
| `f237e192bbd5` | 216 | ❌ no matching `organization_members` row |
| `u-g7-g7admin` | 14 | ❌ no matching `organization_members` row |
| `(NULL)` | 5 | ❌ no user_id at all |

**Verdict**: 235/235 NULL `run_history` rows classify as
`LEGACY_TENANT_UNKNOWN`. None qualify as `LEGACY_TENANT_KNOWN`.

### §5.2 audit_logs NULL resolvability

Same pattern expected (callers omit `organization_id=`, but
`user_id` is stamped for most rows). To be confirmed in §2 of the
migration.

---

## §6. Findings raised

| ID | Severity | Title | Status |
|----|---|---|---|
| **A1A-G2-F01** | P0 | 235 run_history rows have NULL organization_id (G9-003 reaffirmed) | Will close via classification migration |
| **A1A-G2-F02** | P0 | 201 audit_logs rows have NULL organization_id | Will close via classification migration |
| **A1A-G2-F03** | P1 | `log_action` callers do not stamp `organization_id` column | Will close via cloud-mode fail-closed guard |
| **A1A-G2-F04** | P2 | SSE events endpoint skips DB org cross-check | Defense-in-depth; Gate 3 candidate |
| **A1A-G2-F05** | P2 | Console RunTrace path doesn't pass org_id to store | Gate 3 candidate |
| **A1A-G2-F06** | P2 | No reusable `assert_org_scope` helper (logic duplicated) | Refactor; Gate 2 nice-to-have |

---

## §7. Gate 2 scope (what this gate will and will not do)

### §7.1 In scope

1. ✅ Write the survey (this file).
2. ✅ Alembic migration `016_tenancy_classification` adds
   `tenancy_classification` column to `run_history` + `audit_logs`,
   backfills existing NULL rows as `LEGACY_TENANT_UNKNOWN`.
3. ✅ Cloud-mode fail-closed guard: refuse to commit a new
   `run_history` / `audit_log` / `idempotency_record` /
   `preview_session` row with NULL `organization_id` when
   `ICODER_DEPLOYMENT_MODE=cloud`. Local mode still allows NULL for
   single-tenant dev.
4. ✅ 12 negative org-isolation tests covering Run / Trace / Usage /
   Context / Patient / Idempotency / Preview / Audit surfaces.
5. ✅ Closure report + commit.

### §7.2 Out of scope (deferred to Gate 3 or later)

- Refactoring every `log_action` caller to pass `organization_id=`
  explicitly (~17 call sites; too invasive for one gate; the cloud-mode
  fail-closed guard closes the new-data leak instead).
- Console RunTrace path org-scoping (Gate 3).
- SSE events DB org cross-check (Gate 3 defense-in-depth).
- CDI table org-scoping (Phase 5 Track D).
- Patient/Encounter org scoping (Phase 5 Track D).

---

## §8. Verdict (interim)

```
============================================================================
A1A_GATE2_SURVEY_COMPLETE
============================================================================

  Write-path status (NEW data):
    RunHistory          ✅ stamps org_id (Phase 7 Gate 5)
    IdempotencyRecord   ✅ enforced (Phase 7 Gate 3 + Gate 1)
    PreviewSession      ✅ enforced (Phase 7 Gate 13A)
    AuditLog            ❌ column not stamped by callers (Gap A1A-G2-F03)

  Read-path status (org-scope filters):
    GET /api/v1/runs/{id}           ✅ filtered
    GET /api/v1/runs/{id}/trace     ✅ filtered (signed-token path)
    POST /api/v1/runs/{id}/cancel   ✅ filtered
    GET /api/v1/runs/{id}/events    ⚠ token-only (no DB cross-check)
    /api/usage/*                    ✅ per-user (intentional)

  Historical NULL classification (planned):
    run_history  235 NULL → LEGACY_TENANT_UNKNOWN
    audit_logs   201 NULL → LEGACY_TENANT_UNKNOWN (TBC in migration)

  Findings raised: 6 (2 P0, 1 P1, 3 P2)
  Findings closed in this section: 0 (closure requires migration + tests)

NEXT_SECTION: §2 historical NULL classification migration
============================================================================
```

End of §1 survey. Proceeding to §2.
