"""Export FastAPI OpenAPI schema to docs/openapi/openapi.json.

The committed schema is the source of truth for the frontend API contract test
(frontend/src/services/__tests__/apiContract.test.ts), which asserts every
hardcoded path in frontend/src/services/*.ts exists in the OpenAPI schema.

Usage:
    python scripts/export_openapi.py
    python scripts/export_openapi.py --check  # exit 1 if committed schema is stale
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make `app.*` importable when run as a script from backend/
_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

# Output path — committed to repo, used by frontend contract test
_OUTPUT_PATH = _BACKEND_DIR.parent / "docs" / "openapi" / "openapi.json"


def export_schema() -> dict:
    """Import the FastAPI app and dump its OpenAPI schema.

    Adds contract entries for all public A2A paths mounted inside the lifespan
    and therefore not captured by ``app.openapi()`` at module load time.
    """
    # Several legacy loaders still resolve official Agent packs and data files
    # relative to the process CWD. Normalize it here so CI invocation from the
    # repository root produces exactly the same schema as invocation from
    # ``backend/``.
    previous_cwd = Path.cwd()
    os.chdir(_BACKEND_DIR)
    try:
        from app.main import app
        schema = app.openapi()
    finally:
        os.chdir(previous_cwd)
    paths = schema.setdefault("paths", {})
    # These explicit contracts mirror routes mounted during lifespan. Keep the
    # runtime-parity test in sync so OpenAPI cannot advertise an absent route.
    a2a_contracts = {
        "/api/icoder/agents": {
            "get": {
                "summary": "A2A agent discovery (lifespan-mounted)",
                "responses": {"200": {"description": "agent list"}},
            }
        },
        "/api/icoder/agents/{agent_id}/card": {
            "get": {
                "summary": "A2A single AgentCard (lifespan-mounted)",
                "parameters": [
                    {"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {"200": {"description": "agent card"}},
            }
        },
        "/.well-known/agent.json": {
            "get": {
                "summary": "A2A root agent card (lifespan-mounted)",
                "responses": {"200": {"description": "root agent card"}},
            }
        },
        "/.well-known/agent-card.json": {
            "get": {
                "summary": "A2A 1.0 public default Agent Card",
                "operationId": "a2a_well_known_agent_card_v1",
                "responses": {
                    "200": {
                        "description": "Public A2A 1.0 Agent Card",
                        "content": {"application/a2a+json": {"schema": {"type": "object"}}},
                    },
                    "304": {"description": "Agent Card has not changed"},
                    "404": {"description": "Public default Agent not found"},
                },
            }
        },
        "/api/icoder/agents/{agent_id}/v1/message:send": {
            "post": {
                "summary": "Send or continue an authenticated A2A message",
                "operationId": "a2a_message_send_v0_3",
                "security": [{"HTTPBearer": []}],
                "parameters": [
                    {"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "A2A-Protocol-Version", "in": "header", "required": True, "schema": {"type": "string", "enum": ["0.3"]}},
                ],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "responses": {
                    "200": {"description": "A2A JSON-RPC response"},
                    "400": {"description": "Invalid protocol, message or context"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Agent or context not found"},
                    "409": {"description": "Context is no longer active"},
                },
            }
        },
        "/api/icoder/agents/{agent_id}/v1/message:stream": {
            "post": {
                "summary": "Stream an authenticated A2A message response",
                "operationId": "a2a_message_stream_v0_3",
                "security": [{"HTTPBearer": []}],
                "parameters": [
                    {"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "A2A-Protocol-Version", "in": "header", "required": True, "schema": {"type": "string", "enum": ["0.3"]}},
                ],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "responses": {
                    "200": {
                        "description": (
                            "A2A SSE: status, PHI-safe native-provider progress, "
                            "tool/usage telemetry, validated result chunks and finish"
                        ),
                        "content": {
                            "text/event-stream": {
                                "schema": {"type": "string"}
                            }
                        },
                    },
                    "400": {"description": "Invalid protocol or message"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Agent or context not found"},
                },
            }
        },
        "/api/icoder/agents/{agent_id}/v1/contexts/{context_id}": {
            "get": {
                "summary": "Get tenant-scoped A2A context history",
                "operationId": "a2a_get_context_v0_3",
                "security": [{"HTTPBearer": []}],
                "parameters": [
                    {"name": "agent_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "context_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                    {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100}},
                    {"name": "offset", "in": "query", "required": False, "schema": {"type": "integer", "minimum": 0, "default": 0}},
                ],
                "responses": {
                    "200": {"description": "Messages and tasks in the context"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Context not found"},
                },
            }
        },
        "/api/icoder/contexts/{context_id}": {
            "delete": {
                "summary": "Delete and scrub a tenant-scoped A2A context",
                "operationId": "a2a_delete_context_v0_3",
                "security": [{"HTTPBearer": []}],
                "parameters": [
                    {"name": "context_id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}
                ],
                "responses": {
                    "200": {"description": "Context deleted and scrubbed"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Context not found"},
                },
            }
        },
        "/api/icoder/tasks/{task_id}": {
            "get": {
                "summary": "Get tenant-scoped A2A Task state",
                "operationId": "a2a_get_task_v0_3",
                "security": [{"HTTPBearer": []}],
                "parameters": [
                    {"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {"description": "A2A Task state"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Task not found"},
                },
            }
        },
        "/api/icoder/tasks/{task_id}/cancel": {
            "post": {
                "summary": "Cancel a non-terminal tenant-scoped A2A Task",
                "operationId": "a2a_cancel_task_v0_3",
                "security": [{"HTTPBearer": []}],
                "parameters": [
                    {"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "requestBody": {
                    "required": False,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "responses": {
                    "200": {"description": "Canceled A2A Task state"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Task not found"},
                    "409": {"description": "Task cannot be canceled"},
                },
            }
        },
    }
    v1_base = "/api/v2/agentic/agents/{agent_id}"
    v1_path_parameter = {
        "name": "agent_id",
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
    }
    v1_header_parameter = {
        "name": "A2A-Version",
        "in": "header",
        "required": True,
        "schema": {"type": "string", "enum": ["1.0"]},
    }
    v1_security = [{"HTTPBearer": []}]
    v1_json_body = {
        "required": True,
        "content": {"application/a2a+json": {"schema": {"type": "object"}}},
    }
    a2a_contracts.update({
        f"{v1_base}/a2a": {
            "post": {
                "summary": "A2A v1.0 JSON-RPC binding",
                "operationId": "a2a_v1_jsonrpc",
                "security": v1_security,
                "parameters": [v1_path_parameter, v1_header_parameter],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "responses": {
                    "200": {"description": "A2A v1.0 JSON-RPC response or SSE stream"},
                    "401": {"description": "Authentication required"},
                },
            }
        },
        f"{v1_base}/message:send": {
            "post": {
                "summary": "A2A v1.0 HTTP+JSON SendMessage",
                "operationId": "a2a_v1_http_send_message",
                "security": v1_security,
                "parameters": [v1_path_parameter, v1_header_parameter],
                "requestBody": v1_json_body,
                "responses": {
                    "200": {"description": "SendMessageResponse", "content": {"application/a2a+json": {"schema": {"type": "object"}}}},
                    "400": {"description": "google.rpc.Status invalid request"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Task or Agent not found"},
                },
            }
        },
        f"{v1_base}/message:stream": {
            "post": {
                "summary": "A2A v1.0 HTTP+JSON SendStreamingMessage",
                "operationId": "a2a_v1_http_stream_message",
                "security": v1_security,
                "parameters": [v1_path_parameter, v1_header_parameter],
                "requestBody": v1_json_body,
                "responses": {
                    "200": {"description": "StreamResponse SSE", "content": {"text/event-stream": {"schema": {"type": "string"}}}},
                    "400": {"description": "google.rpc.Status invalid request"},
                    "401": {"description": "Authentication required"},
                },
            }
        },
        f"{v1_base}/tasks": {
            "get": {
                "summary": "A2A v1.0 HTTP+JSON ListTasks",
                "operationId": "a2a_v1_http_list_tasks",
                "security": v1_security,
                "parameters": [
                    v1_path_parameter,
                    v1_header_parameter,
                    {"name": "contextId", "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "status", "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "pageSize", "in": "query", "required": False, "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}},
                    {"name": "pageToken", "in": "query", "required": False, "schema": {"type": "string"}},
                    {"name": "statusTimestampAfter", "in": "query", "required": False, "schema": {"type": "string", "format": "date-time"}},
                    {"name": "includeArtifacts", "in": "query", "required": False, "schema": {"type": "boolean", "default": False}},
                ],
                "responses": {
                    "200": {"description": "ListTasksResponse"},
                    "400": {"description": "Invalid filter or page token"},
                    "401": {"description": "Authentication required"},
                },
            }
        },
        f"{v1_base}/tasks/{{task_id}}": {
            "get": {
                "summary": "A2A v1.0 HTTP+JSON GetTask",
                "operationId": "a2a_v1_http_get_task",
                "security": v1_security,
                "parameters": [
                    v1_path_parameter,
                    {"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    v1_header_parameter,
                    {"name": "historyLength", "in": "query", "required": False, "schema": {"type": "integer", "minimum": 0, "maximum": 100}},
                ],
                "responses": {
                    "200": {"description": "Task"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Task not found"},
                },
            }
        },
        f"{v1_base}/tasks/{{task_id}}:subscribe": {
            "get": {
                "summary": "A2A v1.0 HTTP+JSON SubscribeToTask",
                "operationId": "a2a_v1_http_subscribe_task",
                "security": v1_security,
                "parameters": [
                    v1_path_parameter,
                    {"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    v1_header_parameter,
                    {
                        "name": "Last-Event-ID",
                        "in": "header",
                        "required": False,
                        "schema": {"type": "string"},
                        "description": "Resume after the last delivered durable task-event sequence.",
                    },
                    {
                        "name": "afterSequence",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 0, "default": 0},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Durable TaskEvent SSE stream",
                        "content": {"text/event-stream": {"schema": {"type": "string"}}},
                    },
                    "400": {"description": "Invalid resume sequence or protocol version"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Task not found"},
                },
            }
        },
        f"{v1_base}/tasks/{{task_id}}:cancel": {
            "post": {
                "summary": "A2A v1.0 HTTP+JSON CancelTask",
                "operationId": "a2a_v1_http_cancel_task",
                "security": v1_security,
                "parameters": [
                    v1_path_parameter,
                    {"name": "task_id", "in": "path", "required": True, "schema": {"type": "string"}},
                    v1_header_parameter,
                ],
                "requestBody": {"required": False, "content": {"application/a2a+json": {"schema": {"type": "object"}}}},
                "responses": {
                    "200": {"description": "Canceled Task"},
                    "400": {"description": "Task not cancelable"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Task not found"},
                },
            }
        },
        f"{v1_base}/agent-card": {
            "get": {
                "summary": "A2A v1.0 Agent Card",
                "operationId": "a2a_v1_agent_card",
                "security": v1_security,
                "parameters": [v1_path_parameter, v1_header_parameter],
                "responses": {
                    "200": {"description": "AgentCard with JSONRPC and HTTP+JSON interfaces"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Agent not found"},
                },
            }
        },
        f"{v1_base}/.well-known/agent-card.json": {
            "get": {
                "summary": "Authenticated A2A 1.0 tenant Agent Card",
                "operationId": "a2a_v1_standard_agent_card",
                "security": v1_security,
                "parameters": [v1_path_parameter],
                "responses": {
                    "200": {
                        "description": "Tenant-scoped A2A 1.0 Agent Card",
                        "content": {"application/a2a+json": {"schema": {"type": "object"}}},
                    },
                    "304": {"description": "Agent Card has not changed"},
                    "401": {"description": "Authentication required"},
                    "404": {"description": "Agent not found in tenant"},
                },
            }
        },
    })
    for path, spec in a2a_contracts.items():
        paths.setdefault(path, spec)
    return schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI schema")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if committed schema is stale (for CI use)",
    )
    parser.add_argument(
        "--output",
        default=str(_OUTPUT_PATH),
        help=f"Output path (default: {_OUTPUT_PATH})",
    )
    args = parser.parse_args()

    schema = export_schema()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    new_text = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not output_path.exists():
            print(f"FAIL: {output_path} does not exist. Run without --check first.")
            return 1
        existing = output_path.read_text(encoding="utf-8")
        if existing != new_text:
            print(f"FAIL: {output_path} is stale. Re-run without --check to update.")
            return 1
        print(f"OK: {output_path} is up to date")
        return 0

    output_path.write_text(new_text, encoding="utf-8")
    print(f"Wrote {len(new_text)} bytes to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
