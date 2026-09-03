import threading

import httpx
import pytest

from icoder_sdk import (
    PageNumberPager,
    RequestOptions,
    iCoDerClient,
    iCoDerConfig,
    iCoDerRequestCancelledError,
)


def configured_client(handler, *, max_retries: int = 0) -> iCoDerClient:
    client = iCoDerClient(iCoDerConfig(
        base_url="https://api.cn.icoder.test",
        access_token="fixed-token",
        max_retries=max_retries,
        retry_initial_delay=0,
        retry_max_delay=0,
    ))
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


def test_low_level_request_options_are_bounded_and_merged():
    observed = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"ok": True})

    client = configured_client(handler)
    try:
        response = client.get(
            "/api/safe-resource",
            request_options=RequestOptions(
                timeout_in_seconds=1.25,
                max_retries=0,
                headers={"X-Trace-Mode": "safe"},
                query_params={"include": "metadata"},
            ),
        )
        assert response.json() == {"ok": True}
        request = observed[0]
        assert request.headers["X-Trace-Mode"] == "safe"
        assert request.headers["Authorization"] == "Bearer fixed-token"
        assert request.url.params["include"] == "metadata"
        assert request.extensions["timeout"]["read"] == 1.25
    finally:
        client.close()


def test_per_request_retry_and_cancellation_are_effective():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 1 else 200, json={"retried": True})

    client = configured_client(handler)
    try:
        response = client.get(
            "/api/retry",
            request_options=RequestOptions(max_retries=1),
        )
        assert response.json() == {"retried": True}
        assert calls == 2

        cancelled = threading.Event()
        cancelled.set()
        with pytest.raises(iCoDerRequestCancelledError):
            client.get(
                "/api/cancelled",
                request_options=RequestOptions(cancel_event=cancelled),
            )
        assert calls == 2
    finally:
        client.close()


def test_request_options_fail_closed_on_unsafe_overrides():
    client = configured_client(lambda _request: httpx.Response(200, json={}))
    try:
        with pytest.raises(ValueError, match="absolute-path reference"):
            client.get("https://evil.example/api")
        with pytest.raises(ValueError, match="absolute-path reference"):
            client.get("/api/safe?override=true")
        with pytest.raises(ValueError, match="controlled by the SDK"):
            client.get(
                "/api/safe",
                request_options=RequestOptions(
                    headers={"Authorization": "Bearer attacker"},
                ),
            )
        with pytest.raises(ValueError, match="conflicts with a resource parameter"):
            client.billing.transactions(
                1,
                20,
                RequestOptions(query_params={"page": "99"}),
            )
        with pytest.raises(TypeError, match="headers must be a mapping"):
            client.get(
                "/api/safe",
                request_options=RequestOptions(headers=[]),  # type: ignore[arg-type]
            )
        assert not hasattr(client, "reviews")
    finally:
        client.close()


def test_billing_page_pager_is_lazy_and_bounded():
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(200, json={
            "transactions": [{"id": f"txn-{page}"}],
            "total": 2,
            "page": page,
            "page_size": 1,
        })

    client = configured_client(handler)
    try:
        pager = client.billing.iterate_transactions(
            1,
            RequestOptions(query_params={"include": "source"}),
        )
        assert pages == []
        assert [row["id"] for row in pager] == ["txn-1", "txn-2"]
        assert pages == [1, 2]
    finally:
        client.close()

    invalid_total = PageNumberPager(
        lambda _page: {"items": [1], "total": -1},
        lambda response: response["items"],
        lambda response: response["total"],
    )
    with pytest.raises(RuntimeError, match="invalid total"):
        list(invalid_total)

    endless = PageNumberPager(
        lambda _page: {"items": [1], "total": 999},
        lambda response: response["items"],
        lambda response: response["total"],
        max_pages=2,
    )
    with pytest.raises(RuntimeError, match="exceeded max_pages=2"):
        list(endless)


def test_public_expert_surface_maps_only_to_real_read_only_v1_routes():
    paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/mcp_servers"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/registry/reconcile"):
            return httpx.Response(200, json={"summary": {}})
        if request.url.path == "/api/v1/experts":
            return httpx.Response(200, json={"experts": [], "total": 0})
        return httpx.Response(200, json={"id": "expert-1", "name": "Expert"})

    client = configured_client(handler)
    try:
        client.experts.list("coding", "validator")
        client.experts.get("expert/1")
        client.experts.mcp_servers("expert/1", "oauth2.0")
        client.experts.reconcile_registry()
        assert paths == [
            "/api/v1/experts",
            "/api/v1/experts/expert/1",
            "/api/v1/experts/expert/1/mcp_servers",
            "/api/v1/experts/registry/reconcile",
        ]
        assert not hasattr(client.experts, "call")
        assert not hasattr(client.experts, "create")
        assert not hasattr(client.experts, "delete")
        assert not hasattr(client.speech_to_text, "punctuate")
    finally:
        client.close()


def test_a2a_request_options_cover_rest_stream_and_signed_download_boundaries():
    observed = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.url.path.endswith(":subscribe") or request.url.path.endswith("/events"):
            return httpx.Response(
                200,
                content=b'data: {"task": {}}\n\n',
                headers={"content-type": "text/event-stream"},
            )
        return httpx.Response(200, json={"id": "task-1", "status": {}})

    client = configured_client(handler)
    try:
        client.a2a.get_task_v1(
            "agent/1",
            "task/1",
            RequestOptions(
                timeout_in_seconds=2,
                headers={"X-Trace-Mode": "safe"},
                query_params={"projection": "summary"},
            ),
        )
        request = observed[-1]
        assert request.headers["A2A-Version"] == "1.0"
        assert request.headers["X-Trace-Mode"] == "safe"
        assert request.url.params["projection"] == "summary"
        assert request.extensions["timeout"]["read"] == 2

        events = list(client.a2a.subscribe_task_v1(
            "agent-1",
            "task-1",
            after_sequence=3,
            request_options=RequestOptions(
                max_retries=0,
                headers={"X-Trace-Mode": "safe"},
                query_params={"view": "safe"},
            ),
        ))
        assert events[0]["task"] == {}
        request = observed[-1]
        assert request.url.params["afterSequence"] == "3"
        assert request.url.params["view"] == "safe"
        assert request.headers["A2A-Version"] == "1.0"

        with pytest.raises(ValueError, match="max_retries to be 0"):
            list(client.a2a.message_stream_v1(
                "agent-1",
                "hello",
                request_options=RequestOptions(max_retries=1),
            ))
        with pytest.raises(ValueError, match="configured origin"):
            client.a2a.download_authorized_artifact_object_v2({
                "part": {
                    "url": "https://evil.example/api/v2/agentic/artifact-objects/download/grant"
                }
            })

        events = list(client.runs.stream_events(
            "run-1",
            "signed-token",
            request_options=RequestOptions(
                max_retries=0,
                headers={"X-Trace-Mode": "safe"},
                query_params={"view": "safe"},
            ),
        ))
        assert events[0]["task"] == {}
        request = observed[-1]
        assert request.url.params["token"] == "signed-token"
        assert request.url.params["view"] == "safe"
        assert request.headers["X-Trace-Mode"] == "safe"
        with pytest.raises(ValueError, match="conflicts with a resource parameter"):
            list(client.runs.stream_events(
                "run-1",
                "signed-token",
                request_options=RequestOptions(query_params={"token": "attacker"}),
            ))
    finally:
        client.close()
