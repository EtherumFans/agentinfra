from __future__ import annotations


def test_persist_trace_events_propagates_durable_tenant_identity(monkeypatch) -> None:
    from app.icoder.agent_runtime import a2a_facade

    captured: list[dict] = []

    def _capture(run_id, step, **kwargs):
        captured.append({"run_id": run_id, "step": step, **kwargs})

    monkeypatch.setattr(a2a_facade, "emit_trace_event", _capture)

    a2a_facade.persist_trace_events(
        run_id="run-attributed",
        trace_events=[{
            "step": "completion",
            "status": "ok",
            "duration_ms": 12,
            "metadata": {"agent_id": "ignored-duplicate"},
        }],
        agent_id="note-completeness-agent",
        runtime_mode="a2a_pure_llm",
        trace_id="trace-attributed",
        organization_id="org-123",
        user_id="oauth-client-123",
        actor_id="oauth-client-123",
    )

    assert len(captured) == 1
    metadata = captured[0]["safe_metadata"]
    assert metadata["_organization_id"] == "org-123"
    assert metadata["_user_id"] == "oauth-client-123"
    assert metadata["_actor_id"] == "oauth-client-123"
    assert metadata["_trace_id"] == "trace-attributed"
    assert "trace_id" not in metadata

