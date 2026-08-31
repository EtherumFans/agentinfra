import httpx
import pytest

from icoder_sdk import (
    BadGatewayError,
    BadRequestError,
    ConflictError,
    CursorPager,
    ForbiddenError,
    GatewayTimeoutError,
    InternalServerError,
    NotFoundError,
    UnauthorizedError,
    UnprocessableEntityError,
    iCoDerClient,
    iCoDerConfig,
)
from icoder_sdk.resources.a2a import A2AProtocolError


def configured_client(handler, *, max_retries: int = 0) -> iCoDerClient:
    config = iCoDerConfig(
        base_url="https://api.cn.icoder.test",
        access_token="fixed-token",
        max_retries=max_retries,
        retry_initial_delay=0,
        retry_max_delay=0,
    )
    client = iCoDerClient(config)
    client.http.close()
    client.http = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
    )
    return client


def test_http_status_families_raise_typed_phi_safe_errors():
    expected = {
        400: BadRequestError,
        401: UnauthorizedError,
        403: ForbiddenError,
        404: NotFoundError,
        409: ConflictError,
        422: UnprocessableEntityError,
        500: InternalServerError,
        502: BadGatewayError,
        504: GatewayTimeoutError,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            int(request.url.path[1:]),
            headers={"x-request-id": "req-safe-1"},
            json={
                "detail": [{
                    "loc": ["body", "clinical_text"],
                    "type": "value_error",
                    "msg": "patient Zhang San secret diagnosis",
                    "input": "patient Zhang San secret diagnosis",
                }],
                "secret": "patient Zhang San secret diagnosis",
            },
        )

    client = configured_client(handler)
    try:
        for status, error_type in expected.items():
            with pytest.raises(error_type) as captured:
                client.get(f"/{status}").raise_for_status()
            error = captured.value
            assert error.status_code == status
            assert error.request_id == "req-safe-1"
            assert error.details == [{
                "location": ["body", "clinical_text"],
                "type": "value_error",
            }]
            assert "Zhang San" not in repr(error.__dict__)
            assert not hasattr(error, "request")
            assert not hasattr(error, "response")
    finally:
        client.close()


def test_http_408_uses_the_bounded_retry_policy():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(408 if calls == 1 else 200, json={"ok": True})

    client = configured_client(handler, max_retries=1)
    try:
        assert client.get("/timeout").status_code == 200
        assert calls == 2
    finally:
        client.close()


def test_agentic_cursor_resources_expose_lazy_iteration():
    tokens = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pageToken")
        tokens.append(token)
        if token:
            return httpx.Response(200, json={
                "contexts": [{"id": "context-2"}],
                "nextPageToken": None,
                "totalSize": 2,
            })
        return httpx.Response(200, json={
            "contexts": [{"id": "context-1"}],
            "nextPageToken": "cursor-2",
            "totalSize": 2,
        })

    client = configured_client(handler)
    try:
        pager = client.a2a.iterate_contexts_v2(page_size=1)
        assert tokens == []
        assert [context["id"] for context in pager] == ["context-1", "context-2"]
        assert tokens == [None, "cursor-2"]
    finally:
        client.close()


def test_cursor_pager_rejects_repeated_tokens_and_page_ceiling():
    repeated = CursorPager(
        lambda _token: {"items": [1], "next": "same"},
        lambda page: page["items"],
        lambda page: page["next"],
        initial_page_token="same",
    )
    with pytest.raises(RuntimeError, match="repeated page token"):
        list(repeated)

    unbounded = CursorPager(
        lambda token: {"items": [1], "next": f"{token or 'root'}-next"},
        lambda page: page["items"],
        lambda page: page["next"],
        max_pages=2,
    )
    with pytest.raises(RuntimeError, match="exceeded max_pages=2"):
        list(unbounded)


def test_a2a_protocol_mapping_remains_specialized_and_phi_safe():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={
            "error": {
                "code": 404,
                "message": "patient secret text",
                "details": [{
                    "reason": "TASK_NOT_FOUND",
                    "metadata": {"patient": "secret"},
                }],
            },
        })

    client = configured_client(handler)
    try:
        with pytest.raises(A2AProtocolError) as captured:
            client.a2a.get_task_v1("agent", "missing")
        assert captured.value.a2a_error_code == "TASK_NOT_FOUND"
        assert "patient secret" not in str(captured.value)
    finally:
        client.close()
