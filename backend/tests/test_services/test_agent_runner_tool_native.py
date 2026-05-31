"""Test AgentRunner tool-native execution path with contract enforcement"""
import pytest
from unittest.mock import patch
from app.services.agent_runner import AgentRunner
from app.services.tool_registry import ToolDefinition, ToolRegistry, ToolTier
from app.services.contract_engine import SymbolicState


# ── Fixtures ──

@pytest.fixture
def runner():
    return AgentRunner()


@pytest.fixture
def populated_registry():
    """Registry with the minimum tool set for coding pipeline."""
    reg = ToolRegistry()
    reg.register(ToolDefinition(
        id="extract_evidence", name="证据提取", description="Extract clinical facts",
        tier=ToolTier.LLM_REASONING, category="extraction",
        accuracy_tags=["evidence_binding"],
    ))
    reg.register(ToolDefinition(
        id="assign_diagnosis_code", name="诊断编码分配", description="Assign diagnosis code",
        tier=ToolTier.LLM_REASONING, category="coding",
        requires=["state.has('evidence.diagnosis_facts')", "state.has('icd10_search_results')"],
        accuracy_tags=["code_dict", "evidence_binding"],
    ))
    reg.register(ToolDefinition(
        id="search_icd10_index", name="ICD-10索引导航", description="Search ICD-10 index",
        tier=ToolTier.DETERMINISTIC, category="coding",
        accuracy_tags=["code_dict"], is_injectable=True,
    ))
    reg.register(ToolDefinition(
        id="rank_evidence", name="证据排名", description="Rank evidence strength",
        tier=ToolTier.DETERMINISTIC, category="verification",
        accuracy_tags=["evidence_binding", "conflict_detection"], is_injectable=True,
    ))
    reg.register(ToolDefinition(
        id="calibrate_confidence", name="置信度校准", description="Calibrate confidence",
        tier=ToolTier.DETERMINISTIC, category="verification",
        accuracy_tags=["calibration"], is_injectable=True,
    ))
    reg.register(ToolDefinition(
        id="guard_input", name="输入安全验证", description="Validate input",
        tier=ToolTier.DETERMINISTIC, category="safety",
        accuracy_tags=["safety"], is_injectable=True,
    ))
    reg.register(ToolDefinition(
        id="guard_output", name="输出安全验证", description="Validate output",
        tier=ToolTier.DETERMINISTIC, category="safety",
        accuracy_tags=["safety"], is_injectable=True,
    ))
    return reg


# ── _inject_tier1_tools Tests ──

class TestTier1Injection:
    def test_injects_code_dict_when_coding_tools_enabled(self, runner, populated_registry):
        with patch("app.services.agent_runner.global_tool_registry", populated_registry):
            enabled = ["extract_evidence", "assign_diagnosis_code"]
            result = runner._inject_tier1_tools(enabled)
            assert "search_icd10_index" in result
            assert "rank_evidence" in result
            assert "guard_input" in result
            assert "guard_output" in result
            assert "extract_evidence" in result
            assert "assign_diagnosis_code" in result

    def test_no_duplicates(self, runner, populated_registry):
        with patch("app.services.agent_runner.global_tool_registry", populated_registry):
            enabled = ["extract_evidence", "rank_evidence", "calibrate_confidence"]
            result = runner._inject_tier1_tools(enabled)
            assert result.count("rank_evidence") == 1
            assert result.count("calibrate_confidence") == 1

    def test_safety_always_injected(self, runner, populated_registry):
        with patch("app.services.agent_runner.global_tool_registry", populated_registry):
            enabled = ["extract_evidence"]
            result = runner._inject_tier1_tools(enabled)
            assert "guard_input" in result
            assert "guard_output" in result


# ── _build_openai_tools Tests ──

class TestBuildOpenAITools:
    def test_builds_valid_function_definitions(self, runner):
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            id="extract_evidence", name="证据提取", description="Extract facts",
            tier=ToolTier.LLM_REASONING, category="extraction",
        ))
        tools = [reg.get("extract_evidence")]
        openai_tools = runner._build_openai_tools(tools)
        assert len(openai_tools) == 1
        func = openai_tools[0]["function"]
        assert func["name"] == "extract_evidence"
        assert "Tier 2" in func["description"]

    def test_builds_with_input_schema(self, runner):
        td = ToolDefinition(
            id="test_tool", name="Test", description="A test tool",
            tier=ToolTier.LLM_REASONING, category="test",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        openai_tools = runner._build_openai_tools([td])
        func = openai_tools[0]["function"]
        assert "query" in func["parameters"]["properties"]
        assert "query" in func["parameters"]["required"]


# ── _build_tool_system_prompt Tests ──

class TestToolSystemPrompt:
    def test_includes_contract_rules(self, runner):
        reg = ToolRegistry()
        reg.register(ToolDefinition(
            id="search_icd10_index", name="ICD-10索引导航", description="Search ICD-10",
            tier=ToolTier.DETERMINISTIC, category="coding",
        ))
        reg.register(ToolDefinition(
            id="extract_evidence", name="证据提取", description="Extract facts",
            tier=ToolTier.LLM_REASONING, category="extraction",
        ))

        class FakeAgent:
            name = "Test Agent"
            system_prompt = "You are a medical coding assistant."

        tools = list(reg.list_all())
        prompt = runner._build_tool_system_prompt(FakeAgent(), tools)
        assert "CONTRACT RULES" in prompt
        assert "You are a medical coding assistant" in prompt
        assert "Tier 1" in prompt


# ── _synthesize_tool_output Tests ──

class TestSynthesizeOutput:
    def test_synthesizes_codes_and_ranking(self, runner):
        state = SymbolicState({
            "diagnosis_candidates": [
                {"assigned_code": "J18.9", "name": "肺炎"},
                {"code": "I10", "name": "高血压"},
            ],
            "evidence_ranking": {
                "ranked_candidates": [{"code": "J18.9"}],
                "unsupported_codes": [],
            },
            "routing_decisions": [
                {"code": "J18.9", "tier": "auto", "confidence": 0.9},
                {"code": "I10", "tier": "review", "confidence": 0.6},
            ],
        })
        output = runner._synthesize_tool_output(state, ["extract_evidence", "rank_evidence"])
        assert "J18.9" in output
        assert "肺炎" in output
        assert "AUTO" in output
        assert "REVIEW" in output
