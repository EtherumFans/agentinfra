"""Legacy runtime lifecycle and observability resources backed by real routes."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from ..client import iCoDerClient
from ..request_options import RequestOptions


RuntimeLifecycleAction = Literal["enable", "disable", "uninstall", "rollback"]


def _bounded_integer(value: int, name: str, *, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise ValueError(f"{name} must be an integer between {minimum} and {maximum}")
    return value


class RuntimeResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def _json(self, method: str, path: str, *, request_options=None, **kwargs):
        response = self._client.request(
            method,
            path,
            request_options=request_options,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def status(self, request_options: RequestOptions | None = None) -> dict[str, Any]:
        return self._json("GET", "/api/runtime/status", request_options=request_options)

    def data_policy(
        self, request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "GET", "/api/runtime/data-policy", request_options=request_options,
        )

    def list_agents(
        self,
        agent_type: str = "",
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "GET",
            "/api/runtime/agents",
            params={"agent_type": agent_type},
            request_options=request_options,
        )

    def install_agent(
        self,
        name: str,
        version: str,
        agent_type: str = "community",
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            "/api/runtime/agents/install",
            json={
                "agent_name": name,
                "agent_version": version,
                "agent_type": agent_type,
            },
            request_options=request_options,
        )

    def run_agent(
        self,
        agent_ref: str,
        input_text: str,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/runtime/agents/{quote(agent_ref, safe='')}/run",
            json={"input": input_text},
            request_options=request_options,
        )

    def agent_lifecycle(
        self,
        agent_ref: str,
        action: RuntimeLifecycleAction,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        if action not in {"enable", "disable", "uninstall", "rollback"}:
            raise ValueError("action must be enable, disable, uninstall, or rollback")
        return self._json(
            "POST",
            f"/api/runtime/agents/{quote(agent_ref, safe='')}/lifecycle",
            json={"action": action},
            request_options=request_options,
        )

    def list_runs(
        self,
        agent_ref: str = "",
        limit: int = 50,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        _bounded_integer(limit, "limit", minimum=1, maximum=200)
        return self._json(
            "GET",
            "/api/runtime/runs",
            params={"agent_ref": agent_ref, "limit": limit},
            request_options=request_options,
        )

    def get_run(
        self,
        run_id: str,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "GET",
            f"/api/runtime/runs/{quote(run_id, safe='')}",
            request_options=request_options,
        )

    def fallback_stats(
        self,
        hours: int = 24,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        _bounded_integer(hours, "hours", minimum=1, maximum=168)
        return self._json(
            "GET",
            "/api/runtime/observability/fallback",
            params={"hours": hours},
            request_options=request_options,
        )

    def shadow_stats(
        self,
        hours: int = 24,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        _bounded_integer(hours, "hours", minimum=1, maximum=168)
        return self._json(
            "GET",
            "/api/runtime/observability/shadow",
            params={"hours": hours},
            request_options=request_options,
        )

    def audit_log(
        self,
        event_type: str = "",
        limit: int = 100,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        _bounded_integer(limit, "limit", minimum=1, maximum=500)
        return self._json(
            "GET",
            "/api/runtime/audit-log",
            params={"event_type": event_type, "limit": limit},
            request_options=request_options,
        )

    def medical_coding_status(
        self, request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "GET",
            "/api/runtime/medical-coding/status",
            request_options=request_options,
        )

    def test_medical_coding(
        self,
        text: str,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            "/api/runtime/medical-coding/test",
            json={"encounter_text": text},
            request_options=request_options,
        )

    def rule_engine_status(
        self, request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "GET", "/api/runtime/rule-engine/status", request_options=request_options,
        )

    def rule_engine_rules(
        self, request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "GET", "/api/runtime/rule-engine/rules", request_options=request_options,
        )

    def validate_rules(
        self,
        rule_set: str,
        output: dict[str, Any],
        context: dict[str, Any] | None = None,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            "/api/runtime/rule-engine/validate",
            json={
                "rule_set": rule_set,
                "structured_output": output,
                "context": dict(context or {}),
            },
            request_options=request_options,
        )

    def registry_health(
        self, request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "GET", "/api/runtime/registry/health", request_options=request_options,
        )

    def registry_repair(
        self,
        direction: str = "registry_to_db",
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            "/api/runtime/registry/repair",
            json={"direction": direction},
            request_options=request_options,
        )
