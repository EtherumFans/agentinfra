"""With-key runner path — the 3 fat coding-review agents migrated to the tool-calling executor.

Phase 3 splits Stage 1+2 of AgentRunner: when the provider exposes ``.chat`` (a key is
present), the runner drives AgentExecutor's research loop and maps the submitted
``entities`` -> RawExtraction, then runs the UNCHANGED deterministic Stages 3-7. These
tests pin the load-bearing invariants of that with-key path with a scripted fake (no
external key); the deterministic else-branch stays covered by test_runtime.py:

  - the run carries a real research trace (stage="tool" + stage="submit") BEFORE the
    deterministic stages (retrieve..compliance);
  - the extracted entity flows through Stage 3 -> codes still contain I50.900;
  - PHI is redacted before any model call (the fake's messages never see 张三/手机/住院号);
  - versions.model_version is the online signal ("fake"); usage accumulates llm/tool calls;
  - a model that answers in prose without submit_findings degrades to an empty-but-legal run.
"""
from sample_data import SAMPLE_TEXT

from icoder.runtime.gateway import ChatResult, LLMGateway, ToolCall
from icoder.runtime.registry import default_registry
from icoder.runtime.runner import AgentRunner

AGENT_ID = "icoder/homepage-coding-review-agent"
HF = "慢性心力衰竭"  # verbatim substring of SAMPLE_TEXT line 1 (anchors to I50.900)


class _RecordingChatFake:
    """Scripted chat provider; records the messages it saw so PHI redaction is provable."""
    name = "fake"
    model = "fake-1"

    def __init__(self, script):
        self._script = list(script)
        self.calls: list[list[dict]] = []

    def chat(self, messages, tools=None, tool_choice=None):
        self.calls.append([dict(m) for m in messages])
        if self._script:
            return self._script.pop(0)
        return ChatResult(content="done", tool_calls=[])


def _search_then_submit():
    # one research tool call, then the terminal submit_findings with one anchored entity.
    return [
        ChatResult(tool_calls=[ToolCall(id="c1", name="search", arguments={"term": "心力衰竭"})]),
        ChatResult(tool_calls=[ToolCall(id="c2", name="submit_findings",
            arguments={"entities": [{"term": HF, "evidence_quote": HF}]})]),
    ]


def _runner_with(provider):
    return AgentRunner(gateway=LLMGateway(provider), agents=default_registry())


def test_research_trace_precedes_deterministic_stages():
    run = _runner_with(_RecordingChatFake(_search_then_submit())).run(AGENT_ID, SAMPLE_TEXT)
    names = [s.stage for s in run.stages]
    assert names[0] == "ingest"
    assert "tool" in names and "submit" in names  # the research trace is present
    assert any(s.stage == "tool" and s.tool == "search" for s in run.stages)
    # the deterministic post-processing stages still run, in order, AFTER the research.
    i_submit = names.index("submit")
    for st in ("retrieve", "verify", "sequence", "group", "compliance"):
        assert st in names and names.index(st) > i_submit, st


def test_extracted_entity_flows_into_codes():
    run = _runner_with(_RecordingChatFake(_search_then_submit())).run(AGENT_ID, SAMPLE_TEXT)
    # Stage 3 (deterministic) still anchors the submitted entity to a billable code.
    assert "I50.900" in {c.code for c in run.codes}


def test_phi_redacted_before_any_model_call():
    fake = _RecordingChatFake(_search_then_submit())
    _runner_with(fake).run(AGENT_ID, SAMPLE_TEXT)
    user = next(m for m in fake.calls[0] if m["role"] == "user")
    assert "张三" not in user["content"]
    assert "13800001111" not in user["content"]
    assert "ZY20260613" not in user["content"]
    assert "心力衰竭" in user["content"]  # clinical content survives redaction


def test_versions_and_usage_are_online_signals():
    run = _runner_with(_RecordingChatFake(_search_then_submit())).run(AGENT_ID, SAMPLE_TEXT)
    assert run.versions.model_version == "fake"  # online signal, not deterministic-local
    assert run.usage["llm_calls"] == 2           # two chat turns
    assert run.usage["tool_calls"] >= 2          # search + submit + downstream expert calls


def test_prose_without_submit_degrades_gracefully():
    prose_only = [ChatResult(content="# 小结\n未发现可靠事实。", tool_calls=[])]
    run = _runner_with(_RecordingChatFake(prose_only)).run(AGENT_ID, SAMPLE_TEXT)
    assert run.codes == []                        # findings is None -> no extractions
    assert run.versions.model_version == "fake"
    assert run.compliance is not None             # gate still evaluated (empty but legal)
