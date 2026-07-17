# A1A Gate 1 Deliverable #3 — Fail-Closed Env Policy

> Documents the fail-closed startup policy added in Gate 1 Step 4.
> Cloud mode refuses to boot if any required secret is missing or
> carries a known-weak default. Local mode remains permissive.

Spec reference: Phase A1A charter §3 (Gate 1) — fail-closed requirement.

Implementation: `backend/app/config.py` `_validate_fail_closed_policy()`
Tests: `backend/tests/unit/app/test_config_fail_closed.py` (10 tests, all PASS)

---

## §1. Policy summary

| Mode | Behavior |
|---|---|
| `ICODER_DEPLOYMENT_MODE=local` (default) | Permissive. Auto-generates a random `SECRET_KEY` if missing. Allows `SEED_ON_STARTUP=true` and `DEBUG=true`. |
| `ICODER_DEPLOYMENT_MODE=cloud` | Strict. Validates 10 invariants at `Settings.__init__` time. Raises `RuntimeError` if ANY fail. Uvicorn exits non-zero before binding socket. |

---

## §2. The 10 cloud-mode invariants

| # | Invariant | Failure mode |
|---|---|---|
| 1 | `SECRET_KEY` is not in weak-literal blocklist | RuntimeError |
| 2 | `ICODER_HOSTED_URL` is non-empty | RuntimeError |
| 3 | `ICODER_ENVIRONMENT` ∈ {eu, us, cn} | RuntimeError |
| 4 | `ICODER_REGION` is non-empty | RuntimeError |
| 5 | `ICODER_TENANT_ID` is non-empty | RuntimeError |
| 6 | `ICODER_API_CLIENT_ID` is non-empty | RuntimeError |
| 7 | `ICODER_API_CLIENT_SECRET` is non-empty | RuntimeError |
| 8 | `SEED_ON_STARTUP` is False (no auto admin/admin123) | RuntimeError |
| 9 | `DEBUG` is False | RuntimeError |
| 10 | Env var `ICODER_SECRET_KEY` overrides `.env` file value | (priority rule, not a check) |

---

## §3. Weak-secret blocklist

`SECRET_KEY.lower().strip()` must NOT be in:

```
"", "change-me", "change-me-in-production", "changeme",
"secret", "test", "dev", "development"
```

This blocklist catches the most common accidental defaults. The list
lives at module level (`_WEAK_SECRET_KEY_LITERALS`) so it is testable
without instantiating Settings.

---

## §4. Env var precedence

```python
# backend/app/config.py Settings.__init__
env_sk = os.environ.get("ICODER_SECRET_KEY")
if env_sk:
    self.SECRET_KEY = env_sk       # env wins
if not self.SECRET_KEY:
    self.SECRET_KEY = secrets.token_urlsafe(48)  # local dev fallback
```

This priority order ensures cloud KMS injection (env var) always wins
over any stale value in a `.env` file shipped with the image.

---

## §5. Test coverage

| Test | Scenario |
|---|---|
| `test_local_mode_boots_with_empty_secret` | Local mode auto-generates random SECRET_KEY |
| `test_cloud_mode_boots_with_all_required_vars` | All vars set → boots normally |
| `test_cloud_mode_refuses_weak_secret_change_me` | `change-me-in-production` → RuntimeError |
| `test_cloud_mode_refuses_empty_secret` | Empty → RuntimeError |
| `test_cloud_mode_refuses_missing_hosted_url` | Missing ICODER_HOSTED_URL → RuntimeError |
| `test_cloud_mode_refuses_invalid_environment` | ICODER_ENVIRONMENT=mars → RuntimeError |
| `test_cloud_mode_refuses_missing_tenant_id` | Missing ICODER_TENANT_ID → RuntimeError |
| `test_cloud_mode_refuses_seed_on_startup` | SEED_ON_STARTUP=true → RuntimeError |
| `test_cloud_mode_refuses_debug_true` | DEBUG=true → RuntimeError |
| `test_weak_secret_literals_covered_by_blocklist` | All 8 documented literals in blocklist |

Run:
```bash
cd backend && python -m pytest tests/unit/app/test_config_fail_closed.py -v
```

Result: **10/10 PASS**.

---

## §6. Runtime error message

When the policy fires, the error message lists every failing
invariant in one shot (not one-at-a-time) so operators can fix all
issues in a single restart cycle:

```
[A1A Gate 1 fail-closed] ICODER_DEPLOYMENT_MODE=cloud but:
  - SECRET_KEY is empty or a known-weak literal ('change-me-in-production'); ...
  - ICODER_HOSTED_URL is empty; required in cloud mode
  - SEED_ON_STARTUP=true is forbidden in cloud mode (would auto-create admin/admin123)
Refusing to boot. Fix the above env vars and restart.
```

---

## §7. Defense in depth

The policy is the LAST line of defense. The earlier layers are:

1. **Cloud KMS** injects `ICODER_SECRET_KEY` at deploy time (ops layer)
2. **CI pipeline** refuses to deploy if cloud env vars missing (process layer)
3. **Settings.__init__** validates at boot (this Gate 1 Step 4 — code layer)
4. **uvicorn startup** catches RuntimeError and exits non-zero (process layer)
5. **Kubernetes readiness probe** never becomes ready (orchestration layer)

A weak `SECRET_KEY` reaching production requires ALL 5 layers to fail.

---

End of Fail-Closed Env Policy.
