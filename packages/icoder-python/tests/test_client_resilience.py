from concurrent.futures import ThreadPoolExecutor
import threading

import httpx
import pytest

from icoder_sdk import iCoDerAuthenticationError, iCoDerClient, iCoDerConfig


def configured_client(config: iCoDerConfig, handler) -> iCoDerClient:
    client = iCoDerClient(config)
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        timeout=config.timeout,
        transport=httpx.MockTransport(handler),
    )
    return client


def test_client_credentials_are_automatic_and_coalesced_across_threads():
    lock = threading.Lock()
    counts = {"token": 0, "api": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        with lock:
            if request.url.path == "/api/oauth/token":
                counts["token"] += 1
                return httpx.Response(
                    200,
                    json={"access_token": "managed-token", "expires_in": 300},
                )
            counts["api"] += 1
        assert request.headers["Authorization"] == "Bearer managed-token"
        return httpx.Response(200, json={"ok": True})

    client = configured_client(
        iCoDerConfig(
            base_url="https://api.cn.icoder.test",
            client_id="client-id",
            client_secret="client-secret",
            max_retries=0,
        ),
        handler,
    )
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda _: client.get("/api/health"), range(8)))
        assert all(response.status_code == 200 for response in responses)
        assert counts == {"token": 1, "api": 8}
        assert client.config.access_token == "managed-token"
    finally:
        client.close()


def test_concurrent_401_responses_share_one_client_credentials_refresh():
    lock = threading.Lock()
    token_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/api/oauth/token":
            with lock:
                token_calls += 1
                token = f"managed-token-{token_calls}"
            return httpx.Response(200, json={"access_token": token, "expires_in": 300})
        if request.headers["Authorization"] == "Bearer managed-token-1":
            return httpx.Response(401)
        assert request.headers["Authorization"] == "Bearer managed-token-2"
        return httpx.Response(200, json={"ok": True})

    client = configured_client(
        iCoDerConfig(
            base_url="https://api.cn.icoder.test",
            client_id="client-id",
            client_secret="client-secret",
            max_retries=0,
        ),
        handler,
    )
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: client.get("/api/protected"), range(6)))
        assert all(response.status_code == 200 for response in responses)
        assert token_calls == 2
    finally:
        client.close()


def test_retries_are_bounded_and_unsafe_requests_require_idempotency_key():
    counts = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        counts[key] = counts.get(key, 0) + 1
        if request.url.path == "/safe" and counts[key] < 3:
            return httpx.Response(429, headers={"Retry-After": "60"})
        if request.url.path == "/unsafe":
            return httpx.Response(503)
        if request.url.path == "/idempotent" and counts[key] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = configured_client(
        iCoDerConfig(
            base_url="https://api.cn.icoder.test",
            access_token="fixed-token",
            max_retries=2,
            retry_initial_delay=0,
            retry_max_delay=0,
        ),
        handler,
    )
    try:
        assert client.get("/safe").status_code == 200
        assert client.post("/unsafe", json={"value": 1}).status_code == 503
        assert counts[("GET", "/safe")] == 3
        assert counts[("POST", "/unsafe")] == 1
        assert client.post(
            "/idempotent",
            json={"value": 1},
            headers={"Idempotency-Key": "request-1"},
        ).status_code == 200
        assert counts[("POST", "/idempotent")] == 2
    finally:
        client.close()


def test_authentication_errors_are_typed_and_do_not_retain_client_secrets():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, headers={"x-request-id": "req-1"})

    client = configured_client(
        iCoDerConfig(
            base_url="https://api.cn.icoder.test",
            client_id="client-id",
            client_secret="never-print-this-secret",
            max_retries=0,
        ),
        handler,
    )
    try:
        with pytest.raises(iCoDerAuthenticationError) as captured:
            client.get("/api/protected")
        assert captured.value.status_code == 401
        assert captured.value.request_id == "req-1"
        assert "never-print-this-secret" not in str(captured.value)
        assert not hasattr(captured.value, "request")
    finally:
        client.close()
