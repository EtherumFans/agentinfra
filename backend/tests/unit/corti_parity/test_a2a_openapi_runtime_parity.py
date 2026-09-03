import os
from pathlib import Path
import subprocess
import sys
from typing import cast

from app.icoder.agent_runtime.a2a.routes_inbound import build_inbound_router
from app.icoder.agent_runtime.a2a.routes_discovery import build_discovery_router
from app.icoder.agent_runtime.a2a.v1.routes import build_v1_router
from app.icoder.agent_runtime.orchestrator.inbound_handler import InboundHandler
from scripts.export_openapi import export_schema


def test_advertised_a2a_message_routes_exist_in_runtime_router() -> None:
    router = build_inbound_router(cast(InboundHandler, object()))
    runtime_paths = {route.path for route in router.routes}
    advertised_paths = set(export_schema()["paths"])

    for suffix in ("/v1/message:send", "/v1/message:stream"):
        assert suffix in runtime_paths
        assert f"/api/icoder/agents/{{agent_id}}{suffix}" in advertised_paths


def test_advertised_a2a_v1_dual_binding_routes_exist_in_runtime_router() -> None:
    router = build_v1_router(cast(InboundHandler, object()), lambda _agent_id: None)
    runtime_paths = {route.path for route in router.routes}
    advertised_paths = set(export_schema()["paths"])
    expected = {
        "/api/v2/agentic/agents/{agent_id}/a2a",
        "/api/v2/agentic/agents/{agent_id}/message:send",
        "/api/v2/agentic/agents/{agent_id}/message:stream",
        "/api/v2/agentic/agents/{agent_id}/tasks",
        "/api/v2/agentic/agents/{agent_id}/tasks/{task_id}",
        "/api/v2/agentic/agents/{agent_id}/tasks/{task_id}:subscribe",
        "/api/v2/agentic/agents/{agent_id}/tasks/{task_id}:cancel",
        "/api/v2/agentic/agents/{agent_id}/agent-card",
        "/api/v2/agentic/agents/{agent_id}/.well-known/agent-card.json",
    }
    assert expected <= runtime_paths
    assert expected <= advertised_paths

    # The application mounts this router during lifespan, while export_schema()
    # maintains explicit public contracts. Require every runtime A2A v1 path to
    # be exported so a newly added endpoint cannot produce a false-green check.
    runtime_public_paths = {
        path
        for path in runtime_paths
        if path.startswith("/api/v2/agentic/agents/{agent_id}")
    }
    assert runtime_public_paths <= advertised_paths


def test_standard_root_agent_card_is_exported_and_runtime_backed() -> None:
    root, _agents = build_discovery_router(lambda _agent_id: None)
    runtime_paths = {route.path for route in root.routes}
    advertised_paths = set(export_schema()["paths"])
    assert "/.well-known/agent-card.json" in runtime_paths
    assert "/.well-known/agent-card.json" in advertised_paths


def test_current_agentic_trace_and_feedback_methods_are_exported() -> None:
    paths = export_schema()["paths"]
    assert set(paths["/api/v2/agentic/agents/{agent_id}/usage"]) >= {"get"}
    assert set(paths["/api/v2/agentic/contexts/{context_id}/trace"]) >= {"get"}
    assert set(paths[
        "/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/feedback"
    ]) >= {"get", "post", "delete"}
    assert set(paths["/api/v2/agentic/contexts"]) >= {"get"}
    assert set(paths["/api/v2/agentic/contexts/{context_id}"]) >= {
        "get", "delete"
    }
    assert set(paths["/api/v2/agentic/contexts/{context_id}/tasks"]) >= {"get"}
    assert set(paths[
        "/api/v2/agentic/contexts/{context_id}/tasks/{task_id}"
    ]) >= {"get"}
    assert set(paths[
        "/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/artifacts/{artifact_id}"
    ]) >= {"get"}
    assert set(paths[
        "/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/artifacts/"
        "{artifact_id}/objects"
    ]) >= {"get", "post"}
    assert set(paths[
        "/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/artifacts/"
        "{artifact_id}/objects/{object_id}"
    ]) >= {"delete"}
    assert set(paths[
        "/api/v2/agentic/contexts/{context_id}/tasks/{task_id}/artifacts/"
        "{artifact_id}/objects/{object_id}:authorize-download"
    ]) >= {"post"}
    assert set(paths[
        "/api/v2/agentic/artifact-objects/download/{grant_id}"
    ]) >= {"get"}
    assert "/api/v2/agentic/artifact-objects/download" not in paths
    # Current Corti contract uses singular /trace and target.messageId; do not
    # preserve the stale locally-designed /traces or separate message path.
    assert "/api/v2/agentic/contexts/{context_id}/traces" not in paths
    assert not any("/messages/{message_id}/feedback" in path for path in paths)


def test_openapi_export_is_independent_of_invocation_directory(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    output = tmp_path / "openapi.json"
    environment = os.environ.copy()
    environment.update({
        "ICODER_CREDENTIAL_LLM": "",
        "LLM_PROVIDER": "mock",
        "ICODER_ALLOW_EXTERNAL_LLM": "false",
        "ICODER_DISABLE_NATIVE_MEDCODER": "true",
    })
    completed = subprocess.run(
        [
            sys.executable,
            str(repository_root / "backend" / "scripts" / "export_openapi.py"),
            "--output",
            str(output),
        ],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert output.read_bytes() == (
        repository_root / "docs" / "openapi" / "openapi.json"
    ).read_bytes()
