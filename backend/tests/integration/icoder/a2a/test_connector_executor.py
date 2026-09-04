from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
import httpx
from sqlalchemy import delete, select

from app.models.agent import Agent
from app.models.agent_connector import (
    AgentConnector,
    ConnectorCredential,
    ConnectorExecutionAudit,
)
from app.models.organization import Organization
from app.services.agent_connectors import normalize_config
from app.services.connector_executor import (
    ConnectorExecutionError,
    ConnectorExecutor,
    ConnectorInvocation,
    ConnectorTransportError,
)
from app.services.connector_http_transport import (
    GovernedConnectorHTTPTransport,
    canonical_agent_card_digest,
)
from app.services.connector_local_adapters import GovernedRegistryAdapter
from app.services.connector_public_registry import GovernedPublicRegistryProvider
from app.services.connector_runtime import build_connector_runtime


ORG = "org_exec001"
SOURCE = "agt-exec-src"
TARGET = "agt-exec-dst"
CONNECTOR_IDS = {
    "registry": "con-reg-0001",
    "mcp": "con-mcp-0001",
    "agent": "con-agt-0001",
    "a2a": "con-a2a-0001",
    "schema": "con-sch-0001",
}


pytestmark = pytest.mark.postgresql_compat


def _configs() -> dict[str, dict]:
    return {
        "registry": {
            "registry_key": "memory",
            "capabilities": ["lookup"],
            "total_timeout_seconds": 1.0,
        },
        "mcp": {
            "url": "https://8.8.8.8/mcp",
            "auth_policy": "none",
            "tool_allowlist": ["lookup"],
            "max_attempts": 2,
        },
        "agent": {
            "target_agent_id": TARGET,
            "capabilities": ["delegate"],
            "total_timeout_seconds": 1.0,
        },
        "a2a": {
            "endpoint": "https://8.8.8.8/a2a",
            "agent_card_digest": "d" * 64,
            "bindings": ["JSONRPC"],
            "max_attempts": 2,
        },
        "schema": {
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["code"],
                "properties": {"code": {"type": "string"}},
                "additionalProperties": False,
            }
        },
    }


async def _clear_rows(db) -> None:
    await db.execute(
        delete(ConnectorExecutionAudit).where(
            ConnectorExecutionAudit.connector_id.in_(CONNECTOR_IDS.values())
        )
    )
    await db.execute(
        delete(ConnectorCredential).where(
            ConnectorCredential.connector_id.in_(CONNECTOR_IDS.values())
        )
    )
    await db.execute(
        delete(AgentConnector).where(AgentConnector.id.in_(CONNECTOR_IDS.values()))
    )


@pytest_asyncio.fixture(autouse=True)
async def executor_rows():
    import app.database as database

    async with database.AsyncSessionLocal() as db:
        await _clear_rows(db)
        if await db.get(Organization, ORG) is None:
            db.add(
                Organization(
                    id=ORG,
                    name="Connector Executor Org",
                    slug="connector-executor-org",
                    settings={},
                )
            )
        for agent_id, name in ((SOURCE, "Executor Source"), (TARGET, "Executor Target")):
            if await db.get(Agent, agent_id) is None:
                db.add(
                    Agent(
                        id=agent_id,
                        organization_id=ORG,
                        name=name,
                        created_by="test",
                        expert_ids=[],
                        aliases=[],
                    )
                )
        await db.flush()
        for connector_type, raw_config in _configs().items():
            normalized = normalize_config(connector_type, raw_config, enabled=True)
            db.add(
                AgentConnector(
                    id=CONNECTOR_IDS[connector_type],
                    organization_id=ORG,
                    agent_id=SOURCE,
                    type=connector_type,
                    name=f"Executor {connector_type}",
                    enabled=True,
                    config_json=normalized.config,
                    target_agent_id=normalized.target_agent_id,
                    normalized_url=normalized.normalized_url,
                    schema_ref=normalized.schema_ref,
                    schema_digest=normalized.schema_digest,
                    created_by="test",
                )
            )
        await db.commit()
    yield
    async with database.AsyncSessionLocal() as db:
        await _clear_rows(db)
        await db.commit()


def _invocation(
    connector_type: str,
    operation: str,
    arguments: dict | None = None,
    *,
    idempotent: bool = False,
) -> ConnectorInvocation:
    return ConnectorInvocation(
        organization_id=ORG,
        agent_id=SOURCE,
        connector_id=CONNECTOR_IDS[connector_type],
        operation=operation,
        arguments=arguments or {"code": "I21"},
        run_id="run-connector-executor",
        task_id="task-connector-executor",
        trace_span_id="span-connector-executor",
        idempotent=idempotent,
        purpose_of_use="treatment",
    )


def _allow_policy(_connector, _invocation):
    return True


@pytest.mark.asyncio
async def test_all_five_connector_types_execute_through_injected_adapters():
    import app.database as database

    transport_calls = []

    async def transport(request):
        transport_calls.append(request)
        return {"adapter": request.connector_type, "operation": request.operation}

    async def registry(registry_key, operation, arguments):
        return {"registry_key": registry_key, "operation": operation, "count": len(arguments)}

    async def agent(target_agent_id, operation, arguments):
        return {"target_agent_id": target_agent_id, "operation": operation, "accepted": bool(arguments)}

    executor = ConnectorExecutor(
        remote_transport=transport,
        registry_invoker=registry,
        agent_invoker=agent,
        policy_authorizer=_allow_policy,
    )
    invocations = (
        replace(
            _invocation("registry", "lookup"),
            actor_type="api_client",
            actor_id="client-authoritative",
            delegated_subject_id="user-owner-1",
            granted_scopes=frozenset({"agents:run", "coding:validate"}),
            granted_purposes=frozenset({"treatment"}),
        ),
        _invocation("mcp", "lookup"),
        _invocation("agent", "delegate"),
        _invocation("a2a", "SendMessage"),
        _invocation("schema", "validate_input"),
    )
    async with database.AsyncSessionLocal() as db:
        results = [await executor.execute(db, item) for item in invocations]
        await db.commit()
        audits = (
            await db.execute(
                select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.run_id == "run-connector-executor"
                )
            )
        ).scalars().all()

    assert [result.connector_type for result in results] == [
        "registry", "mcp", "agent", "a2a", "schema",
    ]
    assert results[-1].output == {"valid": True, "schema": "input_schema"}
    assert {call.connector_type for call in transport_calls} == {"mcp", "a2a"}
    assert all(call.headers == {} for call in transport_calls)
    assert len(audits) == 5
    assert all(row.status == "success" and row.error_code is None for row in audits)
    assert all(row.organization_id == ORG for row in audits)
    delegated_audit = next(row for row in audits if row.connector_id == CONNECTOR_IDS["registry"])
    assert delegated_audit.actor_type == "api_client"
    assert delegated_audit.actor_id == "client-authoritative"
    assert delegated_audit.delegated_subject_id == "user-owner-1"
    assert delegated_audit.granted_scopes == ["agents:run", "coding:validate"]
    assert delegated_audit.granted_purposes == ["treatment"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "delegated_subject_id,granted_purposes,error_code",
    [
        ("", frozenset({"treatment"}), "CONNECTOR_DELEGATED_SUBJECT_REQUIRED"),
        ("user-owner-1", frozenset(), "CONNECTOR_PURPOSE_FORBIDDEN"),
        ("user-owner-1", frozenset({"payment"}), "CONNECTOR_PURPOSE_FORBIDDEN"),
    ],
)
async def test_machine_connector_cannot_bypass_subject_or_purpose_grants(
    delegated_subject_id, granted_purposes, error_code,
):
    """Executor rechecks machine delegation even if a caller skips Agent Run."""
    import app.database as database

    executor = ConnectorExecutor(
        registry_invoker=lambda *_args: {"unexpected": True},
        policy_authorizer=_allow_policy,
    )
    invocation = replace(
        _invocation("registry", "lookup"),
        actor_type="api_client",
        actor_id="client-authoritative",
        delegated_subject_id=delegated_subject_id,
        granted_scopes=frozenset({"agents:run"}),
        granted_purposes=granted_purposes,
    )
    async with database.AsyncSessionLocal() as db:
        with pytest.raises(ConnectorExecutionError) as denied:
            await executor.execute(db, invocation)
        await db.commit()
        audit = (
            await db.execute(
                select(ConnectorExecutionAudit)
                .where(ConnectorExecutionAudit.connector_id == CONNECTOR_IDS["registry"])
                .order_by(ConnectorExecutionAudit.created_at.desc())
            )
        ).scalars().first()

    assert denied.value.code == error_code
    assert audit is not None
    assert audit.status == "failed"
    assert audit.policy_decision == "deny"
    assert audit.error_code == error_code


@pytest.mark.asyncio
async def test_startup_runtime_executes_local_registry_and_internal_agent(
    monkeypatch,
):
    import app.database as database
    import app.icoder.agent_runtime.provider_a2a_handler as handler_module
    from icoder_runtime.backends.governed_claim_check_provider import (
        GovernedClaimCheckProvider,
    )

    backend_root = Path(__file__).resolve().parents[4]
    claim_pack = json.loads(
        (backend_root / "official_agents" / "claim-check" / "agent_pack.json")
        .read_text(encoding="utf-8")
    )
    claim_input = claim_pack["example_inputs"][0]["input_text"]

    class Registry:
        def resolve_from_agent_pack(self, _pack):
            # Exercise the same deterministic Provider used in production so
            # evidence spans are bound to the route-redacted Connector input.
            return GovernedClaimCheckProvider()

        def get_backend_config(self, _pack):
            return {"llm": {"timeout_seconds": 5}, "tools": {}}

    monkeypatch.setattr(handler_module, "get_default_registry", lambda: Registry())

    async with database.AsyncSessionLocal() as db:
        if await db.get(Agent, "claim-check") is None:
            db.add(Agent(
                id="claim-check",
                organization_id=ORG,
                name="Claim Check",
                created_by="test",
                expert_ids=[],
                aliases=[],
                a2a_enabled=True,
            ))
        registry = await db.get(AgentConnector, CONNECTOR_IDS["registry"])
        registry.config_json = normalize_config("registry", {
            "registry_key": "medical-calculator",
            "capabilities": ["calculate"],
            "total_timeout_seconds": 2.0,
        }, enabled=True).config
        agent = await db.get(AgentConnector, CONNECTOR_IDS["agent"])
        agent.target_agent_id = "claim-check"
        agent.config_json = normalize_config("agent", {
            "target_agent_id": "claim-check",
            "capabilities": ["delegate"],
            "total_timeout_seconds": 5.0,
        }, enabled=True).config
        await db.commit()

    app = SimpleNamespace(state=SimpleNamespace())
    runtime = build_connector_runtime(app)
    app.state.connector_executor = runtime.executor
    try:
        async with database.AsyncSessionLocal() as db:
            calculator = await runtime.executor.execute(
                db,
                _invocation("registry", "calculate", {
                    "calculator": "bmi",
                    "inputs": {"weight_kg": 70, "height_m": 1.75},
                }),
            )
            # Internal delegation records a child Run in its own transaction;
            # release this SQLite writer before exercising that boundary.
            await db.commit()
            delegated = await runtime.executor.execute(
                db,
                _invocation("agent", "delegate", {
                    "text": claim_input,
                }),
            )
            await db.commit()
            audits = (
                await db.execute(select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id.in_([
                        CONNECTOR_IDS["registry"], CONNECTOR_IDS["agent"],
                    ])
                ))
            ).scalars().all()
    finally:
        await runtime.aclose()

    assert calculator.output["output"]["bmi"] == 22.86
    assert delegated.output["target_agent_id"] == "claim-check"
    assert delegated.output["status"] == "completed"
    assert delegated.output["result_attestation"]
    assert any(row.connector_id == CONNECTOR_IDS["registry"] for row in audits)
    assert any(row.connector_id == CONNECTOR_IDS["agent"] for row in audits)


@pytest.mark.asyncio
async def test_persisted_pubmed_registry_uses_governed_http_and_audit():
    """Exercise DB resource -> executor -> registry -> fixed-host HTTP -> audit."""

    import app.database as database

    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/esearch.fcgi"):
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json={"esearchresult": {"count": "1", "idlist": ["12345"]}},
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={
                "result": {
                    "uids": ["12345"],
                    "12345": {
                        "title": "Synthetic deidentified evidence",
                        "source": "Test Journal",
                        "pubdate": "2026",
                        "authors": [{"name": "Test Author"}],
                    },
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=lambda host, port: ("8.8.8.8",),
        client=client,
        host_authorizer=lambda host: host == "eutils.ncbi.nlm.nih.gov",
    )
    provider = GovernedPublicRegistryProvider(
        transport,
        ncbi_contact_email="integration@example.org",
        ncbi_rate_interval_seconds=0,
    )
    adapter = GovernedRegistryAdapter(
        SimpleNamespace(state=SimpleNamespace()),
        public_registry_provider=provider,
    )
    executor = ConnectorExecutor(
        contextual_registry_invoker=adapter,
        policy_authorizer=_allow_policy,
    )

    try:
        async with database.AsyncSessionLocal() as db:
            registry = await db.get(AgentConnector, CONNECTOR_IDS["registry"])
            registry.config_json = normalize_config("registry", {
                "registry_key": "pubmed",
                "capabilities": ["search"],
                "total_timeout_seconds": 2.0,
            }, enabled=True).config
            await db.commit()

        async with database.AsyncSessionLocal() as db:
            invocation = replace(
                _invocation(
                    "registry",
                    "search",
                    {"query": "myocardial infarction", "max_results": 3},
                ),
                data_classification="deidentified",
            )
            result = await executor.execute(db, invocation)
            await db.commit()
            audit = (
                await db.execute(select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id == CONNECTOR_IDS["registry"],
                    ConnectorExecutionAudit.run_id == "run-connector-executor",
                ))
            ).scalars().one()
    finally:
        await client.aclose()

    assert result.output["provider"] == "NCBI PubMed"
    assert result.output["articles"][0]["pmid"] == "12345"
    assert audit.status == "success"
    assert audit.error_code is None
    assert [request.method for request in seen] == ["GET", "GET"]
    assert all(request.url.host == "eutils.ncbi.nlm.nih.gov" for request in seen)
    assert seen[0].url.params["term"] == "myocardial infarction"
    assert seen[0].url.params["email"] == "integration@example.org"


@pytest.mark.asyncio
async def test_credential_adapter_injects_header_but_audit_never_contains_it():
    import app.database as database

    observed_headers = []

    async def credential_resolver(row):
        assert row.secret_ref == "vault://tenant/connectors/executor"
        return {"Authorization": "Bearer fake"}

    async def transport(request):
        observed_headers.append(dict(request.headers))
        return {"ok": True}

    async with database.AsyncSessionLocal() as db:
        connector = await db.get(AgentConnector, CONNECTOR_IDS["mcp"])
        config = dict(connector.config_json)
        config["auth_policy"] = "bearer"
        connector.config_json = normalize_config("mcp", config, enabled=True).config
        credential = ConnectorCredential(
            organization_id=ORG,
            connector_id=connector.id,
            provider="vault",
            secret_ref="vault://tenant/connectors/executor",
            fingerprint="0123456789abcdef",
            secret_type="bearer",
            status="active",
            version=1,
            rotated_at=connector.created_at,
            created_by="test",
        )
        db.add(credential)
        await db.commit()

        executor = ConnectorExecutor(
            remote_transport=transport,
            credential_resolver=credential_resolver,
            policy_authorizer=_allow_policy,
        )
        result = await executor.execute(db, _invocation("mcp", "lookup"))
        await db.commit()
        audit = (
            await db.execute(
                select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id == connector.id
                )
            )
        ).scalar_one()

    assert result.output == {"ok": True}
    assert observed_headers == [{"Authorization": "Bearer fake"}]
    serialized_audit = json.dumps(
        {column.name: getattr(audit, column.name) for column in audit.__table__.columns},
        default=str,
    )
    assert "Bearer fake" not in serialized_audit
    assert "vault://" not in serialized_audit


@pytest.mark.asyncio
async def test_policy_denials_and_execution_time_ssrf_are_audited_without_transport():
    import app.database as database

    transport_calls = 0

    async def transport(_request):
        nonlocal transport_calls
        transport_calls += 1
        return {"ok": True}

    executor = ConnectorExecutor(remote_transport=transport)
    async with database.AsyncSessionLocal() as db:
        registry = await db.get(AgentConnector, CONNECTOR_IDS["registry"])
        registry.enabled = False
        mcp = await db.get(AgentConnector, CONNECTOR_IDS["mcp"])
        tampered = dict(mcp.config_json)
        tampered["url"] = "https://127.0.0.1/mcp"
        mcp.config_json = tampered
        await db.commit()

        with pytest.raises(ConnectorExecutionError) as disabled:
            await executor.execute(db, _invocation("registry", "lookup"))
        assert disabled.value.code == "CONNECTOR_DISABLED"

        with pytest.raises(ConnectorExecutionError) as blocked:
            await executor.execute(db, _invocation("mcp", "lookup"))
        assert blocked.value.code == "CONNECTOR_URL_BLOCKED"
        await db.commit()
        audits = (
            await db.execute(
                select(ConnectorExecutionAudit)
                .where(ConnectorExecutionAudit.connector_id.in_([
                    CONNECTOR_IDS["registry"], CONNECTOR_IDS["mcp"],
                ]))
                .order_by(ConnectorExecutionAudit.connector_id)
            )
        ).scalars().all()

    assert transport_calls == 0
    assert len(audits) == 2
    assert all(row.policy_decision == "deny" for row in audits)
    assert {row.error_code for row in audits} == {
        "CONNECTOR_DISABLED", "CONNECTOR_URL_BLOCKED",
    }


@pytest.mark.asyncio
async def test_retry_budget_is_idempotency_gated_and_circuit_opens():
    import app.database as database

    calls = 0

    async def failing_transport(_request):
        nonlocal calls
        calls += 1
        raise ConnectorTransportError(
            "CONNECTOR_UPSTREAM_503",
            retryable=True,
            http_status_class="5xx",
        )

    executor = ConnectorExecutor(
        remote_transport=failing_transport,
        failure_threshold=2,
        recovery_timeout_seconds=300,
        policy_authorizer=_allow_policy,
    )
    async with database.AsyncSessionLocal() as db:
        with pytest.raises(ConnectorExecutionError) as first:
            await executor.execute(
                db, _invocation("a2a", "GetTask", idempotent=True),
            )
        assert first.value.code == "CONNECTOR_UPSTREAM_503"
        assert calls == 2

        with pytest.raises(ConnectorExecutionError):
            await executor.execute(
                db, _invocation("a2a", "GetTask", idempotent=True),
            )
        assert calls == 4

        with pytest.raises(ConnectorExecutionError) as open_circuit:
            await executor.execute(
                db, _invocation("a2a", "GetTask", idempotent=True),
            )
        assert open_circuit.value.code == "CONNECTOR_CIRCUIT_OPEN"
        assert calls == 4
        await db.commit()
        audits = (
            await db.execute(
                select(ConnectorExecutionAudit)
                .where(ConnectorExecutionAudit.connector_id == CONNECTOR_IDS["a2a"])
                .order_by(ConnectorExecutionAudit.created_at, ConnectorExecutionAudit.id)
            )
        ).scalars().all()

    assert len(audits) == 3
    upstream = [row for row in audits if row.error_code == "CONNECTOR_UPSTREAM_503"]
    circuit_open = [row for row in audits if row.error_code == "CONNECTOR_CIRCUIT_OPEN"]
    assert len(upstream) == 2
    assert all(row.retry_count == 1 for row in upstream)
    assert all(row.http_status_class == "5xx" for row in upstream)
    assert len(circuit_open) == 1
    assert circuit_open[0].policy_decision == "deny"


@pytest.mark.asyncio
async def test_non_idempotent_call_does_not_retry_and_large_response_fails_closed():
    import app.database as database

    calls = 0

    async def retryable_once(_request):
        nonlocal calls
        calls += 1
        raise ConnectorTransportError("CONNECTOR_TRANSIENT", retryable=True)

    async with database.AsyncSessionLocal() as db:
        executor = ConnectorExecutor(
            remote_transport=retryable_once,
            policy_authorizer=_allow_policy,
        )
        with pytest.raises(ConnectorExecutionError):
            await executor.execute(db, _invocation("mcp", "lookup", idempotent=False))
        assert calls == 1

        connector = await db.get(AgentConnector, CONNECTOR_IDS["mcp"])
        config = dict(connector.config_json)
        config["max_response_bytes"] = 1024
        connector.config_json = normalize_config("mcp", config, enabled=True).config
        await db.flush()

        async def oversized(_request):
            return {"payload": "x" * 2048}

        executor = ConnectorExecutor(
            remote_transport=oversized,
            policy_authorizer=_allow_policy,
        )
        with pytest.raises(ConnectorExecutionError) as raised:
            await executor.execute(db, _invocation("mcp", "lookup"))
        assert raised.value.code == "CONNECTOR_RESPONSE_TOO_LARGE"
        await db.commit()


@pytest.mark.asyncio
async def test_schema_validation_failure_and_oversized_arguments_are_audited():
    import app.database as database

    executor = ConnectorExecutor()
    async with database.AsyncSessionLocal() as db:
        with pytest.raises(ConnectorExecutionError) as invalid_schema_input:
            await executor.execute(
                db,
                _invocation("schema", "validate_input", {"unexpected": True}),
            )
        assert invalid_schema_input.value.code == "CONNECTOR_SCHEMA_VALIDATION_FAILED"

        with pytest.raises(ConnectorExecutionError) as oversized:
            await executor.execute(
                db,
                _invocation("schema", "validate_input", {"code": "x" * 70_000}),
            )
        assert oversized.value.code == "CONNECTOR_ARGUMENTS_TOO_LARGE"
        await db.commit()
        audits = (
            await db.execute(
                select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id == CONNECTOR_IDS["schema"]
                )
            )
        ).scalars().all()

    assert len(audits) == 2
    assert {row.error_code for row in audits} == {
        "CONNECTOR_SCHEMA_VALIDATION_FAILED",
        "CONNECTOR_ARGUMENTS_TOO_LARGE",
    }


@pytest.mark.asyncio
async def test_remote_execution_requires_explicit_data_policy_authorizer():
    import app.database as database

    calls = 0

    async def transport(_request):
        nonlocal calls
        calls += 1
        return {"ok": True}

    executor = ConnectorExecutor(remote_transport=transport)
    async with database.AsyncSessionLocal() as db:
        with pytest.raises(ConnectorExecutionError) as raised:
            await executor.execute(
                db,
                _invocation("mcp", "lookup"),
            )
        assert raised.value.code == "CONNECTOR_DATA_POLICY_NOT_CONFIGURED"
        await db.commit()
        audit = (
            await db.execute(
                select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id == CONNECTOR_IDS["mcp"]
                )
            )
        ).scalar_one()

    assert calls == 0
    assert audit.policy_decision == "deny"
    assert audit.error_code == "CONNECTOR_DATA_POLICY_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_timeout_and_target_agent_are_revalidated_at_execution_time():
    import app.database as database

    agent_calls = 0

    async def slow_registry(_key, _operation, _arguments):
        await asyncio.sleep(0.2)
        return {"ok": True}

    async def agent_invoker(_target, _operation, _arguments):
        nonlocal agent_calls
        agent_calls += 1
        return {"ok": True}

    executor = ConnectorExecutor(
        registry_invoker=slow_registry,
        agent_invoker=agent_invoker,
        policy_authorizer=_allow_policy,
    )
    async with database.AsyncSessionLocal() as db:
        registry = await db.get(AgentConnector, CONNECTOR_IDS["registry"])
        registry_config = dict(registry.config_json)
        registry_config["total_timeout_seconds"] = 0.1
        registry.config_json = normalize_config(
            "registry", registry_config, enabled=True,
        ).config

        agent = await db.get(AgentConnector, CONNECTOR_IDS["agent"])
        agent_config = dict(agent.config_json)
        agent_config["target_agent_id"] = "agt-miss-001"
        agent.config_json = normalize_config("agent", agent_config, enabled=True).config
        # Keep the indexed FK projection valid while simulating a stale
        # configuration target. Execution must revalidate the config value.
        await db.flush()

        with pytest.raises(ConnectorExecutionError) as timeout:
            await executor.execute(db, _invocation("registry", "lookup"))
        assert timeout.value.code == "CONNECTOR_TIMEOUT"

        with pytest.raises(ConnectorExecutionError) as missing_target:
            await executor.execute(db, _invocation("agent", "delegate"))
        assert missing_target.value.code == "CONNECTOR_TARGET_AGENT_NOT_FOUND"
        await db.commit()
        audits = (
            await db.execute(
                select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id.in_([
                        CONNECTOR_IDS["registry"], CONNECTOR_IDS["agent"],
                    ])
                )
            )
        ).scalars().all()

    assert agent_calls == 0
    assert {row.error_code for row in audits} == {
        "CONNECTOR_TIMEOUT", "CONNECTOR_TARGET_AGENT_NOT_FOUND",
    }


@pytest.mark.asyncio
async def test_audit_identifiers_and_adapter_error_codes_cannot_carry_free_text():
    import app.database as database

    async def malicious_adapter(_request):
        raise ConnectorTransportError(
            "raw downstream exception text",
            retryable=False,
            http_status_class="raw-status",
        )

    executor = ConnectorExecutor(
        remote_transport=malicious_adapter,
        policy_authorizer=_allow_policy,
    )
    async with database.AsyncSessionLocal() as db:
        invalid_id = ConnectorInvocation(
            organization_id=ORG,
            agent_id=SOURCE,
            connector_id=CONNECTOR_IDS["schema"],
            operation="validate_input",
            arguments={"code": "I21"},
            run_id="patient free text",
        )
        with pytest.raises(ConnectorExecutionError) as invalid:
            await executor.execute(db, invalid_id)
        assert invalid.value.code == "CONNECTOR_AUDIT_IDENTIFIER_INVALID"

        with pytest.raises(ConnectorExecutionError) as sanitized:
            await executor.execute(db, _invocation("mcp", "lookup"))
        assert sanitized.value.code == "CONNECTOR_FAILURE"
        await db.commit()
        audits = (
            await db.execute(
                select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id.in_([
                        CONNECTOR_IDS["schema"], CONNECTOR_IDS["mcp"],
                    ])
                )
            )
        ).scalars().all()

    invalid_audit = next(
        row for row in audits if row.error_code == "CONNECTOR_AUDIT_IDENTIFIER_INVALID"
    )
    sanitized_audit = next(row for row in audits if row.error_code == "CONNECTOR_FAILURE")
    assert invalid_audit.run_id is None
    assert sanitized_audit.http_status_class is None
    serialized = json.dumps(
        [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in audits
        ],
        default=str,
    )
    assert "raw downstream" not in serialized
    assert "patient free text" not in serialized


@pytest.mark.asyncio
async def test_per_connector_concurrency_limit_is_enforced():
    import app.database as database

    active = 0
    peak = 0

    async def transport(_request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.02)
            return {"ok": True}
        finally:
            active -= 1

    executor = ConnectorExecutor(
        remote_transport=transport,
        policy_authorizer=_allow_policy,
    )
    async with database.AsyncSessionLocal() as db:
        connector = await db.get(AgentConnector, CONNECTOR_IDS["mcp"])
        config = dict(connector.config_json)
        config["concurrency_limit"] = 1
        connector.config_json = normalize_config("mcp", config, enabled=True).config
        await db.flush()
        results = await asyncio.gather(
            *[
                executor.execute(
                    db,
                    ConnectorInvocation(
                        organization_id=ORG,
                        agent_id=SOURCE,
                        connector_id=CONNECTOR_IDS["mcp"],
                        operation="lookup",
                        arguments={"code": f"I2{index}"},
                        run_id=f"run-concurrency-{index}",
                    ),
                )
                for index in range(3)
            ]
        )
        await db.commit()

    assert len(results) == 3
    assert peak == 1


@pytest.mark.asyncio
async def test_persisted_mcp_and_a2a_execute_through_governed_protocol_transport():
    """Prove the DB executor and real protocol adapter work as one boundary."""

    import app.database as database

    methods: list[str] = []
    agent_card = {
        "name": "Integration Agent",
        "description": "Synthetic",
        "version": "1.0.0",
        "supportedInterfaces": [{
            "url": "https://8.8.8.8/a2a",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }],
        "capabilities": {},
        "skills": [],
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            methods.append("agent-card")
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json=agent_card,
            )
        body = json.loads(request.content or b"{}")
        methods.append(str(body.get("method") or ""))
        if body.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/json",
                    "Mcp-Session-Id": "integration-session",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"protocolVersion": "2025-03-26"},
                },
            )
        if body.get("method") == "notifications/initialized":
            return httpx.Response(202, content=b"")
        if body.get("method") == "tools/call":
            return httpx.Response(
                200,
                headers={"Content-Type": "application/json"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"tool": body["params"]["name"], "ok": True},
                },
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "application/a2a+json"},
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"kind": "message", "messageId": "msg-integration"},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    transport = GovernedConnectorHTTPTransport(
        resolver=lambda host, port: ("8.8.8.8",),
        client=client,
    )
    executor = ConnectorExecutor(
        remote_transport=transport,
        policy_authorizer=_allow_policy,
    )
    async with database.AsyncSessionLocal() as db:
        a2a_row = await db.get(AgentConnector, CONNECTOR_IDS["a2a"])
        a2a_config = dict(a2a_row.config_json)
        a2a_config["agent_card_digest"] = canonical_agent_card_digest(agent_card)
        a2a_row.config_json = normalize_config(
            "a2a", a2a_config, enabled=True,
        ).config
        await db.flush()
        mcp = await executor.execute(db, _invocation("mcp", "lookup"))
        a2a = await executor.execute(db, _invocation("a2a", "GetTask"))
        await db.commit()
        audits = (
            await db.execute(
                select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id.in_([
                        CONNECTOR_IDS["mcp"], CONNECTOR_IDS["a2a"],
                    ])
                )
            )
        ).scalars().all()
    await client.aclose()

    assert mcp.output == {"tool": "lookup", "ok": True}
    assert a2a.output["messageId"] == "msg-integration"
    assert methods == [
        "initialize", "notifications/initialized", "tools/call", "agent-card", "GetTask",
    ]
    assert len(audits) == 2
    assert all(row.status == "success" for row in audits)
