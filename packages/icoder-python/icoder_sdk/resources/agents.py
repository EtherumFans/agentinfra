"""Agents & Experts resources."""

from __future__ import annotations
from ..client import iCoDerClient


class AgentsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def list(self, category: str = "", search: str = "") -> dict:
        resp = self._client.get("/api/agents", params={"category": category, "search": search})
        resp.raise_for_status()
        return resp.json()

    def get(self, agent_id: str) -> dict:
        resp = self._client.get(f"/api/agents/{agent_id}")
        resp.raise_for_status()
        return resp.json()

    def create(self, name: str, description: str = "", category: str = "",
               system_prompt: str = "", expert_ids: list[str] | None = None) -> dict:
        resp = self._client.post("/api/agents", json={
            "name": name, "description": description, "category": category,
            "system_prompt": system_prompt, "expert_ids": expert_ids or [],
        })
        resp.raise_for_status()
        return resp.json()

    def update(self, agent_id: str, **kwargs) -> dict:
        resp = self._client.put(f"/api/agents/{agent_id}", json=kwargs)
        resp.raise_for_status()
        return resp.json()

    def delete(self, agent_id: str) -> None:
        resp = self._client.delete(f"/api/agents/{agent_id}")
        resp.raise_for_status()

    def run(self, agent_id: str, input_text: str) -> dict:
        resp = self._client.post(f"/api/agents/{agent_id}/run", json={"input": input_text})
        resp.raise_for_status()
        return resp.json()

    def stream(self, agent_id: str, input_text: str):
        """Stream agent response via SSE. Yields text chunks."""
        import httpx
        with httpx.stream(
            "POST",
            f"{self._client.base_url}/api/agents/{agent_id}/stream",
            json={"input": input_text},
            headers=self._client.http.headers,
            timeout=self._client.config.timeout,
        ) as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    yield line[6:]

    def templates(self) -> dict:
        resp = self._client.get("/api/agents/templates")
        resp.raise_for_status()
        return resp.json()


class ExpertsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def list(self, category: str = "", search: str = "") -> dict:
        resp = self._client.get("/api/experts", params={"category": category, "search": search})
        resp.raise_for_status()
        return resp.json()

    def call(self, name: str, input_text: str) -> dict:
        from urllib.parse import quote
        resp = self._client.post(
            f"/api/experts/call/{quote(name)}?input={quote(input_text)}"
        )
        resp.raise_for_status()
        return resp.json()

    def create(self, name: str, category: str, description: str = "") -> dict:
        resp = self._client.post("/api/experts", json={
            "name": name, "category": category, "description": description,
        })
        resp.raise_for_status()
        return resp.json()

    def delete(self, expert_id: str) -> None:
        resp = self._client.delete(f"/api/experts/{expert_id}")
        resp.raise_for_status()
