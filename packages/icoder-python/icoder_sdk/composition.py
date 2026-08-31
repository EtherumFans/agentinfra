"""Alpha-v2 multi-Agent composition primitives aligned with Corti Agent SDK."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, Literal, Mapping, TypeVar


S = TypeVar("S", bound=dict[str, Any])


@dataclass
class MessageResponse:
    text: str | None = None
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParallelResult:
    results: list[dict[str, Any]]
    fulfilled: list[Any]
    rejected: list[Any]


@dataclass
class WorkflowResult:
    output: Any
    steps: list[Any]
    stopped_early: bool


@dataclass
class StateGraphStep(Generic[S]):
    node: str
    delta: dict[str, Any]
    state: S


@dataclass
class StateGraphResult(Generic[S]):
    state: S
    steps: list[StateGraphStep[S]]
    iterations: int
    terminated_by: Literal["end", "maxIterations", "noEdge"]


class _End:
    def __repr__(self) -> str:
        return "END"


END = _End()


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _runnable(value: Any) -> bool:
    return callable(getattr(value, "run", None))


def _status(value: Any) -> str:
    if isinstance(value, Mapping):
        status = value.get("status")
    else:
        status = getattr(value, "status", None)
    return status.lower() if isinstance(status, str) else ""


def _text(value: Any) -> str:
    if isinstance(value, Mapping):
        text = value.get("text")
    else:
        text = getattr(value, "text", None)
    return text if isinstance(text, str) else ""


class Parallel:
    def __init__(self, branches: list[Any]) -> None:
        if not isinstance(branches, list) or not branches:
            raise TypeError("parallel requires at least one branch")
        for branch in branches:
            runnable = branch if _runnable(branch) else (
                branch.get("agent") if isinstance(branch, Mapping) else None
            )
            if not _runnable(runnable):
                raise TypeError("parallel branch must be runnable")
        self.branches = list(branches)

    async def run(self, input: Any) -> ParallelResult:
        async def invoke(branch: Any) -> Any:
            if _runnable(branch):
                return await _await(branch.run(input))
            branch_input = branch["input"] if "input" in branch else input
            return await _await(branch["agent"].run(branch_input))

        raw = await asyncio.gather(
            *(invoke(branch) for branch in self.branches),
            return_exceptions=True,
        )
        results: list[dict[str, Any]] = []
        fulfilled: list[Any] = []
        rejected: list[Any] = []
        for item in raw:
            if isinstance(item, BaseException):
                results.append({"status": "rejected", "reason": item})
                rejected.append(item)
            else:
                results.append({"status": "fulfilled", "value": item})
                fulfilled.append(item)
        return ParallelResult(results=results, fulfilled=fulfilled, rejected=rejected)


def parallel(branches: list[Any]) -> Parallel:
    return Parallel(branches)


class Workflow:
    def __init__(self, steps: list[Any]) -> None:
        if not isinstance(steps, list) or not steps:
            raise TypeError("workflow requires at least one step")
        for step in steps:
            runnable = step if _runnable(step) else (
                step.get("agent") if isinstance(step, Mapping) else None
            )
            if not _runnable(runnable):
                raise TypeError("workflow step must be runnable or a step configuration")
        self.definitions = list(steps)

    @staticmethod
    async def _run_step(runnable: Any, input: Any) -> Any:
        if isinstance(runnable, Parallel):
            result = await runnable.run(input)
            if not result.fulfilled:
                error = RuntimeError("all parallel workflow branches failed")
                setattr(error, "rejected", result.rejected)
                raise error
            return MessageResponse(
                text="\n".join(_text(item) for item in result.fulfilled),
                metadata={"parallel": result},
            )
        response = await _await(runnable.run(input))
        if response is None or not (
            isinstance(response, Mapping) or hasattr(response, "__dict__")
        ):
            raise TypeError("workflow runnable returned a non-object response")
        return response

    async def run(self, input: Any) -> WorkflowResult:
        previous: Any = MessageResponse(
            text=input if isinstance(input, str) else "",
            metadata={"input": input},
        )
        executed: list[Any] = []
        next_input = input
        for index, definition in enumerate(self.definitions):
            config = definition if isinstance(definition, Mapping) else None
            runnable = config["agent"] if config is not None else definition
            if config is not None and config.get("when") is not None:
                if not await _await(config["when"](previous)):
                    continue
            if config is not None and config.get("transform") is not None:
                step_input = await _await(config["transform"](previous))
            else:
                step_input = next_input if index == 0 else _text(previous)
            retries = int(config.get("retries", 0)) if config is not None else 0
            retry_delay = float(config.get("retry_delay", 1.0)) if config is not None else 1.0
            if retries < 0:
                raise ValueError("workflow retries must be non-negative")
            if retry_delay < 0:
                raise ValueError("workflow retry_delay must be non-negative")

            response: Any = None
            last_error: Exception | None = None
            for attempt in range(retries + 1):
                try:
                    response = await self._run_step(runnable, step_input)
                    last_error = None
                except Exception as exc:  # preserve provider exception identity
                    last_error = exc
                needs_retry = last_error is not None or _status(response) == "failed"
                if not needs_retry or attempt == retries:
                    break
                if retry_delay:
                    await asyncio.sleep(retry_delay)
            if last_error is not None:
                raise last_error
            if response is None:
                raise RuntimeError("workflow step produced no response")
            executed.append(response)
            previous = response
            next_input = _text(response)
            if _status(response) == "failed":
                return WorkflowResult(response, executed, True)
        return WorkflowResult(previous, executed, False)


def workflow(steps: list[Any]) -> Workflow:
    return Workflow(steps)


Node = Callable[[S], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]
Edge = str | _End | Callable[[S], str | _End | Awaitable[str | _End]]


class StateGraph(Generic[S]):
    def __init__(self) -> None:
        self.nodes: dict[str, Node[S]] = {}
        self.edges: dict[str, Edge[S]] = {}

    def add_node(self, name: str, node: Node[S]) -> "StateGraph[S]":
        if not name or not callable(node):
            raise TypeError("stateGraph node is invalid")
        self.nodes[name] = node
        return self

    def add_edge(self, source: str, edge: Edge[S]) -> "StateGraph[S]":
        if not source or not (isinstance(edge, str) or edge is END or callable(edge)):
            raise TypeError("stateGraph edge is invalid")
        self.edges[source] = edge
        return self

    async def run(
        self,
        start: str,
        initial_state: S,
        *,
        max_iterations: int = 100,
    ) -> StateGraphResult[S]:
        if not isinstance(max_iterations, int) or max_iterations < 1:
            raise ValueError("max_iterations must be a positive integer")
        if start not in self.nodes:
            raise KeyError(f"stateGraph start node not found: {start}")
        current = start
        state = dict(initial_state)
        steps: list[StateGraphStep[S]] = []
        while True:
            node = self.nodes.get(current)
            if node is None:
                raise KeyError(f"stateGraph node not found: {current}")
            delta = await _await(node(dict(state)))
            if not isinstance(delta, Mapping):
                raise TypeError(f"stateGraph node {current} returned an invalid delta")
            delta_dict = dict(delta)
            state.update(delta_dict)
            steps.append(StateGraphStep(
                node=current,
                delta=delta_dict,
                state=dict(state),  # type: ignore[arg-type]
            ))
            if current not in self.edges:
                return StateGraphResult(
                    state=state, steps=steps, iterations=len(steps),
                    terminated_by="noEdge",
                )
            edge = self.edges[current]
            next_node = await _await(edge(dict(state))) if callable(edge) else edge
            if next_node is END:
                return StateGraphResult(
                    state=state, steps=steps, iterations=len(steps),
                    terminated_by="end",
                )
            if len(steps) >= max_iterations:
                return StateGraphResult(
                    state=state, steps=steps, iterations=len(steps),
                    terminated_by="maxIterations",
                )
            if next_node not in self.nodes:
                raise KeyError(f"stateGraph edge target not found: {next_node}")
            current = next_node


def stateGraph() -> StateGraph[Any]:
    return StateGraph()


def agent_node(
    agent: Any,
    input_fn: Callable[[S], Any],
    merge_fn: Callable[[Any], Mapping[str, Any]],
) -> Node[S]:
    if not _runnable(agent) or not callable(input_fn) or not callable(merge_fn):
        raise TypeError("agent_node requires an Agent handle, input_fn, and merge_fn")

    async def node(state: S) -> Mapping[str, Any]:
        response = await _await(agent.run(input_fn(state)))
        return merge_fn(response)

    return node


__all__ = [
    "END", "MessageResponse", "Parallel", "ParallelResult", "StateGraph",
    "StateGraphResult", "StateGraphStep", "Workflow", "WorkflowResult",
    "agent_node", "parallel", "stateGraph", "workflow",
]
