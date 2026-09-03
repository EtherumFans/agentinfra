from __future__ import annotations

import pytest

from icoder_sdk import END, MessageResponse, agent_node, parallel, stateGraph, workflow


class Agent:
    def __init__(self, handler):
        self.handler = handler

    async def run(self, input):
        return self.handler(input)


@pytest.mark.asyncio
async def test_workflow_transform_skip_retry_and_early_stop():
    attempts = 0

    def retry(_input):
        nonlocal attempts
        attempts += 1
        return MessageResponse("retry", "failed") if attempts == 1 else MessageResponse("URGENT")

    result = await workflow([
        Agent(lambda value: MessageResponse(f"summary:{value}")),
        {"agent": Agent(retry), "retries": 1, "retry_delay": 0},
        {"agent": Agent(lambda _: MessageResponse("must-skip")), "when": lambda _: False},
        {"agent": Agent(lambda value: MessageResponse(value)), "transform": lambda _: "original-note"},
    ]).run("note")
    assert attempts == 2
    assert result.output.text == "original-note"
    assert len(result.steps) == 3
    assert result.stopped_early is False

    stopped = await workflow([
        Agent(lambda _: MessageResponse("withheld", "failed")),
        Agent(lambda _: MessageResponse("must-not-run")),
    ]).run("note")
    assert stopped.stopped_early is True
    assert len(stopped.steps) == 1


@pytest.mark.asyncio
async def test_parallel_isolation_input_override_and_workflow_join():
    def fail(_):
        raise RuntimeError("isolated")

    fanout = parallel([
        Agent(lambda value: MessageResponse(f"shared:{value}")),
        {"agent": Agent(lambda value: MessageResponse(f"override:{value}")), "input": "special"},
        Agent(fail),
    ])
    result = await fanout.run("note")
    assert [item.text for item in result.fulfilled] == ["shared:note", "override:special"]
    assert len(result.rejected) == 1
    joined = await workflow([fanout, Agent(lambda value: MessageResponse(value))]).run("note")
    assert joined.output.text == "shared:note\noverride:special"

    with pytest.raises(RuntimeError, match="all parallel workflow branches failed"):
        await workflow([parallel([Agent(fail)])]).run("note")


@pytest.mark.asyncio
async def test_state_graph_cycles_bounds_and_no_edge():
    graph = (
        stateGraph()
        .add_node("increment", lambda state: {"count": state["count"] + 1})
        .add_edge("increment", lambda state: END if state["count"] >= 3 else "increment")
    )
    ended = await graph.run("increment", {"count": 0}, max_iterations=10)
    assert ended.state["count"] == 3
    assert ended.iterations == 3
    assert ended.terminated_by == "end"
    assert [step.delta["count"] for step in ended.steps] == [1, 2, 3]

    bounded = await graph.run("increment", {"count": 0}, max_iterations=2)
    assert bounded.terminated_by == "maxIterations"
    no_edge = await stateGraph().add_node("once", lambda _: {"done": True}).run(
        "once", {"done": False}
    )
    assert no_edge.terminated_by == "noEdge"


@pytest.mark.asyncio
async def test_agent_node_maps_state_and_response():
    graph = (
        stateGraph()
        .add_node("agent", agent_node(
            Agent(lambda value: MessageResponse(value.upper())),
            input_fn=lambda state: state["note"],
            merge_fn=lambda response: {"output": response.text},
        ))
        .add_edge("agent", END)
    )
    result = await graph.run("agent", {"note": "safe", "output": ""})
    assert result.state["output"] == "SAFE"
