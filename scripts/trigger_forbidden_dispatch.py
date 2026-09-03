"""Trigger a scope_check failure for the forbidden screenshot.

Calls dispatch_tool via the in-process path with granted_scopes
missing the required compliance:evaluate scope. The dispatch
emits TOOLS_CALL=FAILED with dispatch_detail.scope_check=failed,
error_stage=scope, error_code=-32012 (MCP_AUTH_FORBIDDEN).
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
os.chdir(Path(__file__).resolve().parent.parent / "backend")

from starlette.requests import Request  # noqa: E402

from app.icoder.mcp.server import dispatch_tool  # noqa: E402
from app.icoder.agent_runtime.orchestrator.run_trace import (  # noqa: E402
    emit_trace_event,
    get_default_store,
)


async def main() -> None:
    store = get_default_store()
    run_id = f"forbidden-{uuid.uuid4().hex[:12]}"
    context_id = f"ctx-{run_id}"

    emit_trace_event(
        run_id=run_id,
        step="user_message_received",
        status="ok",
        safe_metadata={"agent_id": "forbidden-test-agent", "input_parts": 1},
        store=store,
    )

    scope = {"endpoint": "/", "method": "POST", "type": "http"}
    scope.update({"headers": [], "query_params": {}})
    request = Request(scope)
    request.state.context_id = context_id
    request.state.run_id = run_id
    request.state.auth_header = None

    try:
        await dispatch_tool(
            run_id=run_id,
            context_id=context_id,
            tool_name="evaluate_compliance",
            arguments={"coding_set": []},
            request=request,
        )
    except Exception as exc:
        print(f"dispatch_tool raised: {type(exc).__name__}: {exc}")

    emit_trace_event(
        run_id=run_id,
        step="completion",
        status="failed",
        safe_metadata={"reason": "scope_check_failed_demo"},
        store=store,
    )
    print(f"RUN_ID={run_id}")


if __name__ == "__main__":
    asyncio.run(main())
