"""Real TCP + audited Connector E2E for governed external Registry gateways."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, select

from app.models.agent import Agent
from app.models.agent_connector import AgentConnector, ConnectorExecutionAudit
from app.models.organization import Organization
from app.services.agent_connectors import normalize_config
from app.services.connector_executor import (
    ConnectorExecutionError,
    ConnectorExecutor,
    ConnectorInvocation,
)
from app.services.connector_external_registry import GovernedExternalRegistryProvider
from app.services.connector_http_transport import GovernedConnectorHTTPTransport
from app.services.connector_local_adapters import GovernedRegistryAdapter


BACKEND_ROOT = Path(__file__).resolve().parents[3]
TOKEN = "external-registry-fixture-token"
ORG = "org_extreg1"
AGENT = "agt_extreg1"
CONNECTORS = {
    "drugbank": "con_extdrug1",
    "posos": "con_extpos01",
    "web-search": "con_extweb01",
}


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


async def _delete_rows(db) -> None:
    await db.execute(
        delete(ConnectorExecutionAudit).where(
            ConnectorExecutionAudit.connector_id.in_(CONNECTORS.values())
        )
    )
    await db.execute(
        delete(AgentConnector).where(AgentConnector.id.in_(CONNECTORS.values()))
    )
    await db.execute(delete(Agent).where(Agent.id == AGENT))
    await db.execute(delete(Organization).where(Organization.id == ORG))


def _invocation(key: str, query: str) -> ConnectorInvocation:
    return ConnectorInvocation(
        organization_id=ORG,
        agent_id=AGENT,
        connector_id=CONNECTORS[key],
        operation={"drugbank": "lookup", "posos": "guide", "web-search": "search"}[key],
        arguments={"query": query, "max_results": 2},
        run_id=f"run-ext-{key}",
        task_id=f"task-ext-{key}",
        trace_span_id=f"span-ext-{key}",
        data_classification="deidentified",
        purpose_of_use="treatment",
    )


@pytest.mark.timeout(90)
@pytest.mark.asyncio
async def test_real_http_gateway_executes_all_external_registries_and_audits(
    tmp_path: Path,
) -> None:
    import app.database as database

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    log_path = tmp_path / "external-registry-fixture.log"
    log = log_path.open("wb")
    fixture_env = os.environ.copy()
    fixture_env.update({
        "EXTERNAL_REGISTRY_FIXTURE_TOKEN": TOKEN,
        "ICODER_CREDENTIAL_LLM": "",
        "LLM_PROVIDER": "mock",
        "ICODER_ALLOW_EXTERNAL_LLM": "false",
        "ICODER_DISABLE_NATIVE_MEDCODER": "true",
    })
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "tests.fixtures.external_registry_http_gateway:app",
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
        transport = GovernedConnectorHTTPTransport(
            resolver=lambda host, _port: ("127.0.0.1",) if host == "127.0.0.1" else (),
            host_authorizer=lambda host: host == "127.0.0.1",
            allow_loopback_http_for_testing=True,
        )
        provider = GovernedExternalRegistryProvider(
            transport,
            credential_resolver=lambda _service: TOKEN,
            host_authorizer=lambda host: host == "127.0.0.1",
            endpoints={key: f"{base_url}/gateway/{key}" for key in CONNECTORS},
            region="CN",
            web_provider_opt_in=True,
            web_tenant_opt_in_organizations=frozenset({ORG}),
            allow_loopback_http_for_testing=True,
        )
        adapter = GovernedRegistryAdapter(external_registry_provider=provider)
        executor = ConnectorExecutor(
            contextual_registry_invoker=adapter,
            policy_authorizer=lambda _connector, _invocation: True,
        )

        async with database.AsyncSessionLocal() as db:
            await _delete_rows(db)
            db.add(Organization(
                id=ORG, name="External Registry E2E", slug="external-registry-e2e",
                settings={},
            ))
            db.add(Agent(
                id=AGENT, organization_id=ORG, name="External Registry Agent",
                created_by="test", expert_ids=[], aliases=[],
            ))
            await db.flush()
            for key, connector_id in CONNECTORS.items():
                config = normalize_config("registry", {
                    "registry_key": key,
                    "capabilities": [{
                        "drugbank": "lookup", "posos": "guide", "web-search": "search",
                    }[key]],
                    "total_timeout_seconds": 20.0,
                }, enabled=True).config
                db.add(AgentConnector(
                    id=connector_id,
                    organization_id=ORG,
                    agent_id=AGENT,
                    type="registry",
                    name=f"External {key}",
                    enabled=True,
                    config_json=config,
                    created_by="test",
                ))
            await db.commit()

        async with database.AsyncSessionLocal() as db:
            drugbank = await executor.execute(db, _invocation("drugbank", "aspirin"))
            posos = await executor.execute(db, _invocation("posos", "metformin"))
            web = await executor.execute(db, _invocation("web-search", "asthma guidance"))
            await db.commit()
            audits = (
                await db.execute(
                    select(ConnectorExecutionAudit).where(
                        ConnectorExecutionAudit.connector_id.in_(CONNECTORS.values())
                    )
                )
            ).scalars().all()

        assert drugbank.output["drugs"][0]["drugbank_id"] == "DB00945"
        assert posos.output["guidance"][0]["medication"] == "Metformin"
        assert web.output["results"][0]["title"] == "Contract fixture clinical guidance"
        assert len(audits) == 3
        assert all(
            row.status == "success"
            and row.policy_decision == "allow"
            and row.error_code is None
            and row.organization_id == ORG
            for row in audits
        )
        assert _wait_json(f"{base_url}/stats")["counts"] == {
            "drugbank": 1, "posos": 1, "web-search": 1,
        }

        # PHI is rejected before a socket call; a wrong gateway credential is
        # rejected over the real socket and recorded only as a stable code.
        with pytest.raises(ConnectorExecutionError) as phi_denied:
            await provider(
                "drugbank",
                ConnectorInvocation(
                    **{
                        **_invocation("drugbank", "aspirin").__dict__,
                        "data_classification": "phi",
                    }
                ),
            )
        assert phi_denied.value.code == "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED"
        assert _wait_json(f"{base_url}/stats")["counts"]["drugbank"] == 1

        wrong_credential = GovernedExternalRegistryProvider(
            transport,
            credential_resolver=lambda _service: "wrong-token",
            host_authorizer=lambda host: host == "127.0.0.1",
            endpoints={"drugbank": f"{base_url}/gateway/drugbank"},
            region="CN",
            allow_loopback_http_for_testing=True,
        )
        with pytest.raises(ConnectorExecutionError) as unauthorized:
            await wrong_credential("drugbank", _invocation("drugbank", "aspirin"))
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
