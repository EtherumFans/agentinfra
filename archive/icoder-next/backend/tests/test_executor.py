"""AgentExecutor — the Corti-style LLM tool-calling executor (offline-guarded).

These tests drive the executor with a scripted FakeChatProvider so the loop logic is
verified deterministically with NO external model / API key (the CI durable guardrail).
They assert the load-bearing invariants: PHI is redacted before any model call, every tool
call yields one StageObservation, the terminal submit_findings stops the loop while a
non-terminating model degrades within the bound, and evidence offsets — derived from the
model's verbatim quotes — are anchored exactly server-side (never trusted from the model).
"""
from sample_data import SAMPLE_TEXT

from icoder.agents.fact_extraction import AGENT
from icoder.api.routes_coding_lookup import _entities_from
from icoder.experts.coding_expert import CodingExpert
from icoder.runtime.executor import MAX_ROUNDS, AgentExecutor
from icoder.runtime.gateway import ChatResult, ToolCall

AUTH = {"Authorization": "Bearer demo:coder"}


class FakeChatProvider:
    """Returns scripted ChatResults in order; records the messages seen on each call."""
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


def _script_search_verify_submit():
    return [
        ChatResult(tool_calls=[ToolCall(id="c1", name="search", arguments={"term": "慢性心力衰竭"})]),
        ChatResult(tool_calls=[ToolCall(id="c2", name="verify", arguments={"code": "I50.900"})]),
        ChatResult(tool_calls=[ToolCall(
            id="c3", name="submit_findings",
            arguments={"entities": [
                {"term": "慢性心力衰竭", "evidence_quote": "慢性心力衰竭"},
                {"term": "病理性骨折", "evidence_quote": "病理性骨折"},
            ]},
        )]),
    ]


def test_phi_redacted_before_any_model_call():
    provider = FakeChatProvider(_script_search_verify_submit())
    AgentExecutor(provider).run(AGENT, SAMPLE_TEXT)
    first = provider.calls[0]
    user = next(m for m in first if m["role"] == "user")
    assert "张三" not in user["content"]
    assert "13800001111" not in user["content"]
    assert "ZY20260613" not in user["content"]
    assert "慢性心力衰竭" in user["content"]  # clinical content survives redaction
    system = next(m for m in first if m["role"] == "system")
    assert system["content"] == AGENT.system_prompt


def test_one_stage_observation_per_tool_call():
    provider = FakeChatProvider(_script_search_verify_submit())
    result = AgentExecutor(provider).run(AGENT, SAMPLE_TEXT)
    assert [s.tool for s in result.stages] == ["search", "verify", "submit_findings"]
    for s in result.stages:
        assert s.tool_run_id
        assert s.duration_ms >= 0.0
    assert result.usage["tool_calls"] == 3
    assert result.usage["llm_calls"] == 3


def test_submit_findings_terminates_with_findings():
    provider = FakeChatProvider(_script_search_verify_submit())
    result = AgentExecutor(provider).run(AGENT, SAMPLE_TEXT)
    assert result.findings is not None
    assert [e["term"] for e in result.findings["entities"]] == ["慢性心力衰竭", "病理性骨折"]
    assert result.usage["rounds"] == 3


def test_offsets_anchored_server_side_exactly():
    provider = FakeChatProvider(_script_search_verify_submit())
    result = AgentExecutor(provider).run(AGENT, SAMPLE_TEXT)
    items = [(e["term"], e["evidence_quote"]) for e in result.findings["entities"]]
    entities = _entities_from(result.redaction_text, items, CodingExpert())
    red = result.redaction_text
    spans = 0
    for ent in entities:
        for ev in ent["evidences"]:
            assert red[ev.start:ev.end] == ev.text
            spans += 1
    assert spans >= 2
    # category comes from deterministic retrieval, not the model
    by_term = {e["term"]: e["category"] for e in entities}
    assert by_term["慢性心力衰竭"] == "diagnosis"


def test_model_prose_without_tool_calls_terminates():
    provider = FakeChatProvider([ChatResult(content="无可抽取的可编码事实", tool_calls=[])])
    result = AgentExecutor(provider).run(AGENT, SAMPLE_TEXT)
    assert result.final_message == "无可抽取的可编码事实"
    assert result.findings is None
    assert result.usage["rounds"] == 1


def test_non_terminating_model_stops_within_bound():
    class Looping:
        name = "loop"
        model = "loop-1"

        def __init__(self):
            self.n = 0

        def chat(self, messages, tools=None, tool_choice=None):
            self.n += 1
            return ChatResult(
                tool_calls=[ToolCall(id=f"c{self.n}", name="search", arguments={"term": "x"})]
            )

    result = AgentExecutor(Looping()).run(AGENT, SAMPLE_TEXT)
    assert result.findings is None
    assert result.usage["rounds"] == MAX_ROUNDS
    assert result.usage["llm_calls"] == MAX_ROUNDS


def test_final_round_forces_submit_to_close_out():
    """An over-researching model that never volunteers submit_findings is forced to the
    terminal tool on the final round, so a doc with codeable facts never returns empty from
    round exhaustion. (Pairs with the bound test above: a provider that *ignores* the forced
    tool_choice still degrades to findings=None — the bound is the floor, forcing the ceiling.)"""
    class StubbornResearcher:
        name = "stub"
        model = "stub-1"

        def __init__(self):
            self.n = 0
            self.forced_round = None

        def chat(self, messages, tools=None, tool_choice=None):
            self.n += 1
            if isinstance(tool_choice, dict):  # final round: forced to the terminal tool
                assert tool_choice["function"]["name"] == "submit_findings"
                self.forced_round = self.n
                return ChatResult(tool_calls=[ToolCall(
                    id="f", name="submit_findings",
                    arguments={"entities": [{"term": "慢性心力衰竭", "evidence_quote": "慢性心力衰竭"}]})])
            return ChatResult(tool_calls=[ToolCall(id=f"s{self.n}", name="search", arguments={"term": "x"})])

    provider = StubbornResearcher()
    result = AgentExecutor(provider).run(AGENT, SAMPLE_TEXT)
    assert provider.forced_round == MAX_ROUNDS          # forcing kicked in on the last round
    assert result.findings is not None                  # ...and closed the run out (not empty)
    assert [e["term"] for e in result.findings["entities"]] == ["慢性心力衰竭"]
    assert result.usage["rounds"] == MAX_ROUNDS


# ---- route-level regression: no key -> deterministic /extract still green ----

def test_extract_route_without_key_is_deterministic(client):
    r = client.post("/api/coding/extract", json={"text": SAMPLE_TEXT}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "deterministic-local"
    assert body["redaction"]["spans"] >= 3
    assert "张三" not in body["redaction"]["text"]
    terms = {e["term"] for e in body["entities"]}
    assert "慢性心力衰竭" in terms
    red = body["redaction"]["text"]
    for e in body["entities"]:
        for ev in e["evidences"]:
            assert red[ev["start"]:ev["end"]] == ev["text"]
