"""Project Clone -> Customize -> Run/A2A tenancy and provenance closure."""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")
os.environ.setdefault("ICODER_ALLOW_EXTERNAL_LLM", "false")
os.environ.setdefault("ICODER_DISABLE_NATIVE_MEDCODER", "true")


SOURCE_ID = "evidence-extractor"
SOURCE_REF = "icoder/evidence-extractor@1.1.0"
MEDICAL_SOURCE_ID = "medical-coding-agent"
MEDICAL_SOURCE_REF = "icoder/medical-coding-agent@2.0.0"
CDI_SOURCE_ID = "clinical-documentation-improvement-agent"
CDI_SOURCE_REF = "icoder/clinical-documentation-improvement-agent@1.0.0"
CUSTOM_PROMPT = "PROJECT_PROMPT_SENTINEL: locate only explicit governed evidence."
PROJECT_EXPERT_ID = "projectexp01"


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_project_clone():
    from app.api.icoder_agents_hub import _deterministic_clone_id
    from app.database import AsyncSessionLocal
    from app.models.agent import Agent
    from app.models.agent_connector import AgentConnector, ConnectorExecutionAudit
    from app.models.expert import Expert

    clone_ids = {
        _deterministic_clone_id("org_default1", SOURCE_REF),
        _deterministic_clone_id("org_default1", MEDICAL_SOURCE_REF),
        _deterministic_clone_id("org_default1", CDI_SOURCE_REF),
    }

    async def _delete() -> None:
        async with AsyncSessionLocal() as db:
            connector_ids = list((
                await db.execute(
                    select(AgentConnector.id).where(
                        AgentConnector.agent_id.in_(clone_ids)
                    )
                )
            ).scalars().all())
            if connector_ids:
                await db.execute(
                    delete(ConnectorExecutionAudit).where(
                        ConnectorExecutionAudit.connector_id.in_(connector_ids)
                    )
                )
                await db.execute(
                    delete(AgentConnector).where(
                        AgentConnector.id.in_(connector_ids)
                    )
                )
            await db.execute(delete(Agent).where(Agent.id.in_(clone_ids)))
            await db.execute(delete(Expert).where(Expert.id == PROJECT_EXPERT_ID))
            await db.commit()

    asyncio.run(_delete())
    yield
    asyncio.run(_delete())


def _clone(client: TestClient) -> dict:
    response = client.post(f"/api/icoder/agents/{SOURCE_ID}/clone", json={})
    assert response.status_code == 201, response.text
    return response.json()


def test_clone_runtime_pack_preserves_source_contract_and_applies_prompt(
    client: TestClient,
) -> None:
    clone = _clone(client)
    project_agent_id = clone["project_agent_id"]
    assert clone["runtime_agent_id"] == project_agent_id
    assert clone["source_runtime_agent_id"] == SOURCE_ID
    assert clone["run_url"].endswith(
        f"/{project_agent_id}/v1/message:send"
    )

    update = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={"system_prompt": CUSTOM_PROMPT},
    )
    assert update.status_code == 200, update.text

    from app.database import AsyncSessionLocal
    from app.models.agent import Agent
    from app.services.agent_runtime_pack import resolve_tenant_runtime

    async def _resolve():
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(select(Agent).where(Agent.id == project_agent_id))
            ).scalar_one()
            resolution = await resolve_tenant_runtime(
                project_agent_id, "org_default1", db
            )
            return row, resolution

    row, resolution = asyncio.run(_resolve())
    assert row.system_prompt == CUSTOM_PROMPT
    assert resolution.is_clone is True
    assert resolution.runtime_agent_id == SOURCE_ID
    assert resolution.pack is not None
    assert resolution.pack["agent_ref"].startswith(f"icoder/{project_agent_id}@")
    assert resolution.pack["system_prompt"] == CUSTOM_PROMPT
    assert resolution.pack["backend_provider"] == (
        "icoder.governed-evidence-extractor.v1"
    )
    assert resolution.pack["output_contract"]["schema_ref"] == (
        "icoder/CodedEvidence/v11"
    )
    assert resolution.pack["permissions"]["production_writeback_blocked"] is True
    assert resolution.pack["integrity"] != {
        "sha256": "DB_SYNTHESIZED_NO_PACK_FILE"
    }


def test_concurrent_clone_requests_converge_on_one_project_id(
    client: TestClient,
) -> None:
    def invoke() -> tuple[int, dict]:
        response = client.post(f"/api/icoder/agents/{SOURCE_ID}/clone", json={})
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: invoke(), range(4)))

    statuses = [status for status, _ in results]
    bodies = [body for _, body in results]
    assert statuses.count(201) == 1, results
    assert all(status in {200, 201} for status in statuses), results
    assert len({body["project_agent_id"] for body in bodies}) == 1
    assert sum(1 for body in bodies if body["cloned"] is True) == 1


def test_project_expert_binding_is_resolved_and_enters_provider_policy(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clone = _clone(client)
    project_agent_id = clone["project_agent_id"]
    from app.database import AsyncSessionLocal
    from app.models.expert import Expert

    async def _create_project_expert() -> None:
        async with AsyncSessionLocal() as db:
            db.add(Expert(
                id=PROJECT_EXPERT_ID,
                organization_id="org_default1",
                name="Project Evidence Specialist",
                description="Apply the project evidence localization policy.",
                system_prompt="EXPERT_POLICY_SENTINEL: preserve exact evidence spans.",
                category="coding",
                is_prebuilt=False,
                is_published=True,
                created_by="u-test-bypass",
                capabilities=["evidence_localization"],
                tags=["project-test"],
                origin="ICODER_INTERNAL",
                corti_alignment="ICODER_ONLY",
            ))
            await db.commit()

    asyncio.run(_create_project_expert())
    experts_response = client.get("/api/v1/experts")
    assert experts_response.status_code == 200, experts_response.text
    expert = next(
        item for item in experts_response.json()["experts"]
        if item["id"] == PROJECT_EXPERT_ID
    )
    project_prompt = "PROJECT_AGENT_BASE_PROMPT"
    update = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={
            "system_prompt": project_prompt,
            "expert_ids": [expert["id"]],
            "default_expert_id": expert["id"],
        },
    )
    assert update.status_code == 200, update.text

    card_response = client.get(
        f"/api/v2/agentic/agents/{project_agent_id}/.well-known/agent-card.json"
    )
    assert card_response.status_code == 200, card_response.text
    card = card_response.json()
    assert card["name"]
    assert card["supportedInterfaces"][0]["url"].endswith(
        f"/api/v2/agentic/agents/{project_agent_id}/a2a"
    )
    # Discovery describes capabilities but must not disclose tenant prompts or
    # the contents of a bound Expert policy.
    assert project_prompt not in card_response.text
    assert "EXPERT_POLICY_SENTINEL" not in card_response.text

    from icoder_runtime.backends.registry import get_default_registry

    provider = get_default_registry().get(
        "icoder.governed-evidence-extractor.v1"
    )
    original_invoke = provider.invoke
    captured: dict[str, str] = {}

    async def capture_invoke(backend_request, context, **kwargs):
        captured["system_prompt"] = backend_request.system_prompt
        return await original_invoke(backend_request, context, **kwargs)

    monkeypatch.setattr(provider, "invoke", capture_invoke)
    response = client.post(
        f"/api/v1/agents/{project_agent_id}/run",
        json={
            "input": {
                "text": "待核查编码：N18.803。\n病历文本：慢性肾脏病3期。"
            }
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] is False, body
    effective_prompt = captured["system_prompt"]
    assert project_prompt in effective_prompt
    assert "PROJECT_EXPERT_INSTRUCTIONS" in effective_prompt
    assert expert["name"] in effective_prompt
    assert expert["description"] in effective_prompt
    if expert.get("system_prompt"):
        assert expert["system_prompt"] in effective_prompt

    from app.services.agent_runtime_pack import resolve_tenant_runtime

    async def _resolve():
        async with AsyncSessionLocal() as db:
            return await resolve_tenant_runtime(
                project_agent_id, "org_default1", db
            )

    resolution = asyncio.run(_resolve())
    assert resolution.pack is not None
    assert resolution.pack["project_runtime"]["project_expert_ids"] == [
        expert["id"]
    ]
    assert resolution.pack["experts"][0]["expert_id"] == expert["id"]


def test_project_id_executes_over_unified_run_and_owns_trace(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clone = _clone(client)
    project_agent_id = clone["project_agent_id"]
    update = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={"system_prompt": CUSTOM_PROMPT},
    )
    assert update.status_code == 200, update.text

    from icoder_runtime.backends.registry import get_default_registry

    provider = get_default_registry().get(
        "icoder.governed-evidence-extractor.v1"
    )
    original_invoke = provider.invoke
    captured: dict[str, str] = {}

    async def capture_invoke(backend_request, context, **kwargs):
        captured["system_prompt"] = backend_request.system_prompt
        captured["agent_id"] = context.agent_id
        captured["runtime_agent_id"] = context.runtime_agent_id
        return await original_invoke(backend_request, context, **kwargs)

    monkeypatch.setattr(provider, "invoke", capture_invoke)
    response = client.post(
        f"/api/v1/agents/{project_agent_id}/run",
        json={
            "input": {
                "text": "待核查编码：N18.803。\n病历文本：慢性肾脏病3期。"
            },
            "include_trace": True,
            "include_evidence": True,
        },
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["error"] is False, run
    assert run["agent_id"] == project_agent_id
    assert run["result"]["extraction_status"] == "COMPLETED"
    assert run["result"]["backend_provider"] == (
        "icoder.governed-evidence-extractor.v1"
    )
    assert run["schema_ref"] == "icoder/CodedEvidence/v11"
    assert run["result_attestation"]
    assert captured == {
        "system_prompt": CUSTOM_PROMPT,
        "agent_id": project_agent_id,
        "runtime_agent_id": SOURCE_ID,
    }

    trace = client.get(f"/api/runtime/runs/{run['run_id']}/trace")
    assert trace.status_code == 200, trace.text
    trace_body = trace.json()
    timeline = trace_body.get("timeline", trace_body.get("events", []))
    assert timeline
    assert (trace_body.get("summary") or {}).get("agent_id") == project_agent_id


def test_project_id_executes_over_a2a_with_project_attribution(
    client: TestClient,
) -> None:
    clone = _clone(client)
    project_agent_id = clone["project_agent_id"]
    payload = {
        "jsonrpc": "2.0",
        "id": "project-clone-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{
                    "kind": "text",
                    "text": "待核查编码：N18.803。\n病历文本：慢性肾脏病3期。",
                }],
                "metadata": {},
            },
        },
    }
    response = client.post(
        clone["run_url"],
        headers={"A2A-Protocol-Version": "0.3"},
        json=payload,
    )
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    assert result["metadata"]["agent_id"] == project_agent_id
    assert result["metadata"]["backend_provider"] == (
        "icoder.governed-evidence-extractor.v1"
    )
    data_part = next(part for part in result["parts"] if part["kind"] == "data")
    assert data_part["metadata"]["schema_ref"] == "icoder/CodedEvidence/v11"


def test_project_clone_connector_graph_executes_over_a2a_with_one_audit_chain(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove Clone -> customize tools -> A2A as one project-owned runtime."""

    from app.api.agent_connectors import _connector_admin
    from app.database import AsyncSessionLocal
    from app.main import app
    from app.models.agent_connector import ConnectorExecutionAudit
    from app.models.run_history import RunHistoryModel
    from app.services.connector_executor import ConnectorExecutor
    from icoder_runtime.backends.registry import get_default_registry

    clone = _clone(client)
    project_agent_id = clone["project_agent_id"]

    previous_admin_override = app.dependency_overrides.get(_connector_admin)
    had_admin_override = _connector_admin in app.dependency_overrides
    app.dependency_overrides[_connector_admin] = lambda: object()
    try:
        connector_response = client.post(
            f"/api/v2/agentic/agents/{project_agent_id}/connectors",
            json={
                "type": "registry",
                "name": "Project clone governed lookup",
                "description": "Synthetic de-identified project runtime proof.",
                "enabled": True,
                "config": {
                    "registry_key": "memory",
                    "version": "latest",
                    "capabilities": ["lookup"],
                    "total_timeout_seconds": 1.0,
                    "max_response_bytes": 262144,
                },
            },
        )
        assert connector_response.status_code == 201, connector_response.text
        connector = connector_response.json()
        connector_id = connector["id"]
        assert connector["agent_id"] == project_agent_id

        graph_response = client.put(
            f"/api/v2/agentic/agents/{project_agent_id}/connector-graph",
            json={
                "version": "1.0",
                "enabled": True,
                "execution_mode": "sequential",
                "max_concurrency": 4,
                "expected_revision": 0,
                "nodes": [{
                    "id": "lookup",
                    "connector_id": connector_id,
                    "operation": "lookup",
                    "required": True,
                    "idempotent": True,
                    "include_text": True,
                    "input_keys": ["code"],
                    "depends_on": [],
                    "data_classification": "deidentified",
                    "purpose_of_use": "treatment",
                }],
            },
        )
        assert graph_response.status_code == 200, graph_response.text
        assert graph_response.json()["revision"] == 1
    finally:
        if had_admin_override:
            app.dependency_overrides[_connector_admin] = previous_admin_override
        else:
            app.dependency_overrides.pop(_connector_admin, None)

    raw_phone = "13800138000"
    adapter_arguments: list[dict] = []

    async def registry_invoker(_registry_key, _operation, arguments):
        adapter_arguments.append(arguments)
        return {
            "fact": f"synthetic callback {raw_phone}",
            "code": arguments.get("code"),
        }

    provider = get_default_registry().get(
        "icoder.governed-evidence-extractor.v1"
    )
    original_invoke = provider.invoke
    captured: dict = {}

    async def capture_invoke(backend_request, context, **kwargs):
        captured["user_input"] = backend_request.user_input
        captured["extra_context"] = backend_request.extra_context
        captured["agent_id"] = context.agent_id
        captured["runtime_agent_id"] = context.runtime_agent_id
        captured["tenant_id"] = context.tenant_id
        return await original_invoke(backend_request, context, **kwargs)

    monkeypatch.setattr(provider, "invoke", capture_invoke)
    previous_executor = getattr(app.state, "connector_executor", None)
    had_executor = hasattr(app.state, "connector_executor")
    app.state.connector_executor = ConnectorExecutor(
        registry_invoker=registry_invoker,
        policy_authorizer=lambda _connector, _invocation: True,
    )
    payload = {
        "jsonrpc": "2.0",
        "id": "project-clone-connector-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [
                    {
                        "kind": "text",
                        "text": (
                            f"患者联系电话 {raw_phone}。待核查编码：N18.803。"
                            "病历文本：慢性肾脏病3期。"
                        ),
                    },
                    {
                        "kind": "data",
                        "data": {
                            "schema": "icoder/ConnectorGraphInput/v1",
                            "value": {
                                "code": "N18.803",
                                "unselected": "do-not-send",
                            },
                        },
                    },
                ],
                "metadata": {},
            },
        },
    }
    try:
        response = client.post(
            clone["run_url"],
            headers={"A2A-Protocol-Version": "0.3"},
            json=payload,
        )
    finally:
        if had_executor:
            app.state.connector_executor = previous_executor
        elif hasattr(app.state, "connector_executor"):
            delattr(app.state, "connector_executor")

    assert response.status_code == 200, response.text
    envelope = response.json()
    assert "error" not in envelope, envelope
    result = envelope["result"]
    run_id = result["metadata"]["run_id"]
    assert result["metadata"]["agent_id"] == project_agent_id
    assert result["metadata"]["connector_graph_revision"] == 1
    assert captured["agent_id"] == project_agent_id
    assert captured["runtime_agent_id"] == SOURCE_ID
    assert captured["tenant_id"] == "org_default1"
    assert captured["extra_context"]["connector_graph_revision"] == 1
    assert "SERVER_GOVERNED_CONNECTOR_RESULTS_JSON" in captured["user_input"]
    assert adapter_arguments == [{
        "code": "N18.803",
        "text": (
            "患者联系电话 <REDACTED:PHONE>。待核查编码：N18.803。"
            "病历文本：慢性肾脏病3期。"
        ),
    }]
    assert "do-not-send" not in repr(adapter_arguments)
    assert raw_phone not in repr(captured)
    assert raw_phone not in response.text

    trace = client.get(f"/api/runtime/runs/{run_id}/trace")
    assert trace.status_code == 200, trace.text
    assert connector_id in trace.text
    assert raw_phone not in trace.text

    async def _load_audit_chain():
        async with AsyncSessionLocal() as db:
            audit = (
                await db.execute(
                    select(ConnectorExecutionAudit).where(
                        ConnectorExecutionAudit.connector_id == connector_id
                    )
                )
            ).scalar_one()
            run = (
                await db.execute(
                    select(RunHistoryModel).where(
                        RunHistoryModel.run_id == run_id
                    )
                )
            ).scalar_one()
            return audit, run

    audit, run = asyncio.run(_load_audit_chain())
    assert audit.organization_id == "org_default1"
    assert audit.run_id == run_id
    assert audit.status == "success"
    assert run.agent_id == project_agent_id
    assert run.organization_id == "org_default1"
    assert run.status == "COMPLETED"
    assert raw_phone not in run.input_text


def test_clone_provenance_is_immutable_and_cross_tenant_resolution_is_empty(
    client: TestClient,
) -> None:
    clone = _clone(client)
    project_agent_id = clone["project_agent_id"]
    forged = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={
            "config": {
                "source_agent_ref": "icoder/claim-check@1.0.0",
                "permissions": {"production_writeback_blocked": False},
            }
        },
    )
    assert forged.status_code == 422, forged.text
    detail = forged.json()["detail"]
    assert detail["error"] == "clone_runtime_field_immutable"
    assert detail["fields"] == ["permissions", "source_agent_ref"]

    from app.database import AsyncSessionLocal
    from app.services.agent_runtime_pack import resolve_tenant_runtime

    async def _wrong_tenant():
        async with AsyncSessionLocal() as db:
            return await resolve_tenant_runtime(project_agent_id, "org-not-owner", db)

    resolution = asyncio.run(_wrong_tenant())
    assert resolution.db_agent is None
    assert resolution.pack is None
    assert resolution.runtime_agent_id == project_agent_id


def test_dedicated_clone_uses_source_dispatch_but_keeps_project_identity(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import agent_run as agent_run_module

    clone_response = client.post(
        f"/api/icoder/agents/{MEDICAL_SOURCE_ID}/clone", json={}
    )
    assert clone_response.status_code == 201, clone_response.text
    project_agent_id = clone_response.json()["project_agent_id"]

    detail = client.get(
        f"/api/rest/v1/agent_definitions/{project_agent_id}"
    )
    assert detail.status_code == 200, detail.text
    customization = detail.json()["runtime_customization"]
    assert customization["runtime_kind"] == "dedicated"
    assert customization["system_prompt_mode"] == "additive_specialization"
    assert customization["expert_binding_mode"] == "additive_policy"
    assert customization["source_experts_fixed"] is True
    assert customization["source_expert_ids"] == ["coding-expert"]
    assert customization["project_expert_ids"] == []
    captured: list[dict] = []

    async def fake_medical_run(*, agent_id: str, runtime_agent_id: str = "", **kwargs):
        captured.append({
            "agent_id": agent_id,
            "runtime_agent_id": runtime_agent_id,
            "project_runtime_pack": kwargs.get("project_runtime_pack"),
        })
        return agent_run_module.AgentRunResponse(
            agent_id=agent_id,
            run_id=kwargs["run_id"],
            trace_id=kwargs["trace_id"],
            runtime_mode="test_dedicated",
            summary="synthetic dedicated routing proof",
            result={"coding_results": [], "manual_review_required": True},
            manual_review_required=True,
        )

    monkeypatch.setattr(agent_run_module, "_run_medical_coding", fake_medical_run)
    response = client.post(
        f"/api/v1/agents/{project_agent_id}/run",
        json={"input": {"text": "合成去标识病历"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent_id"] == project_agent_id
    assert captured[0]["agent_id"] == project_agent_id
    assert captured[0]["runtime_agent_id"] == MEDICAL_SOURCE_ID
    assert captured[0]["project_runtime_pack"] is not None

    project_policy = "DEDICATED_PROJECT_POLICY_SENTINEL: use explicit chart evidence."
    update = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={"system_prompt": project_policy},
    )
    assert update.status_code == 200, update.text
    customized = client.post(
        f"/api/v1/agents/{project_agent_id}/run",
        json={"input": {"text": "合成去标识病历"}},
    )
    assert customized.status_code == 200, customized.text
    customized_body = customized.json()
    assert customized_body["agent_id"] == project_agent_id
    assert customized_body["error"] is False

    from app.services.dedicated_project_policy import policy_from_runtime_pack

    policy = policy_from_runtime_pack(captured[1]["project_runtime_pack"])
    assert captured[1]["agent_id"] == project_agent_id
    assert captured[1]["runtime_agent_id"] == MEDICAL_SOURCE_ID
    assert policy.enabled is True
    assert policy.prompt_overridden is True
    assert project_policy in policy.instructions
    assert len(policy.digest) == 64
    assert project_policy not in str(policy.safe_metadata())

    assert {
        "agent_id": project_agent_id,
        "runtime_agent_id": MEDICAL_SOURCE_ID,
    } == {
        "agent_id": captured[1]["agent_id"],
        "runtime_agent_id": captured[1]["runtime_agent_id"],
    }


def test_dedicated_clone_keeps_source_expert_graph_and_adds_project_policy(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import agent_run as agent_run_module
    from app.database import AsyncSessionLocal
    from app.models.expert import Expert
    from app.services.agent_runtime_pack import resolve_tenant_runtime

    clone_response = client.post(
        f"/api/icoder/agents/{MEDICAL_SOURCE_ID}/clone",
        json={},
    )
    assert clone_response.status_code == 201, clone_response.text
    project_agent_id = clone_response.json()["project_agent_id"]

    removal = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={"expert_ids": []},
    )
    assert removal.status_code == 422, removal.text
    assert removal.json()["detail"]["error"] == (
        "clone_dedicated_expert_removal_unsupported"
    )
    assert removal.json()["detail"]["source_expert_ids"] == ["coding-expert"]

    expert_sentinel = "DEDICATED_EXPERT_POLICY_SECRET_SENTINEL"

    async def _create_project_expert() -> None:
        async with AsyncSessionLocal() as db:
            db.add(Expert(
                id=PROJECT_EXPERT_ID,
                organization_id="org_default1",
                name="Project Coding Specialist",
                description="Apply the tenant coding evidence policy.",
                system_prompt=expert_sentinel,
                category="coding",
                is_prebuilt=False,
                is_published=True,
                created_by="u-test-bypass",
                capabilities=["coding_evidence"],
                tags=["project-test"],
                origin="ICODER_INTERNAL",
                corti_alignment="ICODER_ONLY",
            ))
            await db.commit()

    asyncio.run(_create_project_expert())
    update = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={
            "expert_ids": [PROJECT_EXPERT_ID],
            "default_expert_id": PROJECT_EXPERT_ID,
        },
    )
    assert update.status_code == 200, update.text
    saved_customization = update.json()["runtime_customization"]
    assert saved_customization["source_expert_ids"] == ["coding-expert"]
    assert saved_customization["project_expert_ids"] == [PROJECT_EXPERT_ID]

    async def _resolve():
        async with AsyncSessionLocal() as db:
            return await resolve_tenant_runtime(
                project_agent_id,
                "org_default1",
                db,
            )

    resolution = asyncio.run(_resolve())
    pack = resolution.pack or {}
    project_runtime = pack["project_runtime"]
    # The dedicated execution graph remains source-owned.
    assert [item["expert_id"] for item in pack["experts"]] == ["coding-expert"]
    assert project_runtime["project_expert_ids"] == [PROJECT_EXPERT_ID]
    assert project_runtime["project_experts"][0]["expert_id"] == PROJECT_EXPERT_ID
    assert project_runtime["project_prompt_overridden"] is False
    assert project_runtime["dedicated_source_experts_fixed"] is True
    assert expert_sentinel in project_runtime["dedicated_project_policy"]
    assert len(project_runtime["dedicated_project_policy_digest"]) == 64

    captured = {}

    async def fake_medical_run(**kwargs):
        captured["pack"] = kwargs["project_runtime_pack"]
        return agent_run_module.AgentRunResponse(
            agent_id=kwargs["agent_id"],
            run_id=kwargs["run_id"],
            trace_id=kwargs["trace_id"],
            runtime_mode="test_dedicated_expert",
            summary="synthetic dedicated Expert policy proof",
            result={"coding_results": [], "manual_review_required": True},
            manual_review_required=True,
        )

    monkeypatch.setattr(agent_run_module, "_run_medical_coding", fake_medical_run)
    run = client.post(
        f"/api/v1/agents/{project_agent_id}/run",
        json={"input": {"text": "合成去标识病历"}},
    )
    assert run.status_code == 200, run.text
    assert run.json()["error"] is False
    runtime = captured["pack"]["project_runtime"]
    assert expert_sentinel in runtime["dedicated_project_policy"]
    assert expert_sentinel not in run.text


def test_dedicated_clone_a2a_reaches_source_handler_with_project_identity(
    client: TestClient,
) -> None:
    clone_response = client.post(
        f"/api/icoder/agents/{MEDICAL_SOURCE_ID}/clone", json={}
    )
    assert clone_response.status_code == 201, clone_response.text
    clone = clone_response.json()
    project_agent_id = clone["project_agent_id"]
    payload = {
        "jsonrpc": "2.0",
        "id": "dedicated-project-clone-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": "合成去标识病历"}],
                "metadata": {},
            },
        },
    }
    response = client.post(
        clone["run_url"],
        headers={"A2A-Protocol-Version": "0.3"},
        json=payload,
    )
    assert response.status_code in {200, 503}, response.text
    envelope = response.json()
    rendered = str(envelope)
    assert "PROVIDER_UNAVAILABLE" not in rendered
    assert "AGENT_NOT_FOUND" not in rendered
    result = envelope.get("result") or {}
    if result:
        assert (result.get("metadata") or {}).get("agent_id") == project_agent_id
        assert (result.get("metadata") or {}).get("source_runtime_agent_id") == (
            MEDICAL_SOURCE_ID
        )
    else:
        # A disabled native coding stack is an expected safe failure in this
        # Windows test profile, but it must still be attributed to the project.
        error_data = (envelope.get("error") or {}).get("data") or {}
        assert error_data.get("agent_id") == project_agent_id, envelope


def test_dedicated_clone_customization_executes_over_a2a_with_safe_trace(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.coding_runtime import CodingResult
    from official_agents.medical_coding.schema import MedicalCodingOutputSchema

    captured = {}

    class FakeDispatcher:
        async def dispatch(self, request):
            captured["request"] = request
            return CodingResult(
                codes=[],
                summary="Synthetic governed coding review.",
                runtime_mode=request.mode.value,
                latency_ms=4,
                llm_provider="deepseek",
                run_id=request.run_id,
                raw_schema=MedicalCodingOutputSchema(
                    review_conclusion="WARNING",
                    manual_review_required=True,
                    confidence=0.0,
                    provider="deepseek",
                    model="deepseek-chat",
                ).to_dict(),
            )

    monkeypatch.setattr(
        "app.coding_runtime.get_dispatcher",
        lambda: FakeDispatcher(),
    )
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )

    clone_response = client.post(
        f"/api/icoder/agents/{MEDICAL_SOURCE_ID}/clone",
        json={},
    )
    assert clone_response.status_code == 201, clone_response.text
    clone = clone_response.json()
    project_agent_id = clone["project_agent_id"]
    sentinel = "A2A_DEDICATED_PROJECT_POLICY_SECRET_SENTINEL"
    update = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={"system_prompt": sentinel},
    )
    assert update.status_code == 200, update.text

    payload = {
        "jsonrpc": "2.0",
        "id": "dedicated-project-policy-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": "合成去标识病历"}],
                "metadata": {},
            },
        },
    }
    response = client.post(
        clone["run_url"],
        headers={"A2A-Protocol-Version": "0.3"},
        json=payload,
    )

    assert response.status_code == 200, response.text
    envelope = response.json()
    message = envelope["result"]
    metadata = message["metadata"]
    runtime_request = captured["request"]
    assert runtime_request.tenant_id == "org_default1"
    assert sentinel in runtime_request.project_policy
    policy_digest = hashlib.sha256(
        runtime_request.project_policy.encode("utf-8")
    ).hexdigest()
    assert metadata["agent_id"] == project_agent_id
    assert metadata["source_runtime_agent_id"] == MEDICAL_SOURCE_ID
    assert metadata["project_policy_digest"] == policy_digest
    assert metadata["project_prompt_overridden"] is True
    assert metadata["dedicated_source_experts_fixed"] is True
    assert sentinel not in response.text

    from app.icoder.agent_runtime.a2a_facade import medical_coding_schema_ref
    from app.services.result_attestation import verify_result_attestation

    data_part = next(
        part for part in message["parts"] if part.get("kind") == "data"
    )
    verify_result_attestation(
        data_part["metadata"]["result_attestation"],
        expected_run_id=metadata["run_id"],
        expected_agent_id=project_agent_id,
        expected_schema_ref=medical_coding_schema_ref(),
        expected_organization_id="org_default1",
        result=data_part["data"],
    )

    trace_response = client.get(
        f"/api/runtime/runs/{metadata['run_id']}/trace"
    )
    assert trace_response.status_code == 200, trace_response.text
    trace_body = trace_response.json()
    assert (trace_body.get("summary") or {}).get("agent_id") == project_agent_id
    assert policy_digest in trace_response.text
    assert MEDICAL_SOURCE_ID in trace_response.text
    assert sentinel not in trace_response.text


def test_cdi_clone_customization_executes_over_a2a_with_safe_trace(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.icoder.agent_runtime import cdi_a2a_handler
    from app.icoder.agent_runtime.cdi_a2a_handler import CDIA2AHandler
    from app.services import llm_service as llm_service_module

    prompts: list[str] = []

    class FakeLLM:
        async def chat(self, *, messages, system_prompt=None, **kwargs):
            prompts.append(str(system_prompt or ""))
            return {"content": "{}", "usage": {}}

    class FakeRunner:
        def __init__(self, *, llm):
            self.llm = llm
            self.stage_traces = {}
            self.expert_traces = []

    contract = CDIA2AHandler._output_contract()
    trace_schema = contract["field_schemas"]["trace_refs"]
    stage_keys = trace_schema["properties"]["stage_trace"]["required"]
    gate_keys = trace_schema["properties"]["gate_results"]["required"]

    class FakeOrchestrator:
        def __init__(self, *, runner, llm):
            assert llm is runner.llm
            self.llm = llm

        def run(self, case):
            asyncio.run(self.llm.chat(
                messages=[{"role": "user", "content": "synthetic chart"}],
                system_prompt="SOURCE CDI SAFETY PROMPT",
            ))
            return SimpleNamespace(
                case_id="CASE-PROJECT-E2E",
                completion_state="REVIEW_REQUIRED",
                encounter_summary=SimpleNamespace(
                    key_points=[],
                    encounter_metadata={
                        "encounter_type": "inpatient",
                        "patient_age": "unknown",
                        "patient_sex": "unknown",
                    },
                ),
                documentation_gaps=[],
                proposed_provider_queries=[],
                query_rewrite_queue=[],
                coding_specificity_checklist=[],
                risk_flags=[],
                specialist_trace=[],
                stage_run_ids={
                    key: f"run-{index}" for index, key in enumerate(gate_keys)
                },
                stage_trace_ids={
                    key: f"trace-{index}" for index, key in enumerate(stage_keys)
                },
                degraded_safety_gates={},
            )

    monkeypatch.setattr(cdi_a2a_handler, "RealCDIRunner", FakeRunner)
    monkeypatch.setattr(cdi_a2a_handler, "CDIOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(cdi_a2a_handler.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm_service_module, "llm_service", FakeLLM())
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )

    clone_response = client.post(
        f"/api/icoder/agents/{CDI_SOURCE_ID}/clone",
        json={},
    )
    assert clone_response.status_code == 201, clone_response.text
    clone = clone_response.json()
    project_agent_id = clone["project_agent_id"]
    sentinel = "CDI_A2A_PROJECT_POLICY_SECRET_SENTINEL"
    update = client.put(
        f"/api/rest/v1/agent_definitions/{project_agent_id}",
        json={"system_prompt": sentinel},
    )
    assert update.status_code == 200, update.text
    customization = update.json()["runtime_customization"]
    assert customization["runtime_kind"] == "dedicated"
    assert customization["source_expert_ids"] == [
        "coding-expert",
        "pubmed-expert",
        "web-search-expert",
        "medical-calculator-expert",
    ]

    payload = {
        "jsonrpc": "2.0",
        "id": "cdi-project-policy-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": "合成去标识 CDI 病历"}],
                "metadata": {},
            },
        },
    }
    response = client.post(
        clone["run_url"],
        headers={"A2A-Protocol-Version": "0.3"},
        json=payload,
    )

    assert response.status_code == 200, response.text
    envelope = response.json()
    message = envelope["result"]
    metadata = message["metadata"]
    assert prompts
    assert prompts[0].startswith("SOURCE CDI SAFETY PROMPT")
    assert sentinel in prompts[0]
    assert "IMMUTABLE_CDI_BOUNDARY" in prompts[0]
    policy_digest = metadata["project_policy_digest"]
    assert len(policy_digest) == 64
    assert metadata["agent_id"] == project_agent_id
    assert metadata["source_runtime_agent_id"] == CDI_SOURCE_ID
    assert metadata["project_prompt_overridden"] is True
    assert sentinel not in response.text

    from app.services.result_attestation import verify_result_attestation

    data_part = next(
        part for part in message["parts"] if part.get("kind") == "data"
    )
    verify_result_attestation(
        data_part["metadata"]["result_attestation"],
        expected_run_id=metadata["run_id"],
        expected_agent_id=project_agent_id,
        expected_schema_ref=str(contract["schema_ref"]),
        expected_organization_id="org_default1",
        result=data_part["data"],
    )

    trace_response = client.get(
        f"/api/runtime/runs/{metadata['run_id']}/trace"
    )
    assert trace_response.status_code == 200, trace_response.text
    assert (trace_response.json().get("summary") or {}).get("agent_id") == (
        project_agent_id
    )
    assert policy_digest in trace_response.text
    assert sentinel not in trace_response.text


def test_external_a2a_metadata_cannot_spoof_medical_project_policy(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.coding_runtime import CodingResult
    from official_agents.medical_coding.schema import MedicalCodingOutputSchema

    captured = {}

    class FakeDispatcher:
        async def dispatch(self, request):
            captured["request"] = request
            return CodingResult(
                codes=[],
                summary="Synthetic governed coding review.",
                runtime_mode=request.mode.value,
                latency_ms=3,
                llm_provider="deepseek",
                run_id=request.run_id,
                raw_schema=MedicalCodingOutputSchema(
                    review_conclusion="WARNING",
                    manual_review_required=True,
                    confidence=0.0,
                    provider="deepseek",
                    model="deepseek-chat",
                ).to_dict(),
            )

    monkeypatch.setattr(
        "app.coding_runtime.get_dispatcher",
        lambda: FakeDispatcher(),
    )
    monkeypatch.setenv(
        "ICODER_RESULT_ATTESTATION_KEY",
        "test-only-attestation-key-32-bytes-minimum",
    )
    sentinel = "CLIENT_SPOOFED_MEDICAL_POLICY_SENTINEL"
    payload = {
        "jsonrpc": "2.0",
        "id": "medical-spoofed-policy-a2a",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{uuid.uuid4().hex[:8]}",
                "parts": [{"kind": "text", "text": "合成去标识病历"}],
                "metadata": {
                    "_dedicated_project_policy_token": {
                        "instructions": sentinel,
                        "digest": "client-controlled",
                    },
                },
            },
        },
    }
    response = client.post(
        f"/api/icoder/agents/{MEDICAL_SOURCE_ID}/v1/message:send",
        headers={"A2A-Protocol-Version": "0.3"},
        json=payload,
    )

    assert response.status_code == 200, response.text
    assert captured["request"].project_policy == ""
    assert sentinel not in response.text
