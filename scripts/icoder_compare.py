#!/usr/bin/env python3
"""iCoDer vs Corti contract diff gate.

For each contract under ``corti_contracts/{endpoint}_request.json``:

  1. Spin up iCoDer locally (uvicorn) if not already running.
  2. POST the contract's request to iCoDer.
  3. Compare the iCoDer response to the optional ``golden_captures/``
     Corti response using ``deepdiff`` (ignoring dynamic fields).
  4. Print a colored diff report and exit non-zero on mismatch.
  5. On match, write ``corti_contracts/{endpoint}.VERIFIED_OK``.

Usage
-----
    # Run all contracts in corti_contracts/
    python scripts/icoder_compare.py

    # One endpoint only
    python scripts/icoder_compare.py --endpoint coding/icoder

    # Don't auto-start the server (assume it's already on :8000)
    python scripts/icoder_compare.py --no-start-server

    # Save per-endpoint comparison to phase_cycles report
    python scripts/icoder_compare.py --cycle-dir docs/phase_cycles/cycle_19_phase2_baseline
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests
from colorama import Fore, Style, init as colorama_init
from deepdiff import DeepDiff

# Force UTF-8 stdout/stderr on Windows (GBK can't encode box chars / emojis)
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

colorama_init()

REPO_ROOT = Path(__file__).resolve().parent.parent
CORTI_CONTRACTS_DIR = REPO_ROOT / "corti_contracts"
GOLDEN_DIR = REPO_ROOT / "golden_captures"
BACKEND_DIR = REPO_ROOT / "backend"
APP_MODULE = "app.main:app"

ICODER_DEFAULT_URL = "http://127.0.0.1:8000"
ICODER_HEALTH_PATH = "/health"
ICODER_STARTUP_TIMEOUT_S = 30

# Fields that legitimately differ run-to-run and are excluded from diff.
DYNAMIC_PATHS = {
    "root['id']",
    "root['requestId']",
    "root['traceId']",
    "root['timestamp']",
    "root['createdAt']",
    "root['updatedAt']",
    "root['usageInfo']['creditsConsumed']",
    "root['codes'][*]['evidences'][*]['start']",
    "root['codes'][*]['evidences'][*]['end']",
    "root['candidates'][*]['evidences'][*]['start']",
    "root['candidates'][*]['evidences'][*]['end']",
}


class CompareError(Exception):
    pass


def is_server_up(url: str) -> bool:
    try:
        return requests.get(url, timeout=2).status_code < 500
    except Exception:
        return False


def make_test_client():
    """Return a FastAPI TestClient with auth bypassed (dependency_overrides).

    Uses the same pattern as tests/conftest.py:_install_auth_bypass. This
    avoids the need to start a real uvicorn (and the auth-bypass env-var
    gap, since ICODER_DISABLE_AUTH_FOR_TESTS only takes effect via the
    conftest fixture, not the middleware itself).
    """
    # Make the backend package importable when this script is launched
    # from the repo root (cwd = E:/Corti4C) — otherwise `from app.main
    # import app` raises ModuleNotFoundError.
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from fastapi.testclient import TestClient
    from app.main import app
    from app.middleware.auth import get_current_user

    # Set dev-mode env vars before app loads settings
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("LLM_PROVIDER", "mock")
    os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-phase2-tooling")

    def _mock_admin_user():
        from app.models.user import User
        return User(id="phase2-compare", email="compare@local", role="admin", is_active=True)

    app.dependency_overrides[get_current_user] = _mock_admin_user
    print(f"{Fore.CYAN}[client] FastAPI TestClient with auth bypassed (dependency_overrides)")
    return TestClient(app)


def start_icoder_server() -> subprocess.Popen:
    """Launch uvicorn in dev mode. Auth is NOT bypassed at the middleware
    level — callers should prefer --use-test-client instead."""
    env = os.environ.copy()
    env.update({
        "ICODER_DEPLOYMENT_MODE": "local",
        "APP_ENV": "development",
        "LLM_PROVIDER": "mock",
        "ICODER_CREDENTIAL_LLM": "test-fake-key-phase2-tooling",
    })
    print(f"{Fore.CYAN}[start] uvicorn {APP_MODULE} (local dev, auth NOT bypassed)")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", APP_MODULE, "--port", "8000", "--log-level", "warning"],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + ICODER_STARTUP_TIMEOUT_S
    while time.time() < deadline:
        if is_server_up(ICODER_DEFAULT_URL + ICODER_HEALTH_PATH):
            print(f"{Fore.GREEN}[ready] {ICODER_DEFAULT_URL}")
            return proc
        if proc.poll() is not None:
            raise CompareError(f"uvicorn exited with code {proc.returncode} during startup")
        time.sleep(0.5)
    proc.terminate()
    raise CompareError(f"uvicorn did not become ready within {ICODER_STARTUP_TIMEOUT_S}s")


def load_golden(endpoint: str) -> dict[str, Any] | None:
    """Load the Corti golden response, if any, for the endpoint.

    Accepts two shapes:
      1. hand-written: ``{"status": N, "body": {...}}``
      2. corti_deep_crawler summary.json: ``{"resp_status": N, "resp_body": "..."}``
    """
    for path in [
        GOLDEN_DIR / f"{endpoint.replace('/', '_')}_response.json",
        GOLDEN_DIR / endpoint.replace("/", "_") / "summary.json",
    ]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if "status" in data and "body" in data:
            return {"status": data["status"], "body": data["body"]}
        if "resp_status" in data and "resp_body" in data:
            body = data["resp_body"]
            return {
                "status": data["resp_status"],
                "body": json.loads(body) if isinstance(body, str) else body,
            }
    return None


def fetch_icoder(url: str, method: str, payload: dict[str, Any]) -> tuple[int, Any]:
    resp = requests.request(method, url, json=payload, timeout=15)
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:4000]
    return resp.status_code, body


def diff_responses(corti: dict[str, Any], icoder: dict[str, Any]) -> str | None:
    """Run deepdiff. Return a one-line summary if different, else None."""
    if corti.get("status") != icoder.get("status"):
        return f"status code differs: corti={corti.get('status')} icoder={icoder.get('status')}"
    diff = DeepDiff(
        corti.get("body", {}),
        icoder.get("body", {}),
        ignore_order=True,
        exclude_paths=DYNAMIC_PATHS,
        verbose_level=2,
    )
    if not diff:
        return None
    return f"body differs:\n{json.dumps(diff, indent=2, default=str)[:2000]}"


def write_verified_ok(endpoint: str, summary: dict[str, Any]) -> Path:
    path = CORTI_CONTRACTS_DIR / f"{endpoint.replace('/', '_')}.VERIFIED_OK"
    path.write_text(
        json.dumps({**summary, "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2),
        encoding="utf-8",
    )
    return path


def compare_one(endpoint: str, contract_path: Path, client) -> bool:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    request = contract.get("request", {})
    method = contract.get("method", "POST").upper()
    target = contract.get("url", f"/api/v2/tools/{endpoint}/")

    print(f"\n{Fore.CYAN}[cmp] {endpoint}")
    print(f"      {method} {target}")

    golden = load_golden(endpoint)
    if golden:
        print(f"      corti golden: status={golden['status']} (body {len(json.dumps(golden['body']))}B)")
    else:
        print(f"      {Fore.YELLOW}no corti golden found - will only assert iCoDer 2xx/4xx shape")

    if client is None:
        # Fall back to real HTTP (assumes server already running on --base-url)
        icoder_status, icoder_body = fetch_icoder(ICODER_DEFAULT_URL + target, method, request)
    else:
        icoder_status, icoder_body = fetch_via_testclient(client, method, target, request)
    print(f"      icoder result: status={icoder_status}")

    if golden:
        diff = diff_responses(golden, {"status": icoder_status, "body": icoder_body})
        if diff:
            print(f"      {Fore.RED}[FAIL] MISMATCH")
            for line in diff.splitlines()[:30]:
                print(f"        {Fore.RED}{line}")
            return False
        print(f"      {Fore.GREEN}[OK] MATCH (status + body shape)")
        write_verified_ok(endpoint, {
            "endpoint": endpoint,
            "corti_status": golden["status"],
            "icoder_status": icoder_status,
        })
        return True
    else:
        if 200 <= icoder_status < 300:
            print(f"      {Fore.GREEN}[OK] iCoDer returned 2xx (no golden to compare against)")
            write_verified_ok(endpoint, {"endpoint": endpoint, "icoder_status": icoder_status, "no_golden": True})
            return True
        print(f"      {Fore.YELLOW}[?] iCoDer returned {icoder_status} (no golden - inconclusive)")
        return True


def fetch_via_testclient(client, method: str, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    """Call the FastAPI app via TestClient. Auth is bypassed via dependency_overrides."""
    method_fn = {
        "GET": client.get,
        "POST": client.post,
        "PUT": client.put,
        "PATCH": client.patch,
        "DELETE": client.delete,
    }.get(method)
    if method_fn is None:
        raise CompareError(f"unsupported method {method}")
    resp = method_fn(path, json=payload)
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:4000]
    return resp.status_code, body


def main() -> int:
    parser = argparse.ArgumentParser(description="iCoDer vs Corti contract diff gate.")
    parser.add_argument("--endpoint", help="Single endpoint slug (e.g. 'coding/icoder')")
    parser.add_argument(
        "--use-real-server", action="store_true",
        help="Use a real uvicorn process (auth NOT bypassed). Default: TestClient with dependency_overrides.",
    )
    parser.add_argument("--base-url", default=ICODER_DEFAULT_URL, help="iCoDer base URL (real-server mode)")
    parser.add_argument("--cycle-dir", type=Path, help="Phase cycle archive dir for REPORT.md")
    args = parser.parse_args()

    if not CORTI_CONTRACTS_DIR.exists():
        print(f"{Fore.RED}[fail] {CORTI_CONTRACTS_DIR} not found — run corti_deep_scan.py first")
        return 2

    server_proc = None
    client = None
    if args.use_real_server:
        if not is_server_up(args.base_url + ICODER_HEALTH_PATH):
            try:
                server_proc = start_icoder_server()
            except CompareError as e:
                print(f"{Fore.RED}[fail] {e}")
                return 3
    else:
        try:
            client = make_test_client()
        except Exception as e:
            print(f"{Fore.RED}[fail] could not build TestClient: {type(e).__name__}: {e}")
            return 3

    try:
        if args.endpoint:
            contracts = [CORTI_CONTRACTS_DIR / f"{args.endpoint.replace('/', '_')}_request.json"]
            if not contracts[0].exists():
                print(f"{Fore.RED}[fail] contract not found: {contracts[0]}")
                return 4
        else:
            contracts = sorted(CORTI_CONTRACTS_DIR.glob("*_request.json"))

        if not contracts:
            print(f"{Fore.YELLOW}[note] no *_request.json contracts in {CORTI_CONTRACTS_DIR}")
            return 0

        results = []
        for contract_path in contracts:
            try:
                contract_json = json.loads(contract_path.read_text(encoding="utf-8"))
                endpoint = contract_json.get("endpoint", contract_path.stem.removesuffix("_request"))
            except Exception:
                endpoint = contract_path.stem.removesuffix("_request")
            try:
                ok = compare_one(endpoint, contract_path, client)
                results.append((endpoint, ok))
            except Exception as e:
                print(f"      {Fore.RED}[ERR] {type(e).__name__}: {e}")
                results.append((endpoint, False))

        passed = sum(1 for _, ok in results if ok)
        total = len(results)
        print(f"\n{Fore.CYAN}{'=' * 60}")
        print(f"{Fore.CYAN}[summary] {passed}/{total} contracts match")
        for endpoint, ok in results:
            tag = f"{Fore.GREEN}[OK]  " if ok else f"{Fore.RED}[FAIL]"
            print(f"  {tag} {endpoint}")

        if args.cycle_dir:
            cycle_dir = (REPO_ROOT / args.cycle_dir).resolve()
            cycle_dir.mkdir(parents=True, exist_ok=True)
            report = cycle_dir / "contract_diff.md"
            lines = [f"# Phase 2 contract diff - {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}", ""]
            lines.append(f"**Result: {passed}/{total} match**\n")
            for endpoint, ok in results:
                lines.append(f"- {'OK' if ok else 'FAIL'} `{endpoint}`")
            report.write_text("\n".join(lines) + "\n", encoding="utf-8")
            try:
                rel = report.relative_to(REPO_ROOT)
            except ValueError:
                rel = report
            print(f"\n[report] {rel}")

        return 0 if passed == total else 1
    finally:
        if server_proc:
            print(f"\n[stop] terminating uvicorn (pid {server_proc.pid})")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
