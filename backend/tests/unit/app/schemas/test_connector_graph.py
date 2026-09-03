from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.connector_graph import ConnectorGraphSpec


def test_graph_contract_accepts_a_deterministic_dag():
    graph = ConnectorGraphSpec.model_validate({
        "enabled": True,
        "nodes": [
            {
                "id": "lookup",
                "connector_id": "con-graph001",
                "operation": "lookup",
                "input_keys": ["code"],
            },
            {
                "id": "validate",
                "connector_id": "con-graph002",
                "operation": "validate_input",
                "depends_on": ["lookup"],
                "required": False,
            },
        ],
    })

    assert graph.execution_mode == "sequential"
    assert [node.id for node in graph.nodes] == ["lookup", "validate"]


def test_graph_contract_accepts_bounded_parallel_conditions():
    graph = ConnectorGraphSpec.model_validate({
        "enabled": True,
        "execution_mode": "parallel",
        "max_concurrency": 2,
        "nodes": [{
            "id": "lookup",
            "connector_id": "con-graph001",
            "operation": "lookup",
            "when": {
                "input_key": "codingSystem",
                "operator": "in",
                "value": ["ICD-10-CN", "ICD-9-CM-3"],
            },
        }],
    })

    assert graph.execution_mode == "parallel"
    assert graph.max_concurrency == 2
    assert graph.nodes[0].when.input_key == "codingSystem"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "enabled": True,
            "nodes": [
                {"id": "a", "connector_id": "con-graph001", "operation": "lookup", "depends_on": ["b"]},
                {"id": "b", "connector_id": "con-graph002", "operation": "lookup", "depends_on": ["a"]},
            ],
        },
        {
            "enabled": True,
            "execution_mode": "parallel",
            "max_concurrency": 9,
            "nodes": [
                {"id": "a", "connector_id": "con-graph001", "operation": "lookup"},
            ],
        },
        {
            "enabled": True,
            "nodes": [{
                "id": "a",
                "connector_id": "con-graph001",
                "operation": "lookup",
                "when": {"input_key": "route", "operator": "exists", "value": True},
            }],
        },
        {
            "enabled": True,
            "nodes": [{
                "id": "a",
                "connector_id": "con-graph001",
                "operation": "lookup",
                "when": {"input_key": "route", "operator": "in", "value": []},
            }],
        },
        {
            "enabled": True,
            "nodes": [
                {"id": "a", "connector_id": "con-graph001", "operation": "lookup", "depends_on": ["missing"]},
            ],
        },
        {
            "enabled": True,
            "nodes": [
                {
                    "id": "a",
                    "connector_id": "con-graph001",
                    "operation": "lookup",
                    "include_text": True,
                    "data_classification": "non_phi",
                },
            ],
        },
    ],
)
def test_graph_contract_rejects_cycles_unknown_dependencies_and_bad_classification(payload):
    with pytest.raises(ValidationError):
        ConnectorGraphSpec.model_validate(payload)
