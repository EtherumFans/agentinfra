"""First-class Agentic v2 Context, Task, and Artifact resource contracts."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app import database
from app.icoder.agent_runtime.a2a.v1.artifact_store import persist_artifacts
from app.icoder.agent_runtime.a2a.v1.artifact_object_store import (
    DownloadGrantError,
    actor_fingerprint,
    consume_download,
)
from app.icoder.agent_runtime.context.db_models import (
    A2AArtifactDownloadGrantRow,
    A2AArtifactObjectRow,
    A2ATaskArtifactRow,
    A2ATaskExecutionRow,
    ContextMessageRow,
    ContextRow,
    ContextTaskRefRow,
)
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.services.phi_encryption import encrypt_phi


async def _seed_context(
    *,
    organization_id: str = "org_default1",
    agent_id: str = "medcoder-coding-review",
    created_at: datetime | None = None,
    task_count: int = 2,
) -> tuple[str, list[str]]:
    context_id = str(uuid.uuid4())
    created = created_at or datetime.now(timezone.utc)
    task_ids: list[str] = []
    async with database.AsyncSessionLocal() as db:
        if await db.get(Organization, organization_id) is None:
            db.add(
                Organization(
                    id=organization_id,
                    name=f"Context Resource {organization_id}",
                    slug=f"context-resource-{organization_id}",
                    plan="free",
                    settings={},
                    is_active=True,
                )
            )
            await db.flush()
        db.add(
            ContextRow(
                id=context_id,
                created_at=created,
                updated_at=created + timedelta(seconds=task_count),
                expires_at=created + timedelta(hours=24),
                agent_id=agent_id,
                organization_id=organization_id,
                status="active",
                metadata_json="{}",
                redacted_input_hash="",
                original_input_ref="",
            )
        )
        for ordinal in range(task_count):
            task_id = f"task-{uuid.uuid4().hex}"
            task_ids.append(task_id)
            started = created + timedelta(seconds=ordinal)
            user_message_id = f"user-{uuid.uuid4()}"
            agent_message_id = f"agent-{uuid.uuid4()}"
            user_text = f"safe synthetic request {ordinal}"
            result_text = f"safe synthetic result {ordinal}"
            request = {
                "request_id": f"request-{ordinal}",
                "legacy_params": {
                    "message": {
                        "role": "user",
                        "messageId": user_message_id,
                        "contextId": context_id,
                        "parts": [{"kind": "text", "text": user_text}],
                        "metadata": {"_a2a_v1_task_id": task_id},
                    }
                },
            }
            result = {
                "kind": "message",
                "messageId": agent_message_id,
                "contextId": context_id,
                "role": "agent",
                "parts": [{"kind": "text", "text": result_text}],
                "metadata": {"internal_run_id": f"must-not-export-{ordinal}"},
            }
            db.add(
                ContextTaskRefRow(
                    context_id=context_id,
                    task_id=task_id,
                    state="completed",
                    started_at=started,
                    completed_at=started + timedelta(milliseconds=500),
                )
            )
            db.add(
                A2ATaskExecutionRow(
                    task_id=task_id,
                    context_id=context_id,
                    organization_id=organization_id,
                    agent_id=agent_id,
                    message_id=user_message_id,
                    request_json=encrypt_phi(json.dumps(request)),
                    result_json=encrypt_phi(json.dumps(result)),
                    error_code=None,
                    attempt_count=1,
                    lease_owner=None,
                    lease_expires_at=None,
                    created_at=started,
                    updated_at=started + timedelta(milliseconds=500),
                )
            )
            db.add_all(
                [
                    ContextMessageRow(
                        context_id=context_id,
                        message_id=user_message_id,
                        role="user",
                        parts_json=encrypt_phi(
                            json.dumps([{"kind": "text", "text": user_text}])
                        ),
                        timestamp=started,
                        redacted=True,
                        metadata_json=json.dumps(
                            {
                                "a2a_v1_task_id": task_id,
                                "private_correlation": "must-not-export",
                            }
                        ),
                    ),
                    ContextMessageRow(
                        context_id=context_id,
                        message_id=agent_message_id,
                        role="agent",
                        parts_json=encrypt_phi(
                            json.dumps([{"kind": "text", "text": result_text}])
                        ),
                        timestamp=started + timedelta(microseconds=1),
                        redacted=True,
                        metadata_json=json.dumps(
                            {
                                "a2a_v1_task_id": task_id,
                                "run_id": "must-not-export",
                            }
                        ),
                    ),
                ]
            )
            await persist_artifacts(
                db,
                context_id=context_id,
                task_id=task_id,
                artifacts=[{
                    "artifactId": f"{task_id}-result",
                    "name": "Agent result",
                    "parts": [{"text": result_text, "mediaType": "text/plain"}],
                    "metadata": {"sourceMessageId": agent_message_id},
                }],
                created_at=started + timedelta(milliseconds=500),
            )
        await db.commit()
    return context_id, task_ids


async def _cleanup(*context_ids: str) -> None:
    async with database.AsyncSessionLocal() as db:
        object_ids = select(A2AArtifactObjectRow.object_id).where(
            A2AArtifactObjectRow.context_id.in_(context_ids)
        )
        await db.execute(
            delete(A2AArtifactDownloadGrantRow).where(
                A2AArtifactDownloadGrantRow.object_id.in_(object_ids)
            )
        )
        await db.execute(
            delete(A2AArtifactObjectRow).where(
                A2AArtifactObjectRow.context_id.in_(context_ids)
            )
        )
        await db.execute(
            delete(A2ATaskArtifactRow).where(
                A2ATaskArtifactRow.context_id.in_(context_ids)
            )
        )
        await db.execute(
            delete(A2ATaskExecutionRow).where(
                A2ATaskExecutionRow.context_id.in_(context_ids)
            )
        )
        await db.execute(
            delete(ContextMessageRow).where(ContextMessageRow.context_id.in_(context_ids))
        )
        await db.execute(
            delete(ContextTaskRefRow).where(ContextTaskRefRow.context_id.in_(context_ids))
        )
        await db.execute(delete(ContextRow).where(ContextRow.id.in_(context_ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_context_detail_has_oldest_first_full_task_history_and_artifact(client) -> None:
    context_id, task_ids = await _seed_context()
    headers = {"X-Tenant": "org_default1"}
    try:
        response = await client.get(
            f"/api/v2/agentic/contexts/{context_id}", headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.headers["A2A-Version"] == "1.0"
        assert response.headers["Cache-Control"] == "no-store"
        body = response.json()
        assert body["id"] == context_id
        assert body["agentId"] == "medcoder-coding-review"
        assert body["taskCount"] == 2
        assert [task["id"] for task in body["tasks"]] == task_ids
        first = body["tasks"][0]
        assert [message["role"] for message in first["history"]] == [
            "ROLE_USER",
            "ROLE_AGENT",
        ]
        assert all(message["taskId"] == task_ids[0] for message in first["history"])
        serialized = json.dumps(body)
        assert "private_correlation" not in serialized
        assert "internal_run_id" not in serialized
        assert "must-not-export" not in serialized

        capped = await client.get(
            f"/api/v2/agentic/contexts/{context_id}",
            params={"historyLength": 1},
            headers=headers,
        )
        assert capped.status_code == 200
        assert [item["role"] for item in capped.json()["tasks"][0]["history"]] == [
            "ROLE_AGENT"
        ]

        task = await client.get(
            f"/api/v2/agentic/contexts/{context_id}/tasks/{task_ids[0]}",
            headers=headers,
        )
        assert task.status_code == 200
        artifact_id = task.json()["artifacts"][0]["artifactId"]
        artifact = await client.get(
            f"/api/v2/agentic/contexts/{context_id}/tasks/{task_ids[0]}"
            f"/artifacts/{artifact_id}",
            headers=headers,
        )
        assert artifact.status_code == 200, artifact.text
        assert artifact.json()["artifactId"] == f"{task_ids[0]}-result"
        assert artifact.json()["parts"][0]["text"] == "safe synthetic result 0"
        wrong_task = await client.get(
            f"/api/v2/agentic/contexts/{context_id}/tasks/{task_ids[1]}"
            f"/artifacts/{artifact_id}",
            headers=headers,
        )
        assert wrong_task.status_code == 404
    finally:
        await _cleanup(context_id)


@pytest.mark.asyncio
async def test_context_and_task_lists_are_filtered_paginated_and_cursor_bound(client) -> None:
    base = datetime(2026, 8, 20, tzinfo=timezone.utc)
    first, first_tasks = await _seed_context(created_at=base, task_count=2)
    second, _ = await _seed_context(created_at=base + timedelta(hours=1), task_count=1)
    third, _ = await _seed_context(
        created_at=base + timedelta(hours=2),
        task_count=1,
        agent_id="note-completeness",
    )
    headers = {"X-Tenant": "org_default1"}
    try:
        page_one = await client.get(
            "/api/v2/agentic/contexts",
            params={
                "agentId": "medcoder-coding-review",
                "from": "2026-08-20T00:00:00Z",
                "to": "2026-08-21T00:00:00Z",
                "pageSize": 1,
            },
            headers=headers,
        )
        assert page_one.status_code == 200, page_one.text
        assert page_one.json()["totalSize"] == 2
        assert [item["id"] for item in page_one.json()["contexts"]] == [second]
        token = page_one.json()["nextPageToken"]
        assert token
        page_two = await client.get(
            "/api/v2/agentic/contexts",
            params={
                "agentId": "medcoder-coding-review",
                "from": "2026-08-20T00:00:00Z",
                "to": "2026-08-21T00:00:00Z",
                "pageSize": 1,
                "pageToken": token,
            },
            headers=headers,
        )
        assert page_two.status_code == 200, page_two.text
        assert [item["id"] for item in page_two.json()["contexts"]] == [first]
        changed_filter = await client.get(
            "/api/v2/agentic/contexts",
            params={"agentId": "note-completeness", "pageToken": token},
            headers=headers,
        )
        assert changed_filter.status_code == 400

        task_page_one = await client.get(
            f"/api/v2/agentic/contexts/{first}/tasks",
            params={"pageSize": 1},
            headers=headers,
        )
        assert task_page_one.status_code == 200
        assert task_page_one.json()["totalSize"] == 2
        assert task_page_one.json()["tasks"][0]["id"] == first_tasks[0]
        assert task_page_one.json()["tasks"][0]["history"] == []
        task_page_two = await client.get(
            f"/api/v2/agentic/contexts/{first}/tasks",
            params={
                "pageSize": 1,
                "pageToken": task_page_one.json()["nextPageToken"],
            },
            headers=headers,
        )
        assert task_page_two.status_code == 200, task_page_two.text
        assert task_page_two.json()["tasks"][0]["id"] == first_tasks[1]
    finally:
        await _cleanup(first, second, third)


@pytest.mark.asyncio
async def test_context_resources_are_tenant_and_scope_isolated_and_delete_is_audited(
    client,
) -> None:
    from app.main import app
    from app.middleware.auth import get_current_user_or_oauth_client

    own_context, own_tasks = await _seed_context(task_count=1)
    foreign_context, _ = await _seed_context(
        organization_id="org_other001", task_count=1
    )
    headers = {"X-Tenant": "org_default1"}
    original = app.dependency_overrides[get_current_user_or_oauth_client]
    try:
        assert (
            await client.get(
                f"/api/v2/agentic/contexts/{foreign_context}", headers=headers
            )
        ).status_code == 404
        assert (
            await client.get(
                f"/api/v2/agentic/contexts/{foreign_context}/tasks/missing",
                headers=headers,
            )
        ).status_code == 404

        app.dependency_overrides[get_current_user_or_oauth_client] = lambda: (
            None,
            {"client_id": "read-only-client", "scopes": ["contexts:read"]},
        )
        assert (
            await client.get(
                f"/api/v2/agentic/contexts/{own_context}", headers=headers
            )
        ).status_code == 200
        denied = await client.delete(
            f"/api/v2/agentic/contexts/{own_context}", headers=headers
        )
        assert denied.status_code == 403

        app.dependency_overrides[get_current_user_or_oauth_client] = lambda: (
            None,
            {"client_id": "delete-client", "scopes": ["contexts:write"]},
        )
        deleted = await client.delete(
            f"/api/v2/agentic/contexts/{own_context}", headers=headers
        )
        assert deleted.status_code == 204, deleted.text
        assert deleted.headers["A2A-Version"] == "1.0"
        assert (
            await client.get(
                f"/api/v2/agentic/contexts/{own_context}", headers=headers
            )
        ).status_code == 403
    finally:
        app.dependency_overrides[get_current_user_or_oauth_client] = original

    async with database.AsyncSessionLocal() as db:
        assert await db.get(ContextRow, own_context) is None
        assert await db.get(A2ATaskExecutionRow, own_tasks[0]) is None
        assert (
            await db.execute(
                select(A2ATaskArtifactRow).where(
                    A2ATaskArtifactRow.context_id == own_context
                )
            )
        ).scalars().first() is None
        audit = (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.organization_id == "org_default1",
                    AuditLog.action == "agentic.context.delete",
                    AuditLog.resource_id == own_context,
                )
                .order_by(AuditLog.created_at.desc())
            )
        ).scalars().first()
        assert audit is not None
        assert audit.details["reason_code"] == "api_v2_user_requested"
        assert "safe synthetic" not in json.dumps(audit.details)
    await _cleanup(foreign_context)


@pytest.mark.asyncio
async def test_managed_artifact_object_full_lifecycle_is_single_use_and_audited(
    client, monkeypatch,
) -> None:
    context_id, task_ids = await _seed_context(task_count=1)
    task_id = task_ids[0]
    artifact_id = f"{task_id}-result"
    headers = {"X-Tenant": "org_default1"}
    content = b'{"summary":"synthetic deidentified coding result"}'
    root = (
        f"/api/v2/agentic/contexts/{context_id}/tasks/{task_id}"
        f"/artifacts/{artifact_id}/objects"
    )
    try:
        uploaded = await client.post(
            root,
            headers=headers,
            json={
                "raw": base64.b64encode(content).decode("ascii"),
                "filename": "coding-result.json",
                "mediaType": "application/json",
                "dataClassification": "deidentified",
            },
        )
        assert uploaded.status_code == 201, uploaded.text
        item = uploaded.json()
        object_id = item["objectId"]
        assert item["status"] == "available"
        assert item["malwareScanStatus"] == "clean"
        assert item["dlpScanStatus"] == "clear"
        assert item["sha256"]
        assert uploaded.headers["A2A-Version"] == "1.0"

        async with database.AsyncSessionLocal() as db:
            row = await db.get(A2AArtifactObjectRow, object_id)
            assert row is not None
            assert row.payload_ciphertext is not None
            assert content not in row.payload_ciphertext
            assert row.actor_id_hash != "u-test-bypass"

        listed = await client.get(root, headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()["totalSize"] == 1
        assert listed.json()["objects"][0]["objectId"] == object_id

        artifact = await client.get(
            f"/api/v2/agentic/contexts/{context_id}/tasks/{task_id}"
            f"/artifacts/{artifact_id}",
            headers=headers,
        )
        assert artifact.status_code == 200, artifact.text
        assert artifact.json()["metadata"]["managedObjects"][0]["objectId"] == object_id
        assert (
            "urn:icoder:a2a:managed-artifact-object:v1"
            in artifact.json()["extensions"]
        )

        authorized = await client.post(
            f"{root}/{object_id}:authorize-download",
            headers=headers,
            json={"purposeOfUse": "treatment", "expiresInSeconds": 30},
        )
        assert authorized.status_code == 200, authorized.text
        authorization = authorized.json()
        assert authorization["singleUse"] is True
        assert authorization["part"]["mediaType"] == "application/json"
        assert authorization["part"]["metadata"]["sha256"] == item["sha256"]
        download_url = authorization["part"]["url"]
        assert download_url.startswith(
            "http://test/api/v2/agentic/artifact-objects/download/grant-"
        )
        assert "?" not in download_url
        grant_id = download_url.rsplit("/", 1)[-1]

        async with database.AsyncSessionLocal() as db:
            with pytest.raises(DownloadGrantError) as wrong_actor:
                await consume_download(
                    db,
                    grant_id=grant_id,
                    organization_id="org_default1",
                    actor_type="user",
                    actor_id_hash=actor_fingerprint("user", "another-user"),
                )
            assert wrong_actor.value.code == "DOWNLOAD_GRANT_INVALID"

        tampered_url = download_url[:-1] + ("A" if download_url[-1] != "A" else "B")
        tampered = await client.get(tampered_url, headers=headers)
        assert tampered.status_code == 404
        assert tampered.json()["detail"]["code"] == "DOWNLOAD_GRANT_INVALID"

        monkeypatch.setenv("ICODER_AUDIT_WRITE_PAUSED", "true")
        audit_paused = await client.get(download_url, headers=headers)
        assert audit_paused.status_code == 503
        monkeypatch.delenv("ICODER_AUDIT_WRITE_PAUSED")

        downloaded = await client.get(download_url, headers=headers)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content == content
        assert downloaded.headers["Cache-Control"] == "no-store, private"
        assert downloaded.headers["X-Content-Type-Options"] == "nosniff"
        assert downloaded.headers["X-Artifact-SHA256"] == item["sha256"]
        assert "attachment" in downloaded.headers["Content-Disposition"]

        replay = await client.get(download_url, headers=headers)
        assert replay.status_code == 410, replay.text
        assert replay.json()["detail"]["code"] == "DOWNLOAD_GRANT_CONSUMED"

        deleted = await client.delete(f"{root}/{object_id}", headers=headers)
        assert deleted.status_code == 204, deleted.text
        assert (await client.get(root, headers=headers)).json()["totalSize"] == 0

        async with database.AsyncSessionLocal() as db:
            actions = set(
                (
                    await db.execute(
                        select(AuditLog.action).where(
                            AuditLog.organization_id == "org_default1",
                            AuditLog.resource_id == object_id,
                        )
                    )
                ).scalars()
            )
            assert {
                "agentic.artifact.object.upload",
                "agentic.artifact.object.download.authorize",
                "agentic.artifact.object.download.consume",
                "agentic.artifact.object.delete",
            } <= actions
    finally:
        await _cleanup(context_id)


@pytest.mark.asyncio
async def test_managed_artifact_download_requires_authenticated_principal(
    client, needs_auth,
) -> None:
    response = await client.get(
        "/api/v2/agentic/artifact-objects/download/"
        "grant-00000000-0000-4000-8000-000000000000"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_managed_artifact_object_dlp_malware_tenant_and_context_deletion(
    client,
) -> None:
    context_id, task_ids = await _seed_context(task_count=1)
    foreign_context, foreign_tasks = await _seed_context(
        organization_id="org_other001", task_count=1
    )
    task_id = task_ids[0]
    artifact_id = f"{task_id}-result"
    headers = {"X-Tenant": "org_default1"}
    root = (
        f"/api/v2/agentic/contexts/{context_id}/tasks/{task_id}"
        f"/artifacts/{artifact_id}/objects"
    )
    sensitive = "患者姓名：测试甲 身份证号：11010519491231002X".encode()
    try:
        blocked = await client.post(
            root,
            headers=headers,
            json={
                "raw": base64.b64encode(sensitive).decode("ascii"),
                "filename": "clinical-result.txt",
                "mediaType": "text/plain",
                "dataClassification": "deidentified",
            },
        )
        assert blocked.status_code == 201, blocked.text
        blocked_item = blocked.json()
        assert blocked_item["status"] == "rejected"
        assert blocked_item["dlpScanStatus"] == "blocked"
        assert blocked_item["rejectionCode"] == "DEIDENTIFICATION_POLICY_BLOCKED"

        denied_download = await client.post(
            f"{root}/{blocked_item['objectId']}:authorize-download",
            headers=headers,
            json={"purposeOfUse": "treatment"},
        )
        assert denied_download.status_code == 409
        assert denied_download.json()["detail"]["code"] == "OBJECT_NOT_AVAILABLE"

        restricted = await client.post(
            root,
            headers=headers,
            json={
                "raw": base64.b64encode(sensitive).decode("ascii"),
                "filename": "clinical-result.txt",
                "mediaType": "text/plain",
                "dataClassification": "clinical-sensitive",
            },
        )
        assert restricted.status_code == 201, restricted.text
        restricted_item = restricted.json()
        assert restricted_item["status"] == "available"
        assert restricted_item["dlpScanStatus"] == "restricted"

        eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        infected = await client.post(
            root,
            headers=headers,
            json={
                "raw": base64.b64encode(eicar).decode("ascii"),
                "filename": "scanner-test.txt",
                "mediaType": "text/plain",
                "dataClassification": "deidentified",
            },
        )
        assert infected.status_code == 201, infected.text
        assert infected.json()["status"] == "rejected"
        assert infected.json()["malwareScanStatus"] == "infected"
        assert infected.json()["rejectionCode"] == "MALWARE_TEST_SIGNATURE"

        spoofed = await client.post(
            root,
            headers=headers,
            json={
                "raw": base64.b64encode(b'{"safe":true}').decode("ascii"),
                "filename": "spoofed.txt",
                "mediaType": "text/plain",
                "dataClassification": "deidentified",
            },
        )
        assert spoofed.status_code == 201
        assert spoofed.json()["rejectionCode"] == "MEDIA_TYPE_MISMATCH"

        invalid_name = await client.post(
            root,
            headers=headers,
            json={
                "raw": base64.b64encode(b"safe").decode("ascii"),
                "filename": "../escape.txt",
                "mediaType": "text/plain",
            },
        )
        assert invalid_name.status_code == 400
        assert invalid_name.json()["detail"]["code"] == "FILENAME_INVALID"

        foreign_root = (
            f"/api/v2/agentic/contexts/{foreign_context}/tasks/{foreign_tasks[0]}"
            f"/artifacts/{foreign_tasks[0]}-result/objects"
        )
        assert (await client.get(foreign_root, headers=headers)).status_code == 404

        grant = await client.post(
            f"{root}/{restricted_item['objectId']}:authorize-download",
            headers=headers,
            json={"purposeOfUse": "treatment"},
        )
        assert grant.status_code == 200, grant.text
        async with database.AsyncSessionLocal() as db:
            grant_id = (
                await db.execute(
                    select(A2AArtifactDownloadGrantRow.grant_id).where(
                        A2AArtifactDownloadGrantRow.object_id
                        == restricted_item["objectId"]
                    )
                )
            ).scalar_one()
        deleted_context = await client.delete(
            f"/api/v2/agentic/contexts/{context_id}", headers=headers
        )
        assert deleted_context.status_code == 204, deleted_context.text
        async with database.AsyncSessionLocal() as db:
            assert (
                await db.execute(
                    select(A2AArtifactObjectRow).where(
                        A2AArtifactObjectRow.context_id == context_id
                    )
                )
            ).scalars().first() is None
            assert (
                await db.get(A2AArtifactDownloadGrantRow, grant_id)
            ) is None
    finally:
        await _cleanup(context_id, foreign_context)
