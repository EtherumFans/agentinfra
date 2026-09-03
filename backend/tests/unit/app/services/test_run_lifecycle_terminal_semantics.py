from types import SimpleNamespace

import pytest

from app.api.agent_run import _persist_run_history
from app.services.run_lifecycle import RunStatus


def test_provider_continuation_states_are_not_terminal():
    assert RunStatus.is_terminal(RunStatus.CANCEL_NOT_SUPPORTED) is False
    assert RunStatus.is_terminal(RunStatus.CLIENT_ABORTED) is False


def test_actual_completion_and_cancellation_states_are_terminal():
    for status in (
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.COMPLETED_AFTER_CLIENT_ABORT,
    ):
        assert RunStatus.is_terminal(status) is True


@pytest.mark.asyncio
async def test_success_after_client_abort_is_promoted_to_completed_after_abort():
    row = SimpleNamespace(
        status=RunStatus.CLIENT_ABORTED,
        trace_id="trace-start",
        runtime_mode="default",
        input_text="",
    )

    class _Scalars:
        def one_or_none(self):
            return row

    class _Result:
        def scalars(self):
            return _Scalars()

    class _Db:
        async def execute(self, _statement):
            return _Result()

        async def flush(self):
            return None

    response = SimpleNamespace(
        cost={"amount": 0.02},
        error=False,
        run_id="run-aborted",
        agent_id="note-completeness-agent",
        trace_id="trace-final",
        runtime_mode="default",
        latency_ms=25,
        summary="completed",
        error_reason="",
    )

    await _persist_run_history(
        _Db(),
        response=response,
        input_text="safe input",
        user_id="user-1",
        tenant_id="org-1",
        organization_id="org-1",
    )

    assert row.status == RunStatus.COMPLETED_AFTER_CLIENT_ABORT
    assert row.trace_id == "trace-final"
    assert row.cost_usd == 0.02
