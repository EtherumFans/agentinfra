"""Tests for icoder_runtime — run with: python -m pytest icoder_runtime/tests/ -v"""
import pytest
import asyncio
from icoder_runtime.types import AgentDefinition, ExpertDefinition, ToolDefinition, ToolTier
from icoder_runtime.agent_runner import AgentRunner
from icoder_runtime.symbolic_state import SymbolicState as AuditState
from icoder_runtime.contract_engine import SymbolicState, ContractViolation
from icoder_runtime.permissions import PermissionPolicy, PermissionOutcome, ToolPermission
from icoder_runtime.tool_registry import ToolRegistry
from icoder_runtime.evidence_pack import build_evidence_pack
from icoder_runtime.core.llm_gateway import LLMGateway, MockLLMProvider
from icoder_runtime.core.errors import LLMProviderNotConfigured
from icoder_runtime import __version__


class TestVersion:
    def test_version(self):
        assert __version__ == "1.0.0"


class TestTypes:
    def test_agent_definition(self):
        agent = AgentDefinition(id="test", name="Test", category="编码")
        assert agent.id == "test"
        assert agent.name == "Test"
        assert agent.expert_ids == []
        assert agent.version == "1.0.0"

    def test_expert_definition(self):
        exp = ExpertDefinition(id="e1", name="E1", description="Test expert")
        assert exp.id == "e1"
        assert exp.capabilities == []

    def test_tool_definition(self):
        tool = ToolDefinition(
            id="t1", name="T1", description="Test",
            tier=ToolTier.DETERMINISTIC, category="safety",
            requires=["input must be valid"],
            guarantees={"output": "safe output"},
        )
        assert tool.tier == ToolTier.DETERMINISTIC
        assert tool.requires == ["input must be valid"]


class TestSymbolicState:
    def test_basic_operations(self):
        state = SymbolicState()
        assert state.get("nonexistent") is None
        assert state.get("nonexistent", "default") == "default"

    def test_set_and_get(self):
        state = SymbolicState({"key": "value"})
        assert state.get("key") == "value"

    def test_dot_notation(self):
        state = SymbolicState({"a": {"b": "c"}})
        assert state.get("a.b") == "c"

    def test_has(self):
        state = SymbolicState({"key": "value"})
        assert state.has("key") is True
        assert state.has("nonexistent") is False

    def test_update_count(self):
        state = SymbolicState()
        assert state._update_count == 0


class TestAuditState:
    def test_record_and_verify(self):
        audit = AuditState("session-1")
        audit.record("step1", "actor1", {"data": 1})
        audit.record("step2", "actor2", {"data": 2})
        assert len(audit.entries) == 2
        assert audit.verify_chain() is True

    def test_tamper_detection(self):
        audit = AuditState("session-1")
        audit.record("step1", "actor1", {"data": 1})
        # Tamper
        audit.entries[0]["payload"]["data"] = 999
        assert audit.verify_chain() is False

    def test_export(self):
        audit = AuditState("session-1")
        audit.record("step1")
        exported = audit.export()
        assert exported["session_id"] == "session-1"
        assert exported["entry_count"] == 1
        assert exported["chain_valid"] is True


class TestPermissions:
    def test_allow(self):
        policy = PermissionPolicy(permissions={
            "t1": ToolPermission("t1", allowed=True),
        })
        assert policy.check("t1") == PermissionOutcome.ALLOW

    def test_deny_unknown(self):
        policy = PermissionPolicy(permissions={})
        assert policy.check("unknown") == PermissionOutcome.DENY

    def test_require_human(self):
        policy = PermissionPolicy(permissions={
            "t1": ToolPermission("t1", allowed=True, requires_human=True),
        })
        assert policy.check("t1") == PermissionOutcome.NEEDS_HUMAN

    def test_deny_explicit(self):
        policy = PermissionPolicy(permissions={
            "t1": ToolPermission("t1", allowed=False),
        })
        assert policy.check("t1") == PermissionOutcome.DENY


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = ToolDefinition(
            id="t1", name="T1", description="Test tool",
            tier=ToolTier.DETERMINISTIC, category="test",
        )
        reg.register(tool)
        assert reg.get("t1") is not None
        assert reg.get("t1").name == "T1"

    def test_list_all(self):
        reg = ToolRegistry()
        t1 = ToolDefinition(id="t1", name="T1", description="", tier=ToolTier.DETERMINISTIC, category="a")
        t2 = ToolDefinition(id="t2", name="T2", description="", tier=ToolTier.LLM_REASONING, category="b")
        reg.register(t1)
        reg.register(t2)
        assert len(reg.list_all()) == 2

    def test_list_by_tier(self):
        reg = ToolRegistry()
        t1 = ToolDefinition(id="t1", name="T1", description="", tier=ToolTier.DETERMINISTIC, category="a")
        t2 = ToolDefinition(id="t2", name="T2", description="", tier=ToolTier.LLM_REASONING, category="b")
        reg.register(t1)
        reg.register(t2)
        tier1 = reg.list_by_tier(ToolTier.DETERMINISTIC)
        assert len(tier1) == 1
        assert tier1[0].id == "t1"

    def test_list_by_category(self):
        reg = ToolRegistry()
        t1 = ToolDefinition(id="t1", name="T1", description="", tier=ToolTier.DETERMINISTIC, category="safety")
        reg.register(t1)
        assert len(reg.list_by_category("safety")) == 1
        assert len(reg.list_by_category("nonexistent")) == 0


class TestAgentRunner:
    @staticmethod
    def _gateway():
        g = LLMGateway()
        g.register(MockLLMProvider(), default=True)
        return g

    def test_run_with_mock_provider(self):
        agent = AgentDefinition(id="test", name="Test Agent", system_prompt="You are a tester.")
        runner = AgentRunner(gateway=self._gateway())
        result = asyncio.run(runner.run(agent, "test input"))
        assert "review_id" in result
        assert result["agent_name"] == "Test Agent"
        assert result["processing_time_ms"] >= 0
        assert result["output"]  # mock provider returns content

    def test_run_without_llm_throws(self):
        agent = AgentDefinition(id="test", name="Test Agent", system_prompt="You are a tester.")
        runner = AgentRunner()
        with pytest.raises(LLMProviderNotConfigured):
            asyncio.run(runner.run(agent, "test input"))

    def test_run_with_experts(self):
        agent = AgentDefinition(
            id="test", name="Test",
            system_prompt="You are a tester",
            expert_ids=["e1"],
        )
        exp = ExpertDefinition(id="e1", name="E1", description="Test")
        runner = AgentRunner(gateway=self._gateway())
        runner.register_expert(exp)
        result = asyncio.run(runner.run(agent, "test"))
        assert "review_id" in result

    def test_run_audit_chain(self):
        agent = AgentDefinition(id="test", name="Test")
        runner = AgentRunner(gateway=self._gateway())
        result = asyncio.run(runner.run(agent, "test"))
        state_log = result["state_log"]
        assert state_log["chain_valid"] is True
        assert state_log["entry_count"] >= 2  # run_started + llm_response

    def test_run_with_permissions(self):
        agent = AgentDefinition(id="test", name="Test", expert_ids=["e1"])
        exp = ExpertDefinition(id="e1", name="E1", description="Test")
        # Expert denied by policy
        policy = PermissionPolicy(permissions={
            "e1": ToolPermission("e1", allowed=False),
        })
        runner = AgentRunner(gateway=self._gateway())
        runner.register_expert(exp)
        result = asyncio.run(runner.run(agent, "test", permission_policy=policy))
        assert result["state_log"]["chain_valid"] is True


class TestEvidencePack:
    def test_build_pack(self):
        result = {
            "review_id": "test-123",
            "agent_name": "Test Agent",
            "agent_version": "1.0.0",
            "output": "test output",
            "contract_valid": True,
            "primary_diagnosis": {"code": "I21.0"},
            "state_log": {"entry_count": 3, "chain_valid": True},
            "processing_time_ms": 100,
        }
        pack = build_evidence_pack(result)
        assert pack["metadata"]["review_id"] == "test-123"
        assert "integrity" in pack
        assert pack["integrity"]["content_hash"].startswith("sha256:")
        assert pack["integrity"]["unsigned_hash"] is not None

    def test_different_inputs_different_hashes(self):
        r1 = {"review_id": "a", "output": "x"}
        r2 = {"review_id": "b", "output": "y"}
        assert build_evidence_pack(r1)["integrity"]["content_hash"] != \
               build_evidence_pack(r2)["integrity"]["content_hash"]


class TestContractEngine:
    def test_symbolic_state_basics(self):
        state = SymbolicState({"facts": ["f1", "f2"]})
        assert state.get("facts") == ["f1", "f2"]

    def test_contract_violation(self):
        err = ContractViolation("t1", "precondition", "input invalid", "fix it")
        assert err.tool_id == "t1"
        assert err.stage == "precondition"
        feedback = err.to_feedback()
        assert "fix it" in feedback
