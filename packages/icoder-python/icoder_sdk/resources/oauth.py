"""OAuth resource."""

from ..client import iCoDerClient


class OAuthResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def get_token(self, client_id: str, client_secret: str) -> dict:
        resp = self._client.post("/api/oauth/token", json={
            "client_id": client_id, "client_secret": client_secret,
            "grant_type": "client_credentials",
        })
        resp.raise_for_status()
        return resp.json()

    def create_client(self, name: str, description: str, scopes: str) -> dict:
        resp = self._client.post("/api/oauth/clients", json={
            "name": name, "description": description, "scopes": scopes,
        })
        resp.raise_for_status()
        return resp.json()

    def list_clients(self) -> dict:
        resp = self._client.get("/api/oauth/clients")
        resp.raise_for_status()
        return resp.json()

    def revoke_client(self, client_id: str) -> None:
        resp = self._client.delete(f"/api/oauth/clients/{client_id}")
        resp.raise_for_status()
