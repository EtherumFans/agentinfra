"""Project Agent lifecycle: management, run gates, A2A, and audit evidence."""
from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select


def _a2a_message(text: str = "de-identified test input") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "lifecycle-test-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
                "messageId": "lifecycle-client-message-1",
                "metadata": {},
            }
        },
    }


def _audit_actions(agent_id: str) -> list[tuple[str, dict]]:
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog

    async def _read() -> list[tuple[str, dict]]:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.organization_id == "org_default1",
                        AuditLog.resource_type == "agent",
                        AuditLog.resource_id == agent_id,
                    )
                    .order_by(AuditLog.created_at.asc())
                )
            ).scalars().all()
            return [(row.action, row.details or {}) for row in rows]

    return asyncio.run(_read())


def test_project_agent_lifecycle_is_explicit_audited_and_fail_closed() -> None:
    from app.icoder.agent_runtime.a2a import (
        A2A_PROTOCOL_HEADER,
        A2A_PROTOCOL_VERSION,
    )
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/rest/v1/agent_definitions",
            json={
                "name": "Lifecycle contract test Agent",
                "description": "Synthetic lifecycle test only",
                "system_prompt": "Return a concise synthetic response.",
                "expert_ids": [],
                "a2a_enabled": True,
            },
        )
        assert created.status_code in (200, 201), created.text
        agent = created.json()
        agent_id = agent["id"]
        assert agent["status"] == "published"
        assert agent["is_published"] is True
        assert agent["version"] == "1.0.0"
        assert agent["lifecycle"] == {
            "state": "published",
            "effective_published": True,
            "run_action_enabled": True,
            "allowed_actions": ["archive", "version", "delete"],
            "version": "1.0.0",
        }

        direct_transition = client.put(
            f"/api/rest/v1/agent_definitions/{agent_id}",
            json={
                "status": "archived",
                "is_published": False,
                "version": "99.0.0",
            },
        )
        assert direct_transition.status_code == 422
        assert direct_transition.json()["detail"]["error"] == (
            "agent_lifecycle_endpoint_required"
        )
        assert direct_transition.json()["detail"]["fields"] == [
            "status",
            "is_published",
            "version",
        ]

        updated = client.put(
            f"/api/rest/v1/agent_definitions/{agent_id}",
            json={"description": "Synthetic lifecycle test, updated"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["version"] == "1.0.1"

        archived = client.post(
            f"/api/rest/v1/agent_definitions/{agent_id}/archive"
        )
        assert archived.status_code == 200, archived.text
        assert archived.json()["lifecycle"]["state"] == "archived"
        assert archived.json()["lifecycle"]["run_action_enabled"] is False

        immutable = client.put(
            f"/api/rest/v1/agent_definitions/{agent_id}",
            json={"name": "must not change"},
        )
        assert immutable.status_code == 409
        assert immutable.json()["detail"]["error"] == "archived_agent_immutable"

        http_run = client.post(
            f"/api/v1/agents/{agent_id}/run",
            json={"input": {"text": "de-identified test input"}},
        )
        assert http_run.status_code == 200, http_run.text
        assert http_run.json()["error"] is True
        assert http_run.json()["error_reason"] == "agent_not_published"

        a2a_run = client.post(
            f"/api/icoder/agents/{agent_id}/v1/message:send",
            headers={A2A_PROTOCOL_HEADER: A2A_PROTOCOL_VERSION},
            json=_a2a_message(),
        )
        assert a2a_run.status_code == 422, a2a_run.text
        assert "AGENT_NOT_PUBLISHED" in a2a_run.text

        restored = client.post(
            f"/api/rest/v1/agent_definitions/{agent_id}/restore"
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["lifecycle"]["state"] == "published"
        assert restored.json()["lifecycle"]["run_action_enabled"] is True

        actions_and_details = _audit_actions(agent_id)
        actions = [action for action, _ in actions_and_details]
        assert actions == [
            "agent.lifecycle.created_published",
            "agent.lifecycle.updated",
            "agent.lifecycle.archived",
            "agent.lifecycle.restored",
        ]
        update_details = dict(actions_and_details)["agent.lifecycle.updated"]
        assert update_details["changed_fields"] == ["description"]
        assert update_details["previous_version"] == "1.0.0"
        assert update_details["version"] == "1.0.1"
        assert "system_prompt" not in update_details

        deleted = client.delete(
            f"/api/rest/v1/agent_definitions/{agent_id}"
        )
        assert deleted.status_code == 200, deleted.text
        assert _audit_actions(agent_id)[-1][0] == "agent.lifecycle.deleted"


def test_generic_template_clone_requires_publish_before_run() -> None:
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as client:
        cloned = client.post(
            "/api/rest/v1/agent_definitions/translator-blank/clone",
            json={"name": "Lifecycle draft clone test"},
        )
        assert cloned.status_code in (200, 201), cloned.text
        agent = cloned.json()
        agent_id = agent["id"]
        assert agent["lifecycle"]["state"] == "draft"
        assert agent["lifecycle"]["run_action_enabled"] is False

        invalid_archive = client.post(
            f"/api/rest/v1/agent_definitions/{agent_id}/archive"
        )
        assert invalid_archive.status_code == 409, invalid_archive.text
        assert invalid_archive.json()["detail"]["error"] == "agent_not_published"

        blocked = client.post(
            f"/api/v1/agents/{agent_id}/run",
            json={"input": {"text": "hello"}},
        )
        assert blocked.status_code == 200, blocked.text
        assert blocked.json()["error_reason"] == "agent_not_published"

        published = client.post(
            f"/api/rest/v1/agent_definitions/{agent_id}/publish"
        )
        assert published.status_code == 200, published.text
        assert published.json()["lifecycle"]["run_action_enabled"] is True

        actions = [action for action, _ in _audit_actions(agent_id)]
        assert actions == [
            "agent.lifecycle.created_draft",
            "agent.lifecycle.published",
        ]

        deleted = client.delete(
            f"/api/rest/v1/agent_definitions/{agent_id}"
        )
        assert deleted.status_code == 200, deleted.text
