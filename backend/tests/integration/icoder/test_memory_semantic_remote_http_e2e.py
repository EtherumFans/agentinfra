"""Real TCP + encrypted/audited Connector E2E for semantic Memory."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, func, select

from app.models.agent import Agent
from app.models.agent_connector import AgentConnector, ConnectorExecutionAudit
from app.models.memory import ConversationMemory, MemoryConsent
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services.agent_connectors import normalize_config
from app.services.connector_executor import (
    ConnectorExecutionError,
    ConnectorExecutor,
    ConnectorInvocation,
)
from app.services.connector_http_transport import GovernedConnectorHTTPTransport
from app.services.connector_local_adapters import GovernedRegistryAdapter
from app.services.connector_memory_semantic import GovernedMemoryEmbeddingProvider
from app.services.connector_memory_store import GovernedMemoryStore
from app.services.phi_encryption import decrypt_phi, encrypt_phi, is_encrypted_value
from app.agents.experts.memory_expert import retrieve_persistent_async


BACKEND_ROOT = Path(__file__).resolve().parents[3]
TOKEN = "memory-semantic-fixture-token"
ORG = "org_memsem1"
USER = "u-mem-sem01"
AGENT = "agt-memsem1"
CONNECTOR = "con-memsem1"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_json(url: str, *, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=1.0, trust_env=False)
            if response.status_code == 200:
                return response.json()
        except (httpx.HTTPError, ValueError):
            pass
        time.sleep(0.1)
    raise AssertionError(f"fixture did not answer at {url}")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _invocation(operation: str, arguments: dict, *, run_id: str) -> ConnectorInvocation:
    return ConnectorInvocation(
        organization_id=ORG,
        agent_id=AGENT,
        connector_id=CONNECTOR,
        operation=operation,
        arguments=arguments,
        run_id=run_id,
        task_id=f"task-{run_id}",
        trace_span_id=f"span-{run_id}"[:64],
        data_classification="deidentified",
        purpose_of_use="treatment",
        actor_type="user",
        actor_id=USER,
    )


async def _delete_rows(db) -> None:
    await db.execute(delete(ConnectorExecutionAudit).where(
        ConnectorExecutionAudit.connector_id == CONNECTOR,
    ))
    await db.execute(delete(ConversationMemory).where(
        ConversationMemory.organization_id == ORG,
    ))
    await db.execute(delete(MemoryConsent).where(
        MemoryConsent.organization_id == ORG,
    ))
    await db.execute(delete(AgentConnector).where(AgentConnector.id == CONNECTOR))
    await db.execute(delete(Agent).where(Agent.id == AGENT))
    await db.execute(delete(Organization).where(Organization.id == ORG))
    await db.execute(delete(User).where(User.id == USER))


@pytest.mark.timeout(90)
@pytest.mark.asyncio
async def test_semantic_memory_real_tcp_encryption_audit_and_revocation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.database as database

    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", Fernet.generate_key().decode())
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "memory-semantic-fixture.log"
    log = log_path.open("wb")
    fixture_env = os.environ.copy()
    fixture_env.update({
        "MEMORY_SEMANTIC_FIXTURE_TOKEN": TOKEN,
        "ICODER_CREDENTIAL_LLM": "",
        "LLM_PROVIDER": "mock",
        "ICODER_ALLOW_EXTERNAL_LLM": "false",
        "ICODER_DISABLE_NATIVE_MEDCODER": "true",
    })
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "tests.fixtures.memory_semantic_http_worker:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "warning",
        ],
        cwd=BACKEND_ROOT,
        env=fixture_env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    transport: GovernedConnectorHTTPTransport | None = None
    try:
        ready = _wait_json(f"{base_url}/readyz")
        assert ready["ready"] is True
        assert ready["native_modules_loaded"] is False
        transport = GovernedConnectorHTTPTransport(
            resolver=lambda host, _port: ("127.0.0.1",) if host == "127.0.0.1" else (),
            host_authorizer=lambda host: host == "127.0.0.1",
            allow_loopback_http_for_testing=True,
        )
        provider = GovernedMemoryEmbeddingProvider(
            transport,
            credential_resolver=lambda _service: TOKEN,
            host_authorizer=lambda host: host == "127.0.0.1",
            endpoint=f"{base_url}/v1/embed",
            allow_loopback_http_for_testing=True,
        )
        store = GovernedMemoryStore(
            semantic_provider=provider,
            semantic_required=True,
        )
        executor = ConnectorExecutor(
            contextual_registry_invoker=GovernedRegistryAdapter(memory_store=store),
            policy_authorizer=lambda _connector, _invocation: True,
        )

        async with database.AsyncSessionLocal() as db:
            await _delete_rows(db)
            db.add(User(
                id=USER,
                username="memory-semantic-user",
                email="memory-semantic@example.test",
                hashed_password="not-used",
                full_name="Memory Semantic User",
                role=UserRole.ADMIN,
                is_active=True,
                is_verified=True,
            ))
            db.add(Organization(
                id=ORG, name="Memory Semantic E2E", slug="memory-semantic-e2e",
                settings={},
            ))
            db.add(Agent(
                id=AGENT, organization_id=ORG, name="Semantic Memory Agent",
                created_by="test", expert_ids=[], aliases=[],
            ))
            await db.flush()
            config = normalize_config("registry", {
                "registry_key": "memory",
                "capabilities": ["remember", "recall", "forget"],
                "total_timeout_seconds": 20.0,
            }, enabled=True).config
            db.add(AgentConnector(
                id=CONNECTOR,
                organization_id=ORG,
                agent_id=AGENT,
                type="registry",
                name="Semantic Memory",
                enabled=True,
                config_json=config,
                created_by="test",
            ))
            await store.grant(
                db,
                organization_id=ORG,
                user_id=USER,
                agent_id=AGENT,
                purpose_of_use="treatment",
                retention_days=30,
                expires_in_days=30,
            )
            await db.commit()

        async with database.AsyncSessionLocal() as db:
            remembered = await executor.execute(
                db,
                _invocation(
                    "remember",
                    {"content": "血糖控制欠佳，长期口服二甲双胍", "role": "user"},
                    run_id="run-memory-remember",
                ),
            )
            recalled = await executor.execute(
                db,
                _invocation(
                    "recall",
                    {"query": "糖尿病用药情况，联系电话13800138000", "top_k": 5},
                    run_id="run-memory-recall",
                ),
            )
            await db.commit()
            memory_id = remembered.output["memory_id"]
            row = await db.get(ConversationMemory, memory_id)
            assert row is not None
            assert is_encrypted_value(row.key_facts)
            assert "contract-multilingual-clinical" not in row.key_facts
            metadata = json.loads(decrypt_phi(row.key_facts) or "{}")
            assert len(metadata["_embedding"]) == 16
            audits = (
                await db.execute(select(ConnectorExecutionAudit).where(
                    ConnectorExecutionAudit.connector_id == CONNECTOR,
                ))
            ).scalars().all()

            assert remembered.output["semantic_index_status"] == "indexed"
            assert recalled.output["returned"] == 1
            assert recalled.output["retrieval_mode"] == (
                "PERSISTENT_ENCRYPTED_REMOTE_SEMANTIC"
            )
            assert recalled.output["semantic_coverage"] == 1.0
            assert recalled.output["query_redaction_applied"] is True
            assert recalled.output["memories"][0]["memory_id"] == memory_id
            assert len(audits) == 2
            assert all(row.status == "success" for row in audits)

            expert_result = await retrieve_persistent_async(
                "糖尿病管理",
                db=db,
                store=store,
                organization_id=ORG,
                user_id=USER,
                agent_id=AGENT,
            )
            assert expert_result.retrieval_mode == (
                "PERSISTENT_ENCRYPTED_REMOTE_SEMANTIC"
            )
            assert expert_result.matches[0]["memory_id"] == memory_id

            metadata["_embedding_version"] = "stale-version"
            row.key_facts = encrypt_phi(json.dumps(metadata))
            await db.commit()
            with pytest.raises(ConnectorExecutionError) as stale:
                await store.invoke(
                    db,
                    _invocation(
                        "recall", {"query": "糖尿病用药情况"},
                        run_id="run-memory-stale",
                    ),
                )
            assert stale.value.code == "CONNECTOR_MEMORY_SEMANTIC_INDEX_INCOMPLETE"

            consent, deleted = await store.revoke(
                db,
                organization_id=ORG,
                user_id=USER,
                agent_id=AGENT,
                purpose_of_use="treatment",
            )
            await db.commit()
            assert consent is not None and consent.status == "revoked"
            assert deleted == 1
            assert await db.get(ConversationMemory, memory_id) is None
            remaining = await db.scalar(select(func.count(ConversationMemory.id)).where(
                ConversationMemory.organization_id == ORG,
            ))
            assert remaining == 0

        stats = _wait_json(f"{base_url}/stats")
        assert stats["calls"] == 4
        assert stats["saw_sensitive_phone"] is False
        assert stats["last_request_keys"] == ["contract", "normalize", "texts"]

        wrong_provider = GovernedMemoryEmbeddingProvider(
            transport,
            credential_resolver=lambda _service: "wrong-token",
            host_authorizer=lambda host: host == "127.0.0.1",
            endpoint=f"{base_url}/v1/embed",
            allow_loopback_http_for_testing=True,
        )
        with pytest.raises(ConnectorExecutionError) as unauthorized:
            await wrong_provider.embed("糖尿病")
        assert unauthorized.value.code == "CONNECTOR_UPSTREAM_401"
    except Exception:
        log.flush()
        pytest.fail(
            f"fixture_exit={process.poll()}\n"
            + log_path.read_text(encoding="utf-8", errors="replace")[-5000:],
            pytrace=True,
        )
    finally:
        if transport is not None:
            await transport.aclose()
        async with database.AsyncSessionLocal() as db:
            await _delete_rows(db)
            await db.commit()
        _stop(process)
        log.close()
