"""Agents & Experts resources."""

from __future__ import annotations
from typing import Any, Optional
from urllib.parse import quote

from ..client import iCoDerClient
from ..request_options import RequestOptions
from ..types import (
    A2ALegacyAgentCard,
    AgentCloneResponse,
    AgentHubResponse,
    AgentHubTenantReadinessResponse,
    validate_agent_clone_response,
    validate_agent_hub_response,
    validate_agent_hub_tenant_readiness_response,
)


class AgentsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def list(
        self,
        category: str = "",
        search: str = "",
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            "/api/rest/v1/agent_definitions",
            params={"category": category, "search": search},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def get(
        self,
        agent_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            f"/api/rest/v1/agent_definitions/{quote(agent_id, safe='')}",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def hub(
        self,
        use_case: str = "",
        request_options: Optional[RequestOptions] = None,
    ) -> AgentHubResponse:
        """List Corti-style prebuilt Agent Hub cards and typed contracts."""
        resp = self._client.get(
            "/api/icoder/agents/hub",
            params={"use_case": use_case} if use_case else None,
            request_options=request_options,
        )
        resp.raise_for_status()
        return validate_agent_hub_response(resp.json())

    def hub_readiness(
        self, request_options: Optional[RequestOptions] = None,
    ) -> AgentHubTenantReadinessResponse:
        """Get authenticated, tenant-bound configuration/connectivity proof."""
        resp = self._client.get(
            "/api/icoder/agents/hub/readiness",
            request_options=request_options,
        )
        resp.raise_for_status()
        return validate_agent_hub_tenant_readiness_response(resp.json())

    def card(
        self,
        agent_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> A2ALegacyAgentCard:
        """Get one runtime Agent Card by URL-safe Agent id."""
        resp = self._client.get(
            f"/api/icoder/agents/{quote(agent_id, safe='')}/card",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def clone(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        project_id: str | None = None,
        open_after_clone: bool = True,
        request_options: Optional[RequestOptions] = None,
    ) -> AgentCloneResponse:
        """Clone a governed Hub Agent into the active tenant project."""
        payload: dict[str, Any] = {"open_after_clone": open_after_clone}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if project_id is not None:
            payload["project_id"] = project_id
        resp = self._client.post(
            f"/api/icoder/agents/{quote(agent_id, safe='')}/clone",
            json=payload,
            request_options=request_options,
        )
        resp.raise_for_status()
        return validate_agent_clone_response(resp.json())

    def create(
        self,
        name: str,
        description: str = "",
        category: str = "",
        system_prompt: str = "",
        expert_ids: Optional[list[str]] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.post("/api/rest/v1/agent_definitions", json={
            "name": name, "description": description, "category": category,
            "system_prompt": system_prompt, "expert_ids": expert_ids or [],
        }, request_options=request_options)
        resp.raise_for_status()
        return resp.json()

    def update(
        self,
        agent_id: str,
        *,
        request_options: Optional[RequestOptions] = None,
        **kwargs,
    ) -> dict:
        resp = self._client.put(
            f"/api/rest/v1/agent_definitions/{quote(agent_id, safe='')}",
            json=kwargs,
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def delete(
        self,
        agent_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        resp = self._client.delete(
            f"/api/rest/v1/agent_definitions/{quote(agent_id, safe='')}",
            request_options=request_options,
        )
        resp.raise_for_status()

    def list_connectors(
        self,
        agent_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connectors",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def create_connector(
        self,
        agent_id: str,
        *,
        connector_type: str,
        name: str,
        config: dict[str, Any],
        description: str = "",
        enabled: bool = False,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.post(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connectors",
            json={
                "type": connector_type,
                "name": name,
                "description": description,
                "enabled": enabled,
                "config": config,
            },
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def update_connector(
        self,
        agent_id: str,
        connector_id: str,
        *,
        expected_version: int,
        request_options: Optional[RequestOptions] = None,
        **changes: Any,
    ) -> dict:
        resp = self._client.patch(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connectors/"
            f"{quote(connector_id, safe='')}",
            json={"expected_version": expected_version, **changes},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def delete_connector(
        self,
        agent_id: str,
        connector_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        resp = self._client.delete(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connectors/"
            f"{quote(connector_id, safe='')}",
            request_options=request_options,
        )
        resp.raise_for_status()

    def bind_connector_credential(
        self,
        agent_id: str,
        connector_id: str,
        *,
        provider: str,
        secret_ref: str,
        secret_type: str,
        expected_version: int | None = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "provider": provider,
            "secret_ref": secret_ref,
            "secret_type": secret_type,
        }
        if expected_version is not None:
            payload["expected_version"] = expected_version
        resp = self._client.put(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connectors/"
            f"{quote(connector_id, safe='')}/credential",
            json=payload,
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def delete_connector_credential(
        self,
        agent_id: str,
        connector_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        resp = self._client.delete(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connectors/"
            f"{quote(connector_id, safe='')}/credential",
            request_options=request_options,
        )
        resp.raise_for_status()

    def connector_graph(
        self,
        agent_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connector-graph",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def put_connector_graph(
        self,
        agent_id: str,
        *,
        expected_revision: int,
        enabled: bool,
        nodes: list[dict[str, Any]],
        execution_mode: str = "sequential",
        max_concurrency: int = 4,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        if execution_mode not in {"sequential", "parallel"}:
            raise ValueError("execution_mode must be sequential or parallel")
        if max_concurrency < 1 or max_concurrency > 8:
            raise ValueError("max_concurrency must be between 1 and 8")
        resp = self._client.put(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connector-graph",
            json={
                "version": "1.0",
                "enabled": enabled,
                "execution_mode": execution_mode,
                "max_concurrency": max_concurrency,
                "nodes": nodes,
                "expected_revision": expected_revision,
            },
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def delete_connector_graph(
        self,
        agent_id: str,
        *,
        expected_revision: int,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        resp = self._client.delete(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/connector-graph",
            params={"expected_revision": expected_revision},
            request_options=request_options,
        )
        resp.raise_for_status()

    def grant_memory_consent(
        self,
        agent_id: str,
        *,
        acknowledgement: bool,
        purpose_of_use: str = "treatment",
        retention_days: int = 30,
        expires_in_days: int = 30,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        if acknowledgement is not True:
            raise ValueError("memory consent requires explicit acknowledgement=True")
        resp = self._client.post(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/memory-consent",
            json={
                "purpose_of_use": purpose_of_use,
                "retention_days": retention_days,
                "expires_in_days": expires_in_days,
                "acknowledgement": True,
            },
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def memory_consent(
        self,
        agent_id: str,
        *,
        purpose_of_use: str = "treatment",
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/memory-consent",
            params={"purpose_of_use": purpose_of_use},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def memory_readiness(
        self,
        agent_id: str,
        *,
        purpose_of_use: str = "treatment",
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/memory-readiness",
            params={"purpose_of_use": purpose_of_use},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def revoke_memory_consent(
        self,
        agent_id: str,
        *,
        purpose_of_use: str = "treatment",
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        resp = self._client.delete(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/memory-consent",
            params={"purpose_of_use": purpose_of_use},
            request_options=request_options,
        )
        resp.raise_for_status()

    def run(
        self,
        agent_id: str,
        input_text: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        return self._client.a2a.message_send(
            agent_id,
            input_text,
            request_options=request_options,
        )

    def stream(
        self,
        agent_id: str,
        input_text: str,
        request_options: Optional[RequestOptions] = None,
    ):
        """Stream authenticated A2A SSE payloads from the runtime Agent."""
        yield from self._client.a2a.message_stream(
            agent_id,
            input_text,
            request_options=request_options,
        )

    def templates(
        self, request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            "/api/rest/v1/agent_definitions/templates",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()


class ExpertsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def list(
        self,
        category: str = "",
        search: str = "",
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            "/api/v1/experts",
            params={"category": category or None, "search": search or None},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def get(
        self,
        expert_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            f"/api/v1/experts/{quote(expert_id, safe='')}",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def mcp_servers(
        self,
        expert_id: str,
        authorization_type: str = "",
        request_options: Optional[RequestOptions] = None,
    ) -> list[dict]:
        resp = self._client.get(
            f"/api/v1/experts/{quote(expert_id, safe='')}/mcp_servers",
            params={"authorization_type": authorization_type or None},
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def reconcile_registry(
        self,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            "/api/v1/experts/registry/reconcile",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()

    def readiness(
        self,
        request_options: Optional[RequestOptions] = None,
    ) -> dict:
        resp = self._client.get(
            "/api/v1/experts/readiness",
            request_options=request_options,
        )
        resp.raise_for_status()
        return resp.json()
