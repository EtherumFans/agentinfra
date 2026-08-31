"""Current Corti trace-export and caller-owned Task-feedback contracts."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app import database
from app.icoder.agent_runtime.context.context_repository import ContextRepository
from app.icoder.agent_runtime.context.db_models import (
    ContextMessageRow,
    ContextRow,
    ContextTaskRefRow,
)
from app.models.agent_feedback import (
    AgentTaskFeedback,
    FeedbackTrainingAuthorization,
)
from app.models.organization import Organization, OrganizationMember, OrgRole
from app.models.user import User, UserRole
from app.models.run_history import RunHistoryModel
from app.models.run_trace import RunTraceEventModel
from app.services.phi_encryption import is_encrypted_value
from app.services.retention import purge_expired_agent_feedback


async def _seed() -> tuple[str, str, str]:
    context_id = str(uuid.uuid4())
    task_id = f"task-{uuid.uuid4().hex}"
    message_id = f"agent-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    async with database.AsyncSessionLocal() as db:
        if await db.get(Organization, "org_default1") is None:
            db.add(Organization(
                id="org_default1", name="Observability Test Org",
                slug="observability-test-org", plan="free", settings={}, is_active=True,
            ))
            await db.flush()
        if await db.get(User, "u-test-bypass") is None:
            db.add(User(
                id="u-test-bypass",
                username="observability-test-user",
                email="observability-test@example.invalid",
                hashed_password="not-used",
                full_name="Observability Test User",
                role=UserRole.ADMIN,
                department="test",
                is_active=True,
                is_verified=True,
            ))
            await db.flush()
        member = (await db.execute(select(OrganizationMember).where(
            OrganizationMember.organization_id == "org_default1",
            OrganizationMember.user_id == "u-test-bypass",
        ))).scalar_one_or_none()
        if member is None:
            db.add(OrganizationMember(
                organization_id="org_default1",
                user_id="u-test-bypass",
                role=OrgRole.OWNER,
                is_default=True,
            ))
            await db.flush()
        else:
            member.role = OrgRole.OWNER
        db.add(ContextRow(
            id=context_id, created_at=now, updated_at=now,
            expires_at=now + timedelta(hours=1), agent_id="medcoder-coding-review",
            organization_id="org_default1", status="active", metadata_json="{}",
            redacted_input_hash="", original_input_ref="",
        ))
        db.add(ContextTaskRefRow(
            context_id=context_id, task_id=task_id, state="completed",
            started_at=now, completed_at=now,
        ))
        db.add(ContextMessageRow(
            context_id=context_id, message_id=message_id, role="agent",
            parts_json='[{"kind":"text","text":"safe"}]', timestamp=now,
            redacted=True,
            metadata_json=json.dumps({"a2a_v1_task_id": task_id}),
        ))
        for ordinal in range(3):
            run_id = f"run-{ordinal}-{uuid.uuid4()}"
            created = now - timedelta(minutes=ordinal)
            db.add(RunHistoryModel(
                organization_id="org_default1", user_id=None,
                agent_id="medcoder-coding-review", context_id=context_id,
                run_id=run_id, trace_id=f"source-{ordinal}", runtime_mode="mock",
                latency_ms=10 + ordinal, cost_usd=0.0,
                input_text="患者姓名：张三，身份证号：110101199001011234",
                output_summary="sensitive output must never be exported",
                error=False, status="COMPLETED", created_at=created, updated_at=created,
            ))
            db.add(RunTraceEventModel(
                run_id=run_id, organization_id="org_default1",
                agent_id="medcoder-coding-review", step="tools_call", status="ok",
                duration_ms=3.5, ts=created.timestamp(),
                safe_metadata_json={
                    "tool_name": "search_icd", "total_tokens": 42,
                    "input.value": "must-not-export",
                    "authorization": "must-not-export",
                },
                event_id=f"event-{ordinal}", sequence_number=1,
                trace_id=f"source-{ordinal}", identity_source="test",
                created_at=created, updated_at=created,
            ))
            db.add(RunTraceEventModel(
                run_id=run_id, organization_id="org_default1",
                agent_id="medcoder-coding-review", step="output_generated", status="ok",
                duration_ms=6.5, ts=created.timestamp() + 0.01,
                safe_metadata_json={
                    "backend_provider": "icoder.pure-llm.v1",
                    "backend_type": "pure_llm",
                    "model_provider": "deepseek",
                    "model_system": "deepseek",
                    "model_name": "deepseek-chat",
                    "input_tokens": 17,
                    "output_tokens": 25,
                    "total_tokens": 42,
                    "model_cost_usd": 0.00012,
                    "finish_reason": "stop",
                    "llm_call_count": 1,
                    "input.value": "must-not-export",
                    "output.value": "must-not-export",
                },
                event_id=f"llm-event-{ordinal}", sequence_number=2,
                trace_id=f"source-{ordinal}", identity_source="test",
                created_at=created, updated_at=created,
            ))
        await db.commit()
    return context_id, task_id, message_id


@pytest.mark.asyncio
async def test_trace_export_is_paginated_hierarchical_and_minimum_necessary(client) -> None:
    context_id, _task_id, _message_id = await _seed()
    response = await client.get(
        f"/api/v2/agentic/contexts/{context_id}/trace?pageSize=2",
        headers={"X-Tenant": "org_default1"},
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert len(page["traces"]) == 2
    assert page["totalSize"] is None
    assert page["nextPageToken"]
    first = page["traces"][0]
    assert len(first["trace"]["id"]) == 32
    assert first["trace"]["thread_id"] == context_id
    assert len(first["spans"][0]["span_id"]) == 16
    assert first["spans"][1]["parent_span_id"] == first["spans"][0]["span_id"]
    assert first["spans"][0]["attributes"]["openinference.span.kind"] == "AGENT"
    assert first["spans"][0]["attributes"]["session.id"] == context_id
    assert first["spans"][1]["attributes"]["icoder.tool_name"] == "search_icd"
    assert first["spans"][1]["attributes"]["tool.name"] == "search_icd"
    assert first["spans"][1]["attributes"]["llm.token_count.total"] == 42
    llm_span = first["spans"][2]
    assert llm_span["attributes"]["openinference.span.kind"] == "LLM"
    assert llm_span["attributes"]["llm.provider"] == "deepseek"
    assert llm_span["attributes"]["llm.system"] == "deepseek"
    assert llm_span["attributes"]["llm.model_name"] == "deepseek-chat"
    assert llm_span["attributes"]["llm.token_count.prompt"] == 17
    assert llm_span["attributes"]["llm.token_count.completion"] == 25
    assert llm_span["attributes"]["llm.token_count.total"] == 42
    assert llm_span["attributes"]["llm.cost.total"] == 0.00012
    assert llm_span["attributes"]["llm.finish_reason"] == "stop"
    assert llm_span["attributes"]["icoder.trace.input_exported"] is False
    assert llm_span["attributes"]["icoder.trace.output_exported"] is False
    serialized = json.dumps(page, ensure_ascii=False).lower()
    assert "张三" not in serialized
    assert "110101199001011234" not in serialized
    assert "must-not-export" not in serialized
    assert "authorization" not in serialized

    second = await client.get(
        f"/api/v2/agentic/contexts/{context_id}/trace",
        params={"pageSize": 2, "pageToken": page["nextPageToken"]},
        headers={"X-Tenant": "org_default1"},
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["traces"]) == 1
    tampered = page["nextPageToken"][:-1] + ("A" if page["nextPageToken"][-1] != "A" else "B")
    rejected = await client.get(
        f"/api/v2/agentic/contexts/{context_id}/trace",
        params={"pageToken": tampered}, headers={"X-Tenant": "org_default1"},
    )
    assert rejected.status_code == 400


@pytest.mark.asyncio
async def test_feedback_is_redacted_encrypted_idempotent_caller_owned_and_deletable(
    client, monkeypatch,
) -> None:
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    context_id, task_id, message_id = await _seed()
    body = {
        "rating": {"scale": "binary", "value": 0},
        "labels": ["incorrect", "other"],
        "reason": "患者身份证号：110101199001011234，结果不正确",
        "target": {"messageId": message_id},
        "metadata": {
            "collectionMethod": "caseReview",
            "clientReference": "review-session-42",
            "actor": {"externalId": "reviewer-pseudo-9"},
        },
    }
    url = f"/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/feedback"
    created = await client.post(url, json=body, headers={"X-Tenant": "org_default1"})
    assert created.status_code == 201, created.text
    feedback_id = created.json()["id"]
    assert "110101199001011234" not in created.text
    assert created.json()["target"]["messageId"] == message_id

    updated_body = dict(body)
    updated_body["rating"] = {"scale": "binary", "value": 1}
    updated_body["labels"] = ["helpful"]
    updated_body["reason"] = "复核后可用"
    updated = await client.post(url, json=updated_body, headers={"X-Tenant": "org_default1"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["id"] == feedback_id
    assert updated.json()["normalizedScore"] == 1.0

    listed = await client.get(url, headers={"X-Tenant": "org_default1"})
    assert listed.status_code == 200
    assert len(listed.json()["feedbacks"]) == 1
    async with database.AsyncSessionLocal() as db:
        row = (await db.execute(select(AgentTaskFeedback).where(
            AgentTaskFeedback.id == feedback_id
        ))).scalar_one()
        assert is_encrypted_value(row.reason_encrypted)
        metadata = json.loads(row.safe_metadata_json)
        assert "clientReference" not in metadata
        assert "actorExternalId" not in metadata
        assert len(metadata["clientReferenceHash"]) == 64

    deleted = await client.delete(url, headers={"X-Tenant": "org_default1"})
    assert deleted.status_code == 204
    repeated = await client.delete(url, headers={"X-Tenant": "org_default1"})
    assert repeated.status_code == 204
    assert (await client.get(url, headers={"X-Tenant": "org_default1"})).json() == {"feedbacks": []}


@pytest.mark.asyncio
async def test_feedback_validation_and_context_hard_delete(client) -> None:
    context_id, task_id, _message_id = await _seed()
    url = f"/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/feedback"
    invalid = await client.post(url, json={
        "rating": {"scale": "binary", "value": 1}, "labels": ["other"],
    }, headers={"X-Tenant": "org_default1"})
    assert invalid.status_code == 422
    created = await client.post(url, json={
        "rating": {"scale": "binary", "value": 1}, "labels": ["correct"],
    }, headers={"X-Tenant": "org_default1"})
    assert created.status_code == 201
    feedback_id = created.json()["id"]
    authorization = await client.put(
        f"{url}/{feedback_id}/training-authorization",
        json={
            "purposeOfUse": "quality_improvement",
            "dataScope": "feedback_metadata_only",
            "expiresAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "approvalReference": "qi-context-delete-001",
            "acknowledgement": True,
        },
        headers={"X-Tenant": "org_default1"},
    )
    assert authorization.status_code == 200, authorization.text
    async with database.AsyncSessionLocal() as db:
        counts = await ContextRepository(db).hard_delete_context(context_id)
        assert counts["agent_task_feedback"] == 1
        assert counts["feedback_training_authorizations"] == 1
        assert (await db.execute(select(AgentTaskFeedback).where(
            AgentTaskFeedback.context_id == context_id
        ))).scalars().all() == []


@pytest.mark.asyncio
async def test_feedback_training_authorization_is_independent_bounded_and_revoked_on_change(
    client,
) -> None:
    context_id, task_id, _message_id = await _seed()
    feedback_url = f"/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/feedback"
    created = await client.post(
        feedback_url,
        json={
            "rating": {"scale": "binary", "value": 1},
            "labels": ["correct"],
            "reason": "人工复核通过",
        },
        headers={"X-Tenant": "org_default1"},
    )
    assert created.status_code == 201, created.text
    feedback_id = created.json()["id"]
    authorization_url = f"{feedback_url}/{feedback_id}/training-authorization"
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    async with database.AsyncSessionLocal() as db:
        assert (await db.execute(select(FeedbackTrainingAuthorization).where(
            FeedbackTrainingAuthorization.feedback_id == feedback_id
        ))).scalar_one_or_none() is None
        member = (await db.execute(select(OrganizationMember).where(
            OrganizationMember.organization_id == "org_default1",
            OrganizationMember.user_id == "u-test-bypass",
        ))).scalar_one()
        member.role = OrgRole.MEMBER
        await db.commit()
    denied = await client.put(
        authorization_url,
        json={
            "purposeOfUse": "quality_improvement",
            "dataScope": "feedback_metadata_only",
            "expiresAt": expires_at.isoformat(),
            "approvalReference": "qi-review-20260822-denied",
            "acknowledgement": True,
        },
        headers={"X-Tenant": "org_default1"},
    )
    assert denied.status_code == 403
    async with database.AsyncSessionLocal() as db:
        member = (await db.execute(select(OrganizationMember).where(
            OrganizationMember.organization_id == "org_default1",
            OrganizationMember.user_id == "u-test-bypass",
        ))).scalar_one()
        member.role = OrgRole.OWNER
        await db.commit()
    authorized = await client.put(
        authorization_url,
        json={
            "purposeOfUse": "quality_improvement",
            "dataScope": "feedback_metadata_only",
            "expiresAt": expires_at.isoformat(),
            "approvalReference": "qi-review-20260822-001",
            "acknowledgement": True,
        },
        headers={"X-Tenant": "org_default1"},
    )
    assert authorized.status_code == 200, authorized.text
    body = authorized.json()
    assert body["trainingAuthorized"] is True
    assert body["authorizationStatus"] == "active"
    assert body["dataScope"] == "feedback_metadata_only"
    assert "approvalReference" not in authorized.text
    assert "reason" not in authorized.text

    async with database.AsyncSessionLocal() as db:
        row = (await db.execute(select(FeedbackTrainingAuthorization).where(
            FeedbackTrainingAuthorization.feedback_id == feedback_id
        ))).scalar_one()
        assert row.status == "active"
        assert row.authorized_by_user_id == "u-test-bypass"
        assert len(row.approval_reference_hash) == 64
        assert "qi-review" not in row.approval_reference_hash

    # Feedback submission never grants training permission, and any change to
    # an already-authorized snapshot revokes the independent grant.
    changed = await client.post(
        feedback_url,
        json={
            "rating": {"scale": "binary", "value": 0},
            "labels": ["incorrect"],
            "reason": "复核结果变更",
        },
        headers={"X-Tenant": "org_default1"},
    )
    assert changed.status_code == 200, changed.text
    state = await client.get(
        authorization_url, headers={"X-Tenant": "org_default1"}
    )
    assert state.status_code == 200, state.text
    assert state.json()["trainingAuthorized"] is False
    assert state.json()["authorizationStatus"] == "revoked"

    too_long = await client.put(
        authorization_url,
        json={
            "purposeOfUse": "quality_improvement",
            "dataScope": "feedback_metadata_only",
            "expiresAt": (datetime.now(timezone.utc) + timedelta(days=31)).isoformat(),
            "approvalReference": "qi-review-20260822-002",
            "acknowledgement": True,
        },
        headers={"X-Tenant": "org_default1"},
    )
    assert too_long.status_code == 422

    reauthorized = await client.put(
        authorization_url,
        json={
            "purposeOfUse": "quality_improvement",
            "dataScope": "feedback_metadata_only",
            "expiresAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "approvalReference": "qi-review-20260822-003",
            "acknowledgement": True,
        },
        headers={"X-Tenant": "org_default1"},
    )
    assert reauthorized.status_code == 200
    assert reauthorized.json()["trainingAuthorized"] is True
    revoked = await client.delete(
        authorization_url, headers={"X-Tenant": "org_default1"}
    )
    assert revoked.status_code == 204
    assert (await client.delete(
        authorization_url, headers={"X-Tenant": "org_default1"}
    )).status_code == 204
    final = await client.get(
        authorization_url, headers={"X-Tenant": "org_default1"}
    )
    assert final.json()["authorizationStatus"] == "revoked"


@pytest.mark.asyncio
async def test_feedback_scope_caller_isolation_and_retention(client) -> None:
    from app.main import app
    from app.middleware.auth import get_current_user_or_oauth_client

    context_id, task_id, _message_id = await _seed()
    url = f"/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/feedback"
    created = await client.post(url, json={
        "rating": {"scale": "binary", "value": 1}, "labels": ["complete"],
    }, headers={"X-Tenant": "org_default1"})
    assert created.status_code == 201
    feedback_id = created.json()["id"]

    original = app.dependency_overrides[get_current_user_or_oauth_client]
    try:
        app.dependency_overrides[get_current_user_or_oauth_client] = lambda: (
            None, {"client_id": "partner-a", "scopes": ["feedback:read"]},
        )
        isolated = await client.get(url, headers={"X-Tenant": "org_default1"})
        assert isolated.status_code == 200
        assert isolated.json() == {"feedbacks": []}
        denied = await client.post(url, json={
            "rating": {"scale": "binary", "value": 1}, "labels": ["correct"],
        }, headers={"X-Tenant": "org_default1"})
        assert denied.status_code == 403
    finally:
        app.dependency_overrides[get_current_user_or_oauth_client] = original

    authorization_url = f"{url}/{feedback_id}/training-authorization"
    assert (await client.put(
        authorization_url,
        json={
            "purposeOfUse": "quality_improvement",
            "dataScope": "feedback_metadata_only",
            "expiresAt": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "approvalReference": "qi-retention-001",
            "acknowledgement": True,
        },
        headers={"X-Tenant": "org_default1"},
    )).status_code == 200

    async with database.AsyncSessionLocal() as db:
        row = (await db.execute(select(AgentTaskFeedback).where(
            AgentTaskFeedback.context_id == context_id
        ))).scalar_one()
        row.retention_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    async with database.AsyncSessionLocal() as db:
        assert await purge_expired_agent_feedback(db, dry_run=True) == 1
        assert await purge_expired_agent_feedback(db) == 1
    async with database.AsyncSessionLocal() as db:
        assert (await db.execute(select(AgentTaskFeedback).where(
            AgentTaskFeedback.context_id == context_id
        ))).scalars().all() == []
        assert (await db.execute(select(FeedbackTrainingAuthorization).where(
            FeedbackTrainingAuthorization.context_id == context_id
        ))).scalars().all() == []


@pytest.mark.asyncio
async def test_agent_usage_is_tenant_scoped_exclusive_and_always_daily(client) -> None:
    await _seed()
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    async with database.AsyncSessionLocal() as db:
        for ordinal, (created, context_id, org_id, classification) in enumerate((
            (start, "context-a", "org_default1", "MODERN"),
            (start + timedelta(hours=2), "context-a", "org_default1", "MODERN"),
            (start + timedelta(days=1, minutes=1), "context-b", "org_default1", "MODERN"),
            # Exact exclusive boundary and invisible/cross-tenant rows must not count.
            (start + timedelta(days=2), "context-c", "org_default1", "MODERN"),
            (start + timedelta(hours=3), "context-d", "org_default1", "QUARANTINED"),
        )):
            db.add(RunHistoryModel(
                organization_id=org_id, user_id=None,
                agent_id="medical-coding-agent", context_id=context_id,
                run_id=f"usage-{ordinal}-{uuid.uuid4()}", trace_id="", runtime_mode="mock",
                latency_ms=1, cost_usd=0.0, input_text="safe", output_summary="safe",
                error=False, status="COMPLETED", tenancy_classification=classification,
                created_at=created, updated_at=created,
            ))
        await db.commit()

    response = await client.get(
        "/api/v2/agentic/agents/medical-coding-agent/usage",
        params={
            "from": start.isoformat(),
            "to": (start + timedelta(days=2)).isoformat(),
            "granularity": "hour",
        },
        headers={"X-Tenant": "org_default1"},
    )
    assert response.status_code == 200, response.text
    usage = response.json()
    assert usage["granularity"] == "day"
    assert usage["totals"] == {"invocations": 3, "uniqueContexts": 2}
    assert [bucket["invocations"] for bucket in usage["buckets"]] == [2, 1]
    assert [bucket["uniqueContexts"] for bucket in usage["buckets"]] == [1, 1]
    assert usage["from"].startswith("2026-08-01T00:00:00")
    assert usage["to"].startswith("2026-08-03T00:00:00")

    unknown = await client.get(
        "/api/v2/agentic/agents/not-a-real-agent/usage",
        headers={"X-Tenant": "org_default1"},
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_automated_feedback_requires_dedicated_machine_scope(client) -> None:
    from app.main import app
    from app.middleware.auth import get_current_user_or_oauth_client

    context_id, task_id, _message_id = await _seed()
    url = f"/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/feedback"
    automated = {
        "rating": {"scale": "binary", "value": 1},
        "labels": ["correct"],
        "metadata": {"collectionMethod": "automatedEvaluation"},
    }
    # A signed-in human and a broad write token cannot claim automated provenance.
    assert (await client.post(
        url, json=automated, headers={"X-Tenant": "org_default1"},
    )).status_code == 403

    original = app.dependency_overrides[get_current_user_or_oauth_client]
    try:
        app.dependency_overrides[get_current_user_or_oauth_client] = lambda: (
            None, {"client_id": "evaluator", "scopes": ["api:write"]},
        )
        denied = await client.post(
            url, json=automated, headers={"X-Tenant": "org_default1"},
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["required_scope"] == "feedback:evaluate"

        app.dependency_overrides[get_current_user_or_oauth_client] = lambda: (
            None, {"client_id": "evaluator", "scopes": ["feedback:evaluate"]},
        )
        accepted = await client.post(
            url, json=automated, headers={"X-Tenant": "org_default1"},
        )
        assert accepted.status_code == 201, accepted.text

        human_provenance = dict(automated)
        human_provenance["metadata"] = {"collectionMethod": "caseReview"}
        assert (await client.post(
            url, json=human_provenance, headers={"X-Tenant": "org_default1"},
        )).status_code == 403
    finally:
        app.dependency_overrides[get_current_user_or_oauth_client] = original
