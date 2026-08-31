import json
from pathlib import Path

from app.main import app


OPENAPI = Path(__file__).parents[4] / "docs" / "openapi" / "openapi.json"


def test_connector_runtime_and_exported_openapi_contract_match():
    runtime = app.openapi()
    exported = json.loads(OPENAPI.read_text(encoding="utf-8"))
    expected = {
        "/api/v2/agentic/agents/{agent_id}/connector-graph": {
            "get", "put", "delete",
        },
        "/api/v2/agentic/agents/{agent_id}/connectors": {"get", "post"},
        "/api/v2/agentic/agents/{agent_id}/connectors/{connector_id}": {
            "get", "patch", "delete",
        },
        "/api/v2/agentic/agents/{agent_id}/connectors/{connector_id}/credential": {
            "put", "delete",
        },
        "/api/v2/agentic/agents/{agent_id}/memory-consent": {
            "get", "post", "delete",
        },
    }
    for path, methods in expected.items():
        assert methods <= set(runtime["paths"][path])
        assert methods <= set(exported["paths"][path])


def test_connector_openapi_is_typed_and_secret_reference_is_write_only():
    schema = json.loads(OPENAPI.read_text(encoding="utf-8"))
    components = schema["components"]["schemas"]
    assert {
        "ConnectorGraphNode",
        "ConnectorGraphCondition",
        "ConnectorGraphPutRequest",
        "ConnectorGraphResponse",
        "RegistryConnectorConfig",
        "MCPConnectorConfig",
        "AgentConnectorConfig",
        "A2AConnectorConfig",
        "SchemaConnectorConfig",
        "MemoryConsentGrantRequest",
        "MemoryConsentResponse",
    } <= set(components)
    assert components["CredentialBindRequest"]["properties"]["secret_ref"]["writeOnly"] is True
    serialized_response_schema = json.dumps(
        components["ConnectorResponse"], ensure_ascii=False,
    )
    assert "secret_ref" not in serialized_response_schema
    assert "credential_ref" not in serialized_response_schema

    graph_request = components["ConnectorGraphPutRequest"]
    assert graph_request["additionalProperties"] is False
    node_schema = components["ConnectorGraphNode"]
    assert node_schema["additionalProperties"] is False
    assert node_schema["properties"]["connector_id"]["maxLength"] == 12
    assert set(graph_request["properties"]["execution_mode"]["enum"]) == {
        "sequential", "parallel",
    }
    assert graph_request["properties"]["max_concurrency"]["maximum"] == 8
    condition = components["ConnectorGraphCondition"]
    assert condition["additionalProperties"] is False
    assert set(condition["properties"]["operator"]["enum"]) == {
        "exists", "equals", "not_equals", "in",
    }
