"""The four Phase-2 atomic *tool* agents on the executor (offline-guarded).

Each tool agent (index navigation / code validation / compliance guardrail / document
standardization) runs on the same Corti-style tool-calling executor as fact extraction, but
with submit_findings gated OFF: it researches via coding-expert tools then answers in prose
Markdown. These tests drive every tool agent with a scripted FakeChatProvider (no external
model / key) and assert the load-bearing invariants:

- PHI is redacted before any model call (the model only ever sees de-identified text);
- the tool list handed to the model does NOT contain submit_findings (prose surface) but DOES
  expose all five coding-expert tools, including the iCoDer-only `alternatives`;
- the model's prose (a turn with no tool calls) is captured as final_message;
- every tool call yields exactly one StageObservation, and findings stays None (no extract).
"""
import pytest
from sample_data import SAMPLE_TEXT

from icoder.agents.code_validation import AGENT as CODE_VALIDATION
from icoder.agents.compliance_guardrail import AGENT as COMPLIANCE_GUARDRAIL
from icoder.agents.document_standardization import AGENT as DOCUMENT_STANDARDIZATION
from icoder.agents.index_navigation import AGENT as INDEX_NAVIGATION
from icoder.runtime.executor import AgentExecutor
from icoder.runtime.gateway import ChatResult, ToolCall

TOOL_AGENTS = [INDEX_NAVIGATION, CODE_VALIDATION, COMPLIANCE_GUARDRAIL, DOCUMENT_STANDARDIZATION]
EXPECTED_TOOLS = {"search", "verify", "guidelines", "explore", "alternatives"}

PROSE = "# 报告\n**结论：** 已研判，详见下文。\n\n- 要点一\n- 要点二"


class RecordingFakeProvider:
    """Scripted chat provider that records BOTH the messages and the tools seen per call."""
    name = "fake"
    model = "fake-1"

    def __init__(self, script):
        self._script = list(script)
        self.calls: list[list[dict]] = []
        self.tools_seen: list[list[dict]] = []

    def chat(self, messages, tools=None, tool_choice=None):
        self.calls.append([dict(m) for m in messages])
        self.tools_seen.append(tools or [])
        if self._script:
            return self._script.pop(0)
        return ChatResult(content="done", tool_calls=[])


def _search_then_prose():
    # one research tool call, then a prose turn (no tool calls) -> executor captures it.
    return [
        ChatResult(tool_calls=[ToolCall(id="c1", name="search", arguments={"term": "心力衰竭"})]),
        ChatResult(content=PROSE, tool_calls=[]),
    ]


@pytest.mark.parametrize("agent", TOOL_AGENTS, ids=lambda a: a.id)
def test_tool_agent_is_tool_surface(agent):
    from icoder.runtime.registry import effective_surface

    assert agent.surface == "tool"
    assert agent.rule_sets == []
    assert agent.experts == ["coding-expert"]
    assert effective_surface(agent) == "tool"


@pytest.mark.parametrize("agent", TOOL_AGENTS, ids=lambda a: a.id)
def test_phi_redacted_before_any_model_call(agent):
    provider = RecordingFakeProvider(_search_then_prose())
    AgentExecutor(provider).run(agent, SAMPLE_TEXT, submit_findings=False)
    user = next(m for m in provider.calls[0] if m["role"] == "user")
    assert "张三" not in user["content"]
    assert "13800001111" not in user["content"]
    assert "ZY20260613" not in user["content"]
    assert "心力衰竭" in user["content"]  # clinical content survives redaction
    system = next(m for m in provider.calls[0] if m["role"] == "system")
    assert system["content"] == agent.system_prompt


@pytest.mark.parametrize("agent", TOOL_AGENTS, ids=lambda a: a.id)
def test_no_submit_findings_tool_but_all_expert_tools(agent):
    provider = RecordingFakeProvider(_search_then_prose())
    AgentExecutor(provider).run(agent, SAMPLE_TEXT, submit_findings=False)
    names = {t["function"]["name"] for t in provider.tools_seen[0]}
    assert "submit_findings" not in names  # prose surface: no terminal tool
    assert EXPECTED_TOOLS <= names  # all five coding-expert tools exposed (incl. alternatives)


@pytest.mark.parametrize("agent", TOOL_AGENTS, ids=lambda a: a.id)
def test_prose_captured_and_no_findings(agent):
    provider = RecordingFakeProvider(_search_then_prose())
    result = AgentExecutor(provider).run(agent, SAMPLE_TEXT, submit_findings=False)
    assert result.final_message == PROSE
    assert result.findings is None  # tool agents never submit structured entities
    assert [s.tool for s in result.stages] == ["search"]  # one stage per tool call
    assert result.usage["tool_calls"] == 1
    assert result.redaction_text and "张三" not in result.redaction_text
