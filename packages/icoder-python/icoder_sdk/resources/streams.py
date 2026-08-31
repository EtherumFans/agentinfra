"""Corti-compatible Streams resource."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from ..client import iCoDerClient
from ..managed_streams_session import ManagedStreamsSession, ManagedStreamsSessionError


class StreamsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    async def connect_async(
        self,
        *,
        interaction_id: str,
        tenant_name: str,
        configuration: dict[str, Any],
        environment: str = "cn",
        setup_timeout: float = 10.0,
        require_checkpoint_resume: bool = False,
    ) -> ManagedStreamsSession:
        try:
            import websockets
        except ImportError:
            raise ImportError("websockets library required. Install: pip install websockets") from None
        if environment not in {"cn", "eu", "us"}:
            raise ValueError("environment must be cn, eu, or us")
        token = self._client.ensure_access_token()
        if not token:
            raise ManagedStreamsSessionError("missing_access_token")
        websocket_base = self._client.base_url.replace("http://", "ws://").replace(
            "https://", "wss://"
        )

        def url_factory() -> str:
            current = self._client.config.access_token or ""
            query = urlencode({
                "environment": environment,
                "tenant-name": tenant_name,
                "token": current,
            })
            return (
                f"{websocket_base}/api/v2/tools/streams/"
                f"{quote(interaction_id, safe='')}?{query}"
            )

        session = ManagedStreamsSession(
            websockets.connect,
            url_factory,
            configuration=configuration,
            setup_timeout=setup_timeout,
            require_checkpoint_resume=require_checkpoint_resume,
        )
        return await session.connect()

    async def resume_async(
        self,
        *,
        interaction_id: str,
        tenant_name: str,
        configuration: dict[str, Any],
        environment: str = "cn",
        setup_timeout: float = 10.0,
    ) -> ManagedStreamsSession:
        if configuration.get("retentionPolicy") != "retain":
            raise ManagedStreamsSessionError("stream_resume_requires_retention")
        return await self.connect_async(
            interaction_id=interaction_id,
            tenant_name=tenant_name,
            configuration=configuration,
            environment=environment,
            setup_timeout=setup_timeout,
            require_checkpoint_resume=True,
        )
