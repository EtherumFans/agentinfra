from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.middleware import rate_limit


def _request(app: FastAPI, path: str) -> Request:
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("203.0.113.7", 12345),
        "server": ("test", 80),
        "app": app,
    })


async def _ok(_request: Request) -> Response:
    return Response(status_code=204)


@pytest.mark.asyncio
async def test_general_requests_do_not_consume_login_window(monkeypatch):
    app = FastAPI()
    monkeypatch.setattr(rate_limit, "GENERAL_LIMIT", 10)
    monkeypatch.setattr(rate_limit, "LOGIN_LIMIT", 2)

    for _ in range(8):
        response = await rate_limit.rate_limit_middleware(
            _request(app, "/api/admin/users"), _ok
        )
        assert response.status_code == 204

    for _ in range(2):
        response = await rate_limit.rate_limit_middleware(
            _request(app, "/api/auth/login"), _ok
        )
        assert response.status_code == 204

    try:
        await rate_limit.rate_limit_middleware(
            _request(app, "/api/auth/login"), _ok
        )
    except HTTPException as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("third login request should exceed the isolated login window")

    counts = app.state.rate_limiter_counts
    assert len(counts["general:203.0.113.7"]) == 8
    assert len(counts["login:203.0.113.7"]) == 2
