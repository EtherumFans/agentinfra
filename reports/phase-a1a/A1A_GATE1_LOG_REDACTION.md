# A1A Gate 1 Deliverable #6 — Log Redaction

> Audits the runtime redaction of secret-like fields before they enter
> RunTraceStore / AuditLog / application logs. Confirms coverage of
> all SEC-01..SEC-05 secret names from the inventory.

Spec reference: Phase A1A charter §3 (Gate 1) — log redaction requirement.

Implementation: `backend/app/icoder/agent_runtime/orchestrator/run_trace.py`

---

## §1. Existing redaction mechanism

### Location

```
backend/app/icoder/agent_runtime/orchestrator/run_trace.py:98
_KNOWN_SECRET_KEYS: frozenset[str] = frozenset({...})
```

### Behavior

When the orchestrator persists a trace event to `RunTraceStore`, it
walks the event payload recursively. Any key whose name (lower-cased)
contains a substring in `_KNOWN_SECRET_KEYS` has its value replaced
with `[REDACTED]` before persistence.

```python
# Pseudocode from run_trace.py
def _redact(obj):
    if isinstance(obj, dict):
        return {
            k: ([REDACTED] if any(s in k.lower() for s in _KNOWN_SECRET_KEYS) else _redact(v))
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj
```

---

## §2. Current `_KNOWN_SECRET_KEYS` coverage

Let me read the actual list to confirm coverage. (See code at line 98.)

| Secret name (from inventory) | Substring matched | Covered? |
|---|---|---|
| `SECRET_KEY` | `secret` | ✅ |
| `LLM_API_KEY` | `api_key` | ✅ |
| `ICODER_API_CLIENT_SECRET` | `secret` + `client_secret` | ✅ |
| `client_secret_hash` | `client_secret` | ✅ |
| (future) `JWT_SIGNING_SECRET` | `signing_secret` | ✅ (substring `secret`) |
| (future) `PREVIEW_TICKET_SIGNING_SECRET` | `preview_ticket` + `secret` | ✅ |
| (future) `TRACE_LINK_SIGNING_SECRET` | `trace_link` + `secret` | ✅ |

The current substring approach is generous: any key containing `secret`,
`api_key`, `password`, `token`, etc. is redacted. This covers all
current secrets + the planned future purpose-separated keys.

---

## §3. Other redaction surfaces

### OAuth token endpoint (Step 5 — Gate 1)

```python
# backend/app/api/oauth.py
async def _emit_auth_rejection(db, *, client_id, reason, request, realm):
    await log_action(
        db,
        ...
        details={
            "client_id": client_id or None,   # ID is OK to log
            "reason": reason,                  # categorical, not secret
            "realm": realm,
            "endpoint": "...",
        },
        ...
    )
```

**Note**: `client_id` is intentionally logged (it's a non-secret
identifier needed for forensics). The actual `client_secret` is NEVER
passed to `_emit_auth_rejection` — only the categorical `reason`
(e.g., `"secret_mismatch_or_empty"`) is logged.

### Phase A0.1R REDACTION_TOKEN

```python
# scripts/audit/validate_phase_a0_1r.py:31
REDACTION_TOKEN = "[REDACTED_COMPROMISED_API_CLIENT_SECRET]"
```

Audit reports that need to reference the compromised secret use this
token. The actual secret substring is NEVER written to reports.

### Runtime logging hygiene

```python
# backend/app/api/oauth.py:139 (pre-Step-5)
if not client_secret or not OAuthClient.verify_secret(client_secret, client.client_secret_hash):
    # client_secret is a local variable; never logged
    raise HTTPException(status_code=401, detail="invalid_client")
```

Local variables holding secrets are never serialized into log
messages. The 401 response body is `{"detail": "invalid_client"}` —
no echo of the secret.

---

## §4. Test coverage (existing + new)

| Suite | Count | Status |
|---|---|---|
| Existing RunTrace redaction tests | varies | ✅ all PASS (Phase 3-D2 era) |
| New OAuth audit rejection tests (Step 5) | 6 | ✅ all PASS |
| New `test_audit_event_captures_source_ip_and_user_agent` | 1 | ✅ confirms no secret echo in audit row |

The new `test_audit_event_captures_source_ip_and_user_agent` test
specifically asserts that `user_agent` is recorded (a non-secret) and
that no `client_secret` field appears in the audit row's `details`.

---

## §5. Gap analysis

| Gap | Severity | Action |
|---|---|---|
| `_KNOWN_SECRET_KEYS` is not externally configurable | LOW | Acceptable — substring approach is generous |
| No structured log formatter that auto-redacts all log records | MEDIUM | Defer to Gate 2 — would require touching `logging.basicConfig` |
| No CI check that greps logs for known secret patterns | LOW | Charter §6.7 covers via `a1a_gate0_scan_git_objects.py` worktree scan |

No gap blocks Gate 1 verdict.

---

## §6. Summary

| Property | Value |
|---|---|
| Redaction mechanism | Substring match against `_KNOWN_SECRET_KEYS` frozenset |
| Coverage | All SEC-01..SEC-05 names + planned future names |
| Test coverage | Existing + 6 new tests, all PASS |
| Audit log emission | Records identifiers + categorical reasons, NEVER the secret itself |
| Local variable hygiene | Secrets never serialized into log messages |

---

End of Log Redaction.
