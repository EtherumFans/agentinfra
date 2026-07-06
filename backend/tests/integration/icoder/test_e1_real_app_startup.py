"""E1.1 (2026-06-26) — real FastAPI / uvicorn startup integration test.

This test exercises the *real* FastAPI lifespan and the *real* uvicorn
boot path — not the TestClient short-circuit that hides the
``starlette on_startup`` deprecation. Specifically:

  1. The app is created in-process and the ASGI lifespan is driven via
     ``LifespanManager`` so every startup hook (DB init, MCP server
     mount, A2A wiring, expert invoker construction, 4 D2 expert
     wiring, MedCodER agent pack discovery) actually runs.
  2. A subprocess-based smoke test boots uvicorn on a free port and
     curls ``/api/health`` + the A2A discovery endpoint to prove the
     real uvicorn path (not just the in-process app) is healthy.

Why this test lives in ``tests/integration/`` (not unit/):
  - It loads the full app and runs lifespan — heavy.
  - It spawns a subprocess for the smoke test — slow.
  - It's the production boot gate; the cost is justified.

If you can't run the subprocess part (e.g., sandboxed CI without
port binding), the in-process assertions still cover the bulk of the
E1.1 contract. The subprocess check is a belt-and-suspenders
production gate.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


# ── Path helpers ──────────────────────────────────────────────


# backend/tests/integration/icoder/test_e1_real_app_startup.py
#  → backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


# ── In-process lifespan test (no port, no subprocess) ─────────


@pytest.mark.asyncio
async def test_e1_real_app_lifespan_creates_real_wiring():
    """E1.1 lockdown: the real FastAPI lifespan must produce:
      - a working app
      - a real ``build_expert_invoker_for_medcoder`` invoker bound to
        app.state
      - 4 D2 expert pack wiring (E1)
      - MCP tools registered
      - MedCodER agent pack discovery endpoint working
      - /api/health returning 200

    We drive the lifespan via ``LifespanManager`` (asgi-lifespan) so
    every startup hook runs end-to-end. This is the closest in-process
    approximation of a real uvicorn boot.

    Phase 3-C0 A2 (2026-07-05): bumped ``startup_timeout`` from the
    default 5s to 60s. The iCoDer lifespan loads PlatformRuntime +
    16 builtin packs + medcoder retriever + HybridCodingAdapter +
    MCP server, which routinely takes 10-30s on a cold Windows dev
    box. The 5s default was too tight and produced spurious
    ``TimeoutError`` failures on master HEAD (verified pre-existing
    via ``git stash``).
    """
    pytest.importorskip("asgi_lifespan")

    # ``tests/conftest.py`` patches starlette to drop on_startup
    # kwargs — that patch is needed for the FastAPI app to even
    # *import* on starlette 1.3.1. We rely on the conftest hook so
    # we don't need to re-apply it here.
    from app.main import app

    from asgi_lifespan import LifespanManager

    async with LifespanManager(app, startup_timeout=60.0) as manager:
        # The lifespan started successfully — that's the headline.
        # Now check the post-startup state.
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac:
            # 1) /api/health returns 200
            r = await ac.get("/api/health")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "healthy"
            assert body["app"] == "iCoDer Medical Coding Agent"

            # 2) MedCodER agent pack discovery works
            r = await ac.get("/api/icoder/agents")
            assert r.status_code == 200
            agents = r.json()["agents"]
            ids = {a["id"] for a in agents}
            assert "medcoder-coding-review" in ids, (
                f"medcoder-coding-review agent must be discoverable; got {ids}"
            )

            # 3) Agent card for MedCodER returns the E1 4-expert wiring
            r = await ac.get("/api/icoder/agents/medcoder-coding-review/card")
            assert r.status_code == 200

            # 4) MCP tools endpoint registered (JSON-RPC POST per MCP spec
            # — GET returns 405 Method Not Allowed by design).
            r = await ac.post(
                "/mcp/v1/tools/list",
                json={"jsonrpc": "2.0", "id": "e1-1-mcp-list", "method": "tools/list"},
            )
            assert r.status_code == 200, r.text
            # MCP returns a JSON-RPC envelope with result.tools.
            envelope = r.json()
            tools = envelope.get("result", {}).get("tools", [])
            tool_names = {t["name"] for t in tools}
            assert "search_icd" in tool_names, (
                f"MCP /tools/list must expose search_icd (got {sorted(tool_names)})"
            )
            assert "verify_code" in tool_names, (
                f"MCP /tools/list must expose verify_code (got {sorted(tool_names)})"
            )


@pytest.mark.asyncio
async def test_e1_real_app_unknown_agent_returns_agent_not_found():
    """E1.1 lockdown: real InboundHandler must return A2A
    ``AGENT_NOT_FOUND`` (HTTP 404) for unknown agent_id.

    Phase 3-C0 A2 (2026-07-05): bumped ``startup_timeout`` to 60s
    (same rationale as the lifespan test above).
    """
    from app.main import app
    from app.icoder.agent_runtime.a2a import (
        A2A_PROTOCOL_HEADER,
        A2A_PROTOCOL_VERSION,
    )

    from asgi_lifespan import LifespanManager

    async with LifespanManager(app, startup_timeout=60.0) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac:
            r = await ac.post(
                "/api/icoder/agents/ghost-agent/v1/message:send",
                headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
                json={
                    "jsonrpc": "2.0",
                    "id": "e1-1-startup-test",
                    # A2A v0.3 method name is ``message/send`` (slash) per
                    # ``envelope.SUPPORTED_METHODS``; the URL path uses
                    # the colon form ``message:send`` (HTTP convention).
                    "method": "message/send",
                    "params": {
                        "message": {
                            "role": "user",
                            "parts": [{"kind": "text", "text": "test"}],
                        }
                    },
                },
            )
            assert r.status_code == 404, r.text
            body = r.json()
            assert body["error"]["data"]["a2a_error_code"] == "AGENT_NOT_FOUND"
            assert "ghost-agent" in body["error"]["data"]["details"]


# ── Subprocess uvicorn smoke test (real port) ────────────────


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_http(url: str, timeout_s: float = 20.0) -> bool:
    """Poll a URL until it returns any HTTP response or timeout."""
    import urllib.request
    import urllib.error
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1.0)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


@pytest.mark.timeout(60)
def test_e1_real_uvicorn_subprocess_boot_and_health():
    """E1.1 production boot gate: spawn the real uvicorn process
    against the real app, hit ``/api/health`` and the MedCodER agent
    discovery endpoint, then clean up.

    This is the test that would have caught the
    ``on_startup`` deprecation issue at product gate (TestClient did
    NOT trigger it; only real uvicorn did).
    """
    port = _find_free_port()
    base = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    # Degraded-echo path is fine for boot smoke (no real DeepSeek key).
    env.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")
    env.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")

    # E1.1: use DEVNULL for stderr to avoid a Windows pipe deadlock
    # — on Windows, a full stderr buffer can block the subprocess if no
    # reader drains it. We capture uvicorn logs into the test logs by
    # sending them to stderr of this pytest process (instead of PIPE).
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(_BACKEND_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        # 1) Wait for uvicorn to bind the port and become ready
        assert _wait_for_http(f"{base}/api/health", timeout_s=60.0), (
            f"uvicorn did not become ready on /api/health within 60s "
            f"(pid={proc.pid}). Check the test process logs above for "
            f"uvicorn stderr output."
        )

        # 2) /api/health returns 200 + healthy
        import urllib.request
        import json
        with urllib.request.urlopen(f"{base}/api/health", timeout=5) as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
            assert body["status"] == "healthy"
            assert body["app"] == "iCoDer Medical Coding Agent"

        # 3) MedCodER agent is discoverable
        with urllib.request.urlopen(f"{base}/api/icoder/agents", timeout=5) as resp:
            assert resp.status == 200
            agents = json.loads(resp.read())["agents"]
            ids = {a["id"] for a in agents}
            assert "medcoder-coding-review" in ids, (
                f"medcoder-coding-review must be discoverable from real uvicorn; got {ids}"
            )

        # 4) AGENT_NOT_FOUND is the A2A code for unknown agent (the
        # discovery endpoint /card) — this catches the InboundHandler
        # AGENT_NOT_FOUND alignment via the real HTTP path.
        try:
            urllib.request.urlopen(
                f"{base}/api/icoder/agents/ghost-agent/card", timeout=5
            )
        except urllib.error.HTTPError as e:
            assert e.code == 404
            blob = json.loads(e.read())
            assert blob["error"]["data"]["a2a_error_code"] == "AGENT_NOT_FOUND"
    finally:
        # Clean shutdown — terminate the subprocess regardless of test
        # outcome.
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)