"""Health check — runs targeted checks against a running iCoDer backend.

Replaces the deleted icoder_doctor.py. Each check prints [PASS] / [FAIL reason].
Final line: VERDICT: PASS or VERDICT: FAIL. Exit code 0 = pass, 1 = fail.

Usage:
    python scripts/health_check.py --base-url http://localhost:8000
    python scripts/health_check.py --base-url http://localhost:8000 --json

Checks:
    1. alembic_head      — alembic current == alembic head
    2. schema_drift      — 0 divergences (ORM matches DB)
    3. registry_sync     — last_status == "success" (from /api/runtime/status)
    4. runtime_started   — /api/runtime/status returns 200 with started=true
    5. agents_installed  — agents table has >= 1 row
    6. auth_register     — POST /api/auth/register returns 201 (test user)
    7. auth_login        — POST /api/auth/login returns 200 (test user)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import urllib.error
import urllib.request

# Make `app.*` importable when run as a script from backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class HealthReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "PASS" if all(r.passed for r in self.results) else "FAIL"

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "total": len(self.results),
            "checks": [r.to_dict() for r in self.results],
        }


def _http_request(method: str, url: str, body: dict | None = None, timeout: float = 5.0) -> tuple[int, dict, str]:
    """Returns (status_code, json_body_or_empty, text_body)."""
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            text = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text) if text else {}
            except json.JSONDecodeError:
                parsed = {}
            return status_code, parsed, text
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {}
        return e.code, parsed, text
    except urllib.error.URLError as e:
        return 0, {}, f"connection failed: {e.reason}"


def _check_alembic_head() -> CheckResult:
    """alembic current == alembic head."""
    start = time.time()
    try:
        current = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            cwd=_BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if current.returncode != 0:
            return CheckResult(
                "alembic_head", False,
                f"alembic current failed: {current.stderr.strip()[:200]}",
                (time.time() - start) * 1000,
            )
        # Output looks like: "008 (head)" or "008\n" or "002\n"
        out = current.stdout.strip()
        # Take the last non-empty line
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        line = lines[-1] if lines else ""
        if "head" in line.lower():
            return CheckResult("alembic_head", True, f"at head: {line}", (time.time() - start) * 1000)
        # Not at head — check if it's just a revision
        heads = subprocess.run(
            [sys.executable, "-m", "alembic", "heads"],
            cwd=_BACKEND_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        head_rev = heads.stdout.strip().splitlines()
        head_rev = [ln.strip() for ln in head_rev if ln.strip()]
        if line in head_rev:
            return CheckResult("alembic_head", True, f"at head: {line}", (time.time() - start) * 1000)
        return CheckResult(
            "alembic_head", False,
            f"not at head (current={line}, head={head_rev})",
            (time.time() - start) * 1000,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("alembic_head", False, "alembic timed out (30s)", (time.time() - start) * 1000)


def _check_schema_drift() -> CheckResult:
    """0 divergences between ORM and DB."""
    start = time.time()
    try:
        from app.services.schema_drift_service import check_drift
        from app.config import settings
        # settings.DATABASE_URL is async (sqlite+aiosqlite://...); convert to sync
        db_url = settings.DATABASE_URL.replace("+aiosqlite", "")
        report = check_drift(db_url)
        if report.total == 0:
            return CheckResult(
                "schema_drift", True,
                f"0 divergences across {report.tables_checked} tables / {report.columns_checked} columns",
                (time.time() - start) * 1000,
            )
        return CheckResult(
            "schema_drift", False,
            f"{report.total} divergences: {report.by_type}",
            (time.time() - start) * 1000,
        )
    except Exception as e:
        return CheckResult("schema_drift", False, f"error: {e}", (time.time() - start) * 1000)


def _check_runtime_started(base_url: str) -> tuple[CheckResult, dict]:
    """GET /api/runtime/status returns 200 with started=true. Returns (result, body)."""
    start = time.time()
    status_code, body, text = _http_request("GET", f"{base_url}/api/runtime/status")
    if status_code != 200:
        return CheckResult(
            "runtime_started", False,
            f"GET /api/runtime/status returned {status_code}: {text[:200]}",
            (time.time() - start) * 1000,
        ), body
    if not body.get("started"):
        return CheckResult(
            "runtime_started", False,
            f"started=false (body: {json.dumps(body)[:200]})",
            (time.time() - start) * 1000,
        ), body
    return CheckResult(
        "runtime_started", True,
        f"started=true (providers: {list(body.get('providers', {}).keys())})",
        (time.time() - start) * 1000,
    ), body


def _check_registry_sync(status_body: dict) -> CheckResult:
    """registry_sync.last_status == 'success' from /api/runtime/status response."""
    start = time.time()
    sync = status_body.get("registry_sync")
    if not sync:
        return CheckResult(
            "registry_sync", False,
            "registry_sync field missing from /api/runtime/status",
            (time.time() - start) * 1000,
        )
    last_status = sync.get("last_status")
    if last_status == "success":
        return CheckResult(
            "registry_sync", True,
            f"last_status=success, agents_created={sync.get('agents_created', 0)}",
            (time.time() - start) * 1000,
        )
    return CheckResult(
        "registry_sync", False,
        f"last_status={last_status}, error={sync.get('last_error')}",
        (time.time() - start) * 1000,
    )


def _check_agents_installed() -> CheckResult:
    """agents table has >= 1 row."""
    start = time.time()
    try:
        from sqlalchemy import create_engine, text
        from app.config import settings
        db_url = settings.DATABASE_URL.replace("+aiosqlite", "")
        engine = create_engine(db_url)
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM agents")).scalar()
        engine.dispose()
        if count is None or count < 1:
            return CheckResult(
                "agents_installed", False,
                f"agents table has {count} rows (expected >= 1)",
                (time.time() - start) * 1000,
            )
        return CheckResult(
            "agents_installed", True,
            f"{count} agents in DB",
            (time.time() - start) * 1000,
        )
    except Exception as e:
        return CheckResult("agents_installed", False, f"error: {e}", (time.time() - start) * 1000)


def _check_auth_register(base_url: str) -> tuple[CheckResult, str, str]:
    """POST /api/auth/register returns 201. Returns (result, username, password)."""
    start = time.time()
    username = f"healthcheck_{uuid.uuid4().hex[:8]}"
    password = "Healthcheck123!"
    body = {
        "username": username,
        "email": f"{username}@example.com",
        "password": password,
        "full_name": "Health Check",
        "role": "coder",
        # org name must be unique per register call — the backend auto-creates
        # an org from full_name if organization_name is omitted, which collides
        # on re-runs (organizations.name has a UNIQUE constraint).
        "organization_name": f"Healthcheck Org {uuid.uuid4().hex[:6]}",
    }
    status_code, resp_body, text = _http_request("POST", f"{base_url}/api/auth/register", body=body)
    if status_code == 201:
        return CheckResult(
            "auth_register", True,
            f"registered {username}",
            (time.time() - start) * 1000,
        ), username, password
    return CheckResult(
        "auth_register", False,
        f"POST /api/auth/register returned {status_code}: {text[:200]}",
        (time.time() - start) * 1000,
    ), username, password


def _check_auth_login(base_url: str, username: str, password: str) -> CheckResult:
    """POST /api/auth/login returns 200."""
    start = time.time()
    body = {"username": username, "password": password}
    status_code, resp_body, text = _http_request("POST", f"{base_url}/api/auth/login", body=body)
    if status_code == 200:
        return CheckResult(
            "auth_login", True,
            f"logged in {username}",
            (time.time() - start) * 1000,
        )
    return CheckResult(
        "auth_login", False,
        f"POST /api/auth/login returned {status_code}: {text[:200]}",
        (time.time() - start) * 1000,
    )


def run_health_checks(base_url: str) -> HealthReport:
    report = HealthReport()
    # 1. alembic_head (no HTTP needed)
    report.results.append(_check_alembic_head())
    # 2. schema_drift (no HTTP needed)
    report.results.append(_check_schema_drift())
    # 3. agents_installed (no HTTP needed)
    report.results.append(_check_agents_installed())
    # 4. runtime_started (HTTP) — also captures the body for registry_sync check
    runtime_result, status_body = _check_runtime_started(base_url)
    report.results.append(runtime_result)
    # 5. registry_sync (parsed from runtime status body)
    if status_body:
        report.results.append(_check_registry_sync(status_body))
    else:
        report.results.append(CheckResult("registry_sync", False, "no /api/runtime/status body to inspect"))
    # 6. auth_register
    register_result, username, password = _check_auth_register(base_url)
    report.results.append(register_result)
    # 7. auth_login (only if register passed, so we have valid creds)
    if register_result.passed:
        report.results.append(_check_auth_login(base_url, username, password))
    else:
        report.results.append(CheckResult("auth_login", False, "skipped — register failed"))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="iCoDer backend health check")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    report = run_health_checks(args.base_url)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        for r in report.results:
            tag = "[PASS]" if r.passed else "[FAIL]"
            print(f"  {tag} {r.name:20s} ({r.duration_ms:.0f}ms)  {r.detail}")
        print()
        print(f"VERDICT: {report.verdict}  ({report.passed_count}/{len(report.results)} passed)")

    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
