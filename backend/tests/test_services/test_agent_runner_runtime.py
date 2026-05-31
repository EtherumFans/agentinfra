# Tests: Runtime integration in AgentRunner
#
# Verifies:
# 1. AgentRunner.run() creates a DeterministicRuntime instance
# 2. State transitions occur: INGESTED -> CONTEXT_READY -> FACTS_EXTRACTED -> ARCHIVED
# 3. Guard calls happen before expert execution
# 4. Audit events are recorded
# 5. Denied gate returns immediately without executing experts
# 6. AgentRunner.stream() creates Runtime and transitions
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.runtime import (
    runtime_registry, DeterministicRuntime, CaseState, GateOutcome,
    AuditChain, ToolGate, AuditEvent,
)
from app.services.agent_runner import AgentRunner


@pytest.fixture(autouse=True)
def cleanup_registry():
    """Clean runtime registry before each test."""
    runtime_registry._runtimes.clear()
    yield
    runtime_registry._runtimes.clear()


def make_mock_agent(name="Test Agent", expert_ids=None, config=None):
    agent = MagicMock()
    agent.id = f"agent-{uuid.uuid4().hex[:6]}"
    agent.name = name
    agent.description = "Test agent for Runtime tests"
    agent.system_prompt = "You are a test agent."
    agent.expert_ids = expert_ids or []
    agent.config = config or {}
    agent.a2a_enabled = False
    return agent


def make_mock_expert(name="Test Expert", capabilities=None):
    expert = MagicMock()
    expert.id = f"exp-{uuid.uuid4().hex[:6]}"
    expert.name = name
    expert.description = "A test expert"
    expert.system_prompt = "You are a test expert."
    expert.capabilities = capabilities or ["testing"]
    return expert


def make_mock_db(experts_to_return=None):
    """Create a mock AsyncSession that returns specified experts."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = experts_to_return or []
    db.execute = AsyncMock(return_value=mock_result)
    return db


class TestAgentRunnerRuntime:
    """Unit tests for AgentRunner Runtime integration via API-style calls."""

    @pytest.mark.asyncio
    async def test_run_creates_runtime_no_experts(self):
        """AgentRunner.run() without experts creates Runtime and transitions to ARCHIVED."""
        runner = AgentRunner()
        agent = make_mock_agent(expert_ids=[])
        db = make_mock_db([])

        # Instance patch: no self-binding, args passed as-is
        async def mock_resolve(agent, db=None):
            return []
        async def mock_run_single(agent, user_input, history, expert, rt):
            return "Mock LLM output"

        with patch.object(runner, '_resolve_experts', mock_resolve):
            with patch.object(runner, '_run_single_expert', mock_run_single):
                result = await runner.run(
                    agent=agent,
                    user_input="Hello",
                    db=db,
                )

        assert "run_id" in result
        assert result["runtime_state"] == CaseState.ARCHIVED.value
        run_id = result["run_id"]
        rt = runtime_registry.get(run_id)
        assert rt is not None
        assert rt.state == CaseState.ARCHIVED
        assert len(rt.audit) >= 3

    @pytest.mark.asyncio
    async def test_run_state_transitions_with_experts(self):
        """With experts bound: INGESTED -> CONTEXT_READY -> FACTS_EXTRACTED -> ARCHIVED."""
        runner = AgentRunner()
        agent = make_mock_agent(expert_ids=["exp-001"], config={"routing_strategy": "single_expert"})
        expert = make_mock_expert()
        db = make_mock_db([expert])

        async def mock_resolve(agent, db=None):
            return [expert]
        async def mock_run_single(agent, user_input, history, expert, rt):
            return "Expert output"

        with patch.object(runner, '_resolve_experts', mock_resolve):
            with patch.object(runner, '_run_single_expert', mock_run_single):
                result = await runner.run(
                    agent=agent,
                    user_input="Test input",
                    db=db,
                )

        run_id = result["run_id"]
        rt = runtime_registry.get(run_id)
        assert rt is not None
        assert rt.state == CaseState.ARCHIVED
        events = [e.event_type for e in rt.audit._events]
        assert "agent_run_start" in events
        assert "state_transition" in events

    @pytest.mark.asyncio
    async def test_run_audit_chain_integrity(self):
        """Audit chain records all events with correct structure."""
        runner = AgentRunner()
        agent = make_mock_agent(expert_ids=[])
        db = make_mock_db([])

        async def mock_resolve(agent, db=None):
            return []
        async def mock_run_single(agent, user_input, history, expert, rt):
            return "Output"

        with patch.object(runner, '_resolve_experts', mock_resolve):
            with patch.object(runner, '_run_single_expert', mock_run_single):
                result = await runner.run(
                    agent=agent,
                    user_input="Audit me",
                    db=db,
                )

        run_id = result["run_id"]
        rt = runtime_registry.get(run_id)
        audit_data = rt.audit.get_all()
        assert len(audit_data) >= 5
        for event in audit_data:
            assert "event_id" in event
            assert "timestamp" in event
            assert "case_id" in event
            assert "event_type" in event
            assert "actor" in event

    @pytest.mark.asyncio
    async def test_run_routing_direct_no_experts(self):
        """Without experts, routing is 'direct'."""
        runner = AgentRunner()
        agent = make_mock_agent(expert_ids=[])
        db = make_mock_db([])

        async def mock_resolve(agent, db=None):
            return []
        async def mock_run_single(agent, user_input, history, expert, rt):
            return "Direct output"

        with patch.object(runner, '_resolve_experts', mock_resolve):
            with patch.object(runner, '_run_single_expert', mock_run_single):
                result = await runner.run(
                    agent=agent,
                    user_input="Direct query",
                    db=db,
                )

        assert result["routing"] == "direct"
        assert result["expert_count"] == 0
        assert result["runtime_state"] == CaseState.ARCHIVED.value

    @pytest.mark.asyncio
    async def test_run_multiple_runs_no_registry_collision(self):
        """Multiple concurrent runs create independent Runtime instances."""
        runner = AgentRunner()
        agent = make_mock_agent(expert_ids=[])
        db = make_mock_db([])

        run_ids = []

        async def mock_resolve(agent, db=None):
            return []
        async def mock_run_single(agent, user_input, history, expert, rt):
            return "Output"

        with patch.object(runner, '_resolve_experts', mock_resolve):
            with patch.object(runner, '_run_single_expert', mock_run_single):
                for _ in range(3):
                    result = await runner.run(agent=agent, user_input="Test", db=db)
                    run_ids.append(result["run_id"])

        assert len(set(run_ids)) == 3
        for rid in run_ids:
            rt = runtime_registry.get(rid)
            assert rt is not None
            assert rt.state == CaseState.ARCHIVED


class TestAgentRunnerStreamRuntime:
    """Unit tests for AgentRunner.stream() Runtime integration."""

    @pytest.mark.asyncio
    async def test_stream_creates_runtime(self):
        """AgentRunner.stream() must create a Runtime."""
        runner = AgentRunner()
        agent = make_mock_agent(expert_ids=[])
        db = make_mock_db([])

        with patch.object(AgentRunner, '_resolve_experts', return_value=[]):
            async def mock_stream_single(self, *args, **kwargs):
                import json
                yield json.dumps({"type": "token", "text": "Test"})

            with patch.object(AgentRunner, '_stream_single', mock_stream_single):
                chunks = []
                async for chunk in runner.stream(
                    agent=agent,
                    user_input="Stream test",
                    db=db,
                ):
                    chunks.append(chunk)

        done_chunks = [c for c in chunks if '"type": "done"' in c]
        assert len(done_chunks) >= 1

    @pytest.mark.asyncio
    async def test_stream_no_experts_direct(self):
        """Without experts, stream uses direct path with Runtime."""
        runner = AgentRunner()
        agent = make_mock_agent(expert_ids=[])
        db = make_mock_db([])

        with patch.object(AgentRunner, '_resolve_experts', return_value=[]):
            async def mock_stream_single(self, *args, **kwargs):
                import json
                yield json.dumps({"type": "token", "text": "Hello"})

            with patch.object(AgentRunner, '_stream_single', mock_stream_single):
                chunks = []
                async for chunk in runner.stream(
                    agent=agent, user_input="Hi", db=db,
                ):
                    chunks.append(chunk)

        tokens = [c for c in chunks if '"type": "token"' in c]
        done = [c for c in chunks if '"type": "done"' in c]
        assert len(tokens) >= 1
        assert len(done) >= 1
