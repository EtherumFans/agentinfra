"""OAuth resource."""

from typing import Optional
from urllib.parse import quote

from ..client import iCoDerClient
from ..request_options import RequestOptions


class OAuthResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def get_token(
        self,
        client_id: str,
        client_secret: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.post("/api/oauth/token", data={
            "client_id": client_id, "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "api:read api:write",
        }, request_options=request_options)
        resp.raise_for_status()
        return resp.json()

    def create_client(
        self,
        name: str,
        description: str,
        scopes: str,
        *,
        allowed_agent_ids: list[str] | None = None,
        allowed_purposes: list[str] | None = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.post("/api/oauth/clients", data={
            "name": name,
            "description": description,
            "scopes": scopes,
            "allowed_agent_ids": ",".join(allowed_agent_ids or []),
            "allowed_purposes": ",".join(allowed_purposes or []),
        }, request_options=request_options)
        resp.raise_for_status()
        return resp.json()

    def list_clients(
        self, request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            "/api/oauth/clients", request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def update_delegation(
        self,
        client_id: str,
        *,
        allowed_agent_ids: list[str],
        allowed_purposes: list[str],
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.patch(
            f"/api/clients/{quote(client_id, safe='')}/delegation",
            json={
                "allowed_agent_ids": allowed_agent_ids,
                "allowed_purposes": allowed_purposes,
            },
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def revoke_client(
        self,
        client_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        resp = self._client.delete(
            f"/api/oauth/clients/{quote(client_id, safe='')}",
            request_options=request_options,
        )
        resp.raise_for_status()
