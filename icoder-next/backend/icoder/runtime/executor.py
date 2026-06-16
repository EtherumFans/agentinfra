"""AgentExecutor — Corti-style LLM tool-calling executor (the message:send analog).

Generic and domain-light: given an Agent (system prompt + declared experts) and raw
clinical text, it (1) redacts PHI server-side BEFORE any model call, (2) exposes the
experts' tools as OpenAI function schemas, and (3) lets the model loop — calling tools,
reading results — until it calls the terminal ``submit_findings`` tool or stops.

Red-lines baked in:
  - PHI redaction happens first; the model only ever sees de-identified text.
  - Char offsets are NOT computed here and are never trusted from the model. The executor
    returns the de-identified text + the model's raw findings; the caller anchors each
    ``evidence_quote`` to a char span server-side (CodingExpert.find_evidences).
  - The loop is bounded (MAX_ROUNDS) so a non-terminating model degrades gracefully.

This is the reusable primitive the atomic agents run on; the fat coding agents migrate to
it in a later phase. It does not import or touch the deterministic ``AgentRunner``.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Optional

from pydantic import BaseModel

from ..experts.registry import ExpertRegistry, default_expert_registry
from ..experts.tool_schemas import SUBMIT_FINDINGS, SUBMIT_FINDINGS_TOOL, build_expert_tools
from .gateway import ChatProvider
from .runner import PHIRedactor, _timed
from .types import StageObservation

MAX_ROUNDS = 8


@dataclass
class ExecutionResult:
    redaction_text: str
    phi: list[dict]
    final_message: Optional[str] = None
    findings: Optional[dict] = None  # the submit_findings arguments, e.g. {"entities": [...]}
    stages: list[StageObservation] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


def _json_default(o):
    if isinstance(o, BaseModel):
        return o.model_dump()
    if is_dataclass(o):
        return asdict(o)
    return str(o)


class AgentExecutor:
    def __init__(
        self,
        provider: ChatProvider,
        experts: ExpertRegistry | None = None,
        redactor: PHIRedactor | None = None,
    ):
        self.provider = provider
        self.experts = experts or default_expert_registry()
        self.redactor = redactor or PHIRedactor()

    def run(self, agent, raw_text: str, *, submit_findings: bool = True) -> ExecutionResult:
        # Stage 0 — PHI redaction, BEFORE any model call. The model only sees red_text.
        red_text, phi = self.redactor.redact_typed(raw_text)

        # Resolve the agent's declared experts -> their tools + a name->method dispatch table.
        dispatch: dict = {}
        tools: list[dict] = []
        for eid in agent.experts:
            expert = self.experts.get(eid)
            if expert is None:
                continue
            for schema in build_expert_tools(expert):
                fname = schema["function"]["name"]
                tools.append(schema)
                dispatch[fname] = getattr(expert, fname)
        # submit_findings is the extract surface's terminal tool (structured entities for
        # evidence highlighting). Tool agents (submit_findings=False) instead answer in prose
        # Markdown — captured via the no-tool-calls branch below, mirroring Corti.
        if submit_findings:
            tools.append(SUBMIT_FINDINGS_TOOL)

        messages: list[dict] = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": red_text},
        ]

        stages: list[StageObservation] = []
        usage = {
            "provider": getattr(self.provider, "name", "unknown"),
            "model": getattr(self.provider, "model", ""),
            "llm_calls": 0,
            "tool_calls": 0,
            "rounds": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

        findings: Optional[dict] = None
        final_message: Optional[str] = None

        for round_index in range(MAX_ROUNDS):
            # On the final allowed round, force the terminal tool so an over-researching
            # model still closes out with what it has gathered — never an empty run from
            # round exhaustion. (A provider that ignores tool_choice still degrades to
            # findings=None below: the bound is the floor, the forced submit the ceiling.)
            force = submit_findings and round_index == MAX_ROUNDS - 1
            tool_choice = (
                {"type": "function", "function": {"name": SUBMIT_FINDINGS}} if force else None
            )
            result = self.provider.chat(messages, tools, tool_choice=tool_choice)
            usage["llm_calls"] += 1
            usage["rounds"] += 1
            u = result.usage or {}
            usage["prompt_tokens"] += int(u.get("prompt_tokens", 0) or 0)
            usage["completion_tokens"] += int(u.get("completion_tokens", 0) or 0)

            if not result.tool_calls:
                # model answered in prose without calling a tool — done talking.
                final_message = result.content
                break

            # Append the assistant turn (must carry tool_calls before the tool messages).
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in result.tool_calls
                    ],
                }
            )

            terminated = False
            for tc in result.tool_calls:
                usage["tool_calls"] += 1

                if tc.name == SUBMIT_FINDINGS:
                    findings = tc.arguments
                    with _timed(stages, "submit", SUBMIT_FINDINGS) as obs:
                        n = len(tc.arguments.get("entities", []) if isinstance(tc.arguments, dict) else [])
                        obs.summary = f"提交 {n} 个事实"
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id,
                         "content": json.dumps({"status": "received"}, ensure_ascii=False)}
                    )
                    terminated = True
                    break

                method = dispatch.get(tc.name)
                with _timed(stages, "tool", tc.name) as obs:
                    if method is None:
                        content = json.dumps({"error": f"unknown tool: {tc.name}"}, ensure_ascii=False)
                        obs.summary = f"未知工具 {tc.name}"
                    else:
                        try:
                            out = method(**(tc.arguments if isinstance(tc.arguments, dict) else {}))
                            if isinstance(out, list):
                                out = out[:20]  # token-budget guard on broad search results
                            content = json.dumps(out, ensure_ascii=False, default=_json_default)
                            obs.summary = f"{tc.name} ok"
                        except Exception as e:  # a bad tool call must not kill the loop
                            content = json.dumps(
                                {"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False
                            )
                            obs.summary = f"{tc.name} 失败"
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})

            if terminated:
                break

        usage["stages_observed"] = len(stages)
        return ExecutionResult(
            redaction_text=red_text,
            phi=phi,
            final_message=final_message,
            findings=findings,
            stages=stages,
            usage=usage,
        )
