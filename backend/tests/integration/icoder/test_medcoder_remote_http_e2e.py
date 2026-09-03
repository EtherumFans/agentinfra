"""Real TCP E2E for API -> isolated MedCodER retrieval worker."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from icoder_runtime.providers.medical_coding.remote_retriever import (
    RemoteMedCodERRetriever,
    RemoteRetrieverError,
)


BACKEND_ROOT = Path(__file__).resolve().parents[3]
TOKEN = "contract-worker-token-32-characters-minimum"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_json(url: str, *, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code in {200, 503}:
                return response.json()
            last_error = f"HTTP {response.status_code}"
        except (httpx.HTTPError, ValueError) as exc:
            last_error = type(exc).__name__
        time.sleep(0.2)
    raise AssertionError(f"service did not answer at {url}: {last_error}")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_real_api_uses_remote_worker_over_http_without_native_imports(
    tmp_path: Path,
) -> None:
    worker_port = _free_port()
    api_port = _free_port()
    worker_url = f"http://127.0.0.1:{worker_port}"
    api_url = f"http://127.0.0.1:{api_port}"
    worker_env = os.environ.copy()
    worker_env.update({
        "MEDCODER_RETRIEVER_TOKEN": TOKEN,
        "ICODER_CREDENTIAL_LLM": "",
        "LLM_PROVIDER": "mock",
        "ICODER_ALLOW_EXTERNAL_LLM": "false",
    })
    worker_log_path = tmp_path / "worker.log"
    api_log_path = tmp_path / "api.log"
    worker_log = worker_log_path.open("wb")
    api_log = api_log_path.open("wb")
    worker = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "tests.fixtures.medcoder_http_worker:app",
            "--host", "127.0.0.1", "--port", str(worker_port),
            "--log-level", "warning",
        ],
        cwd=BACKEND_ROOT,
        env=worker_env,
        stdout=worker_log,
        stderr=subprocess.STDOUT,
    )
    api: subprocess.Popen | None = None
    try:
        worker_ready = _wait_json(f"{worker_url}/readyz", timeout=20)
        assert worker_ready["ready"] is True

        # Prove the strict client contract crosses a real TCP socket before
        # booting the full API.
        diagnosis = RemoteMedCodERRetriever(
            worker_url,
            code_system="ICD-10-CN",
            token=TOKEN,
        )
        procedure = RemoteMedCodERRetriever(
            worker_url,
            code_system="ICD-9-CM-3-CN",
            token=TOKEN,
        )
        assert (await diagnosis.retrieve_async("心衰", top_k=1))[0].code == "I50.900"
        assert (await procedure.retrieve_async("胆囊切除", top_k=1))[0].code == "51.2300"
        with pytest.raises(RemoteRetrieverError, match="HTTP 401"):
            await RemoteMedCodERRetriever(
                worker_url,
                code_system="ICD-10-CN",
                token="wrong-worker-token-32-characters-minimum",
            ).retrieve_async("心衰", top_k=1)

        api_env = worker_env.copy()
        api_env.update({
            "DATABASE_URL": (
                "sqlite+aiosqlite:///" + (tmp_path / "api.db").resolve().as_posix()
            ),
            "SEED_ON_STARTUP": "0",
            "ICODER_DISABLE_AUTH_FOR_TESTS": "1",
            "ICODER_DISABLE_NATIVE_MEDCODER": "true",
            "MEDCODER_RETRIEVER_URL": worker_url,
            "MEDCODER_RETRIEVER_ALLOW_HTTP": "1",
            "MEDCODER_RETRIEVER_TIMEOUT_SECONDS": "5",
        })
        api = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", "app.main:app",
                "--host", "127.0.0.1", "--port", str(api_port),
                "--log-level", "warning",
            ],
            cwd=BACKEND_ROOT,
            env=api_env,
            stdout=api_log,
            stderr=subprocess.STDOUT,
        )
        health = _wait_json(f"{api_url}/api/health", timeout=75)
        assert health["medcoder_index_ready"] is True
        assert health["medcoder_retriever_mode"] == "remote"
        assert health["medcoder_retriever_worker_version"] == "1.0.0"
        assert health["medcoder_retriever_index_version"] == (
            "contract-fixture-2026-08"
        )

        response = httpx.post(
            f"{api_url}/mcp/v1/tools/call",
            json={
                "jsonrpc": "2.0",
                "id": "remote-worker-e2e",
                "method": "tools/call",
                "params": {
                    "name": "search_icd",
                    "arguments": {"emr_text": "心衰", "top_k": 1},
                },
            },
            timeout=15,
        )
        assert response.status_code == 200
        payload = response.json()
        assert "error" not in payload, json.dumps(payload, ensure_ascii=False)
        assert "I50.900" in response.text
        assert "lexical_catalog_fallback" not in response.text
    except Exception:
        worker_log.flush()
        api_log.flush()
        diagnostics = {
            "worker_exit": worker.poll(),
            "api_exit": api.poll() if api else None,
            "worker_log": worker_log_path.read_text(encoding="utf-8", errors="replace")[-4000:],
            "api_log": api_log_path.read_text(encoding="utf-8", errors="replace")[-6000:],
        }
        pytest.fail(json.dumps(diagnostics, ensure_ascii=False, indent=2), pytrace=True)
    finally:
        if api is not None:
            _stop(api)
        _stop(worker)
        worker_log.close()
        api_log.close()
