from __future__ import annotations

import httpx2
from starlette import testclient


def test_starlette_testclient_uses_pinned_httpx2_backend() -> None:
    assert httpx2.__version__ == "2.12.0"
    assert testclient.httpx is httpx2
