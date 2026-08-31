from __future__ import annotations

import asyncio

import pytest

from app.schemas.connector_graph import ConnectorGraphResponse
from app.services.connector_executor import ConnectorExecutionResult
from app.services.connector_graph import execute_connector_graph


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def commit(self):
        return None

    async def rollback(self):
        return None


class _ParallelExecutor:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.started = asyncio.Event()
        self.invocations = []

    async def execute(self, _db, invocation):
        self.invocations.append(invocation)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.active == 2:
            self.started.set()
        await asyncio.wait_for(self.started.wait(), timeout=1.0)
        await asyncio.sleep(0)
        self.active -= 1
        return ConnectorExecutionResult(
            connector_id=invocation.connector_id,
            connector_type="registry",
            operation=invocation.operation,
            output={"node": invocation.trace_span_id},
            attempts=1,
            latency_ms=1,
        )


@pytest.mark.asyncio
async def test_parallel_graph_runs_one_dependency_layer_concurrently(monkeypatch):
    import app.services.connector_graph as graph_module

    monkeypatch.setattr(graph_module.database, "AsyncSessionLocal", _Session)
    executor = _ParallelExecutor()
    graph = ConnectorGraphResponse.model_validate({
        "enabled": True,
        "execution_mode": "parallel",
        "max_concurrency": 2,
        "revision": 7,
        "nodes": [
            {"id": "left", "connector_id": "con-left001", "operation": "lookup"},
            {"id": "right", "connector_id": "con-right01", "operation": "lookup"},
        ],
    })

    result = await execute_connector_graph(
        object(),
        executor=executor,
        graph=graph,
        organization_id="org_default1",
        agent_id="agt-parallel",
        run_id="run-parallel",
        trace_id="trace-parallel",
        safe_text="de-identified",
        safe_extra={},
    )

    assert executor.max_active == 2
    assert result.execution_mode == "parallel"
    assert [node.node_id for node in result.nodes] == ["left", "right"]
    assert all(node.status == "success" for node in result.nodes)


class _SequentialExecutor:
    def __init__(self) -> None:
        self.invocations = []

    async def execute(self, _db, invocation):
        self.invocations.append(invocation)
        return ConnectorExecutionResult(
            connector_id=invocation.connector_id,
            connector_type="registry",
            operation=invocation.operation,
            output={"ok": True},
            attempts=1,
            latency_ms=1,
        )


@pytest.mark.asyncio
async def test_parallel_condition_preserves_order_without_sending_unselected_input(
    monkeypatch,
):
    import app.services.connector_graph as graph_module

    monkeypatch.setattr(graph_module.database, "AsyncSessionLocal", _Session)
    executor = _SequentialExecutor()
    graph = ConnectorGraphResponse.model_validate({
        "enabled": True,
        "execution_mode": "parallel",
        "revision": 3,
        "nodes": [
            {
                "id": "diagnosis",
                "connector_id": "con-diag001",
                "operation": "lookup",
                "input_keys": ["codingSystem"],
                "when": {
                    "input_key": "codingSystem",
                    "operator": "equals",
                    "value": "ICD-10-CN",
                },
            },
            {
                "id": "procedure",
                "connector_id": "con-proc001",
                "operation": "lookup",
                "input_keys": ["codingSystem"],
                "when": {
                    "input_key": "codingSystem",
                    "operator": "equals",
                    "value": "ICD-9-CM-3",
                },
            },
        ],
    })

    result = await execute_connector_graph(
        object(),
        executor=executor,
        graph=graph,
        organization_id="org_default1",
        agent_id="agt-conditional",
        run_id="run-conditional",
        trace_id="trace-conditional",
        safe_text="must-not-be-sent",
        safe_extra={"codingSystem": "ICD-10-CN", "unselected": "private"},
    )

    assert [node.status for node in result.nodes] == ["success", "skipped"]
    assert len(executor.invocations) == 1
    assert executor.invocations[0].arguments == {"codingSystem": "ICD-10-CN"}
    assert result.provider_payload()["nodes"][1] == {
        "node_id": "procedure",
        "status": "skipped",
        "condition_matched": False,
    }
