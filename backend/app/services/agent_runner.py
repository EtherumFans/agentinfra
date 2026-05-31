"""Agent Runner — execute an Agent by orchestrating multiple Experts.

iCoDer Agentic Framework equivalent: "Agent orchestrates Experts. When a user
sends a message to an Agent, the Agent:
1. Analyzes the request (optionally using LLM planning)
2. Selects which Experts to invoke from its expert_ids pool
3. Calls them in sequence or parallel
4. Aggregates results into a unified response

ALL execution paths are gated by DeterministicRuntime.
"""
import json
import logging
import time
import uuid
from typing import AsyncGenerator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.expert import Expert
from app.services.expert_runner import expert_runner
from app.services.llm_service import llm_service
from app.services.runtime import (
    runtime_registry, DeterministicRuntime, CaseState, GateOutcome,
)
from app.services.tool_registry import tool_registry as global_tool_registry
from app.services.contract_engine import (
    SymbolicState, evaluate_precondition, validate_postcondition,
    ContractResult, ContractViolation,
)
from app.services.permissions import PermissionPolicy, PermissionOutcome, PRESET_POLICIES

logger = logging.getLogger(__name__)

ROUTING_SYSTEM_PROMPT = """You are an intelligent routing system. Given a user's message and a list of available Experts,
determine which Experts should be called and in what order.

Available Experts:
{expert_list}

Respond with a JSON plan:
{{
  "reasoning": "Why these experts were chosen",
  "steps": [
    {{"expert_name": "exact name", "input_summary": "what to ask this expert", "reason": "why this expert"}}
  ]
}}

Rules:
- If a single Expert can handle the request, use only that one
- If the request requires multiple capabilities, chain multiple Experts
- Order matters: fact extraction before coding, coding before compliance check
- Skip Experts that are not relevant to the request"""


class AgentRunner:
    """Execute an Agent by orchestrating its bound Experts.

    Every execution path creates a DeterministicRuntime instance.
    State transitions, tool gates, and audit are enforced on every expert call.
    """

    async def run(
        self,
        agent: Agent,
        user_input: str,
        conversation_history: list[dict] | None = None,
        db: AsyncSession | None = None,
    ) -> dict:
        """Run the Agent with multi-Expert orchestration, gated by Runtime."""
        start = time.time()
        conversation_history = conversation_history or []
        run_id = f"AR-{uuid.uuid4().hex[:8]}"

        # --- Runtime: create instance ---
        rt = runtime_registry.get_or_create(run_id)
        rt.transition(CaseState.INGESTED, actor="agent_runner")
        rt.audit.record("agent_run_start", actor="agent_runner", payload={
            "agent_id": agent.id, "agent_name": agent.name,
            "input_length": len(user_input),
        })

        # Resolve bound experts
        experts = await self._resolve_experts(agent, db)

        # --- Runtime: timeout check + context ready ---
        rt.check_timeout()
        rt.transition(CaseState.CONTEXT_READY, actor="agent_runner")

        if not experts:
            # No experts bound — use Agent's own system_prompt directly
            gate = rt.guard("context_build", "agent_runner")
            if gate == GateOutcome.DENY:
                return await self._denied_result(agent, run_id, rt, start, db)
            rt.check_timeout()
            output = await self._run_single_expert(agent, user_input, conversation_history, None, rt)
            rt.guard_post({"output": output, "errors": []})
            rt.check_timeout()
            rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
            rt.transition(CaseState.ARCHIVED, actor="agent_runner")
            rt._total_processing_ms = int((time.time() - start) * 1000)
            if db:
                await rt.flush_to_db(db)
            return {
                "agent": agent.name, "expert_count": 0, "output": output,
                "routing": "direct",
                "run_id": run_id, "runtime_state": rt.state.value,
            }

        routing_strategy = (agent.config or {}).get("routing_strategy", "llm_plan")

        if routing_strategy == "tool_native":
            result = await self._run_tool_native(agent, user_input, conversation_history, start, rt)
            rt.transition(CaseState.ARCHIVED, actor="agent_runner")
            rt._total_processing_ms = int((time.time() - start) * 1000)
            if db:
                await rt.flush_to_db(db)
            result["run_id"] = run_id
            result["runtime_state"] = rt.state.value
            return result

        if routing_strategy in ("single_expert", "direct") or len(experts) == 1:
            default_exp = experts[0] if experts else None
            gate = rt.guard("extract_facts", "agent_runner")
            if gate == GateOutcome.DENY:
                return await self._denied_result(agent, run_id, rt, start, db)
            rt.check_timeout()
            output = await self._run_single_expert(agent, user_input, conversation_history, default_exp, rt)
            rt.guard_post({"output": output, "errors": []})
            rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
            rt.transition(CaseState.ARCHIVED, actor="agent_runner")
            rt._total_processing_ms = int((time.time() - start) * 1000)
            if db:
                await rt.flush_to_db(db)
            return {
                "agent": agent.name, "expert_count": 1, "output": output,
                "routing": "single_expert",
                "run_id": run_id, "runtime_state": rt.state.value,
            }

        if routing_strategy == "fixed_order":
            result = await self._run_fixed_order(agent, user_input, conversation_history, experts, start, rt)
        else:
            result = await self._run_llm_planned(agent, user_input, conversation_history, experts, start, rt)

        # --- Runtime: complete ---
        rt.transition(CaseState.ARCHIVED, actor="agent_runner")
        # Persist to DB
        rt._total_processing_ms = int((time.time() - start) * 1000)
        if db:
            await rt.flush_to_db(db)
        result["run_id"] = run_id
        result["runtime_state"] = rt.state.value
        return result

    async def stream(
        self,
        agent: Agent,
        user_input: str,
        conversation_history: list[dict] | None = None,
        db: AsyncSession | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream Agent response with multi-Expert orchestration, gated by Runtime."""
        conversation_history = conversation_history or []
        run_id = f"ARS-{uuid.uuid4().hex[:8]}"

        # --- Runtime: create instance ---
        rt = runtime_registry.get_or_create(run_id)
        rt.transition(CaseState.INGESTED, actor="agent_runner")
        rt.audit.record("agent_stream_start", actor="agent_runner", payload={
            "agent_id": agent.id, "agent_name": agent.name,
            "input_length": len(user_input),
        })

        # Resolve experts
        experts = await self._resolve_experts(agent, db)

        # --- Runtime: timeout check + context ready ---
        rt.check_timeout()
        rt.transition(CaseState.CONTEXT_READY, actor="agent_runner")

        if not experts:
            gate = rt.guard("context_build", "agent_runner")
            if gate == GateOutcome.DENY:
                yield json.dumps({"type": "error", "message": "Action denied by runtime guard", "run_id": run_id})
                return
            rt.check_timeout()
            async for token in self._stream_single(agent, user_input, conversation_history, None, rt):
                yield token
            rt.guard_post({"output": "stream_completed", "errors": []})
            rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
            rt.transition(CaseState.ARCHIVED, actor="agent_runner")
            if db:
                await rt.flush_to_db(db)
            yield json.dumps({
                "type": "done", "expert_count": 0, "routing": "direct",
                "run_id": run_id, "runtime_state": rt.state.value,
            })
            return

        routing_strategy = (agent.config or {}).get("routing_strategy", "llm_plan")

        if routing_strategy == "tool_native":
            async for token in self._stream_tool_native(agent, user_input, conversation_history, rt):
                yield token
            rt.transition(CaseState.ARCHIVED, actor="agent_runner")
            if db:
                await rt.flush_to_db(db)
            yield json.dumps({"type": "done", "routing": "tool_native", "run_id": run_id, "runtime_state": rt.state.value})
            return

        if routing_strategy in ("single_expert", "direct") or len(experts) == 1:
            default_exp = experts[0] if experts else None
            gate = rt.guard("extract_facts", "agent_runner")
            if gate == GateOutcome.DENY:
                yield json.dumps({"type": "error", "message": "Action denied by runtime guard", "run_id": run_id})
                return
            rt.check_timeout()
            async for token in self._stream_single(agent, user_input, conversation_history, default_exp, rt):
                yield token
            rt.guard_post({"output": "stream_completed", "errors": []})
            rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
            rt.transition(CaseState.ARCHIVED, actor="agent_runner")
            if db:
                await rt.flush_to_db(db)
            yield json.dumps({
                "type": "done", "expert_count": 1, "routing": "single_expert",
                "run_id": run_id, "runtime_state": rt.state.value,
            })
            return

        if routing_strategy == "fixed_order":
            async for token in self._stream_fixed_order(agent, user_input, conversation_history, experts, rt):
                yield token
        else:
            async for token in self._stream_llm_planned(agent, user_input, conversation_history, experts, rt):
                yield token

        rt.transition(CaseState.ARCHIVED, actor="agent_runner")
        if db:
            await rt.flush_to_db(db)
        yield json.dumps({"type": "done", "run_id": run_id, "runtime_state": rt.state.value})

    # ---- Internal methods ----

    async def _resolve_experts(self, agent: Agent, db: AsyncSession | None) -> list[Expert]:
        """Resolve the agent's expert_ids to actual Expert objects."""
        if not db or not agent.expert_ids:
            return []
        result = await db.execute(
            select(Expert).where(Expert.id.in_(agent.expert_ids))
        )
        return list(result.scalars().all())

    async def _run_single_expert(
        self, agent: Agent, user_input: str, history: list[dict],
        expert: Expert | None, rt: DeterministicRuntime,
    ) -> str:
        """Run with a single Expert (or Agent's own prompt if no Expert)."""
        if expert:
            action = f"call_{self._slug(expert.name)}"
            gate = rt.guard(action, "agent_runner")
            rt.audit.record("expert_call", actor="agent_runner", payload={
                "expert": expert.name, "action": action, "gate": gate.value,
            })
            if gate == GateOutcome.DENY:
                return f"[Runtime Denied] Action '{action}' blocked by safety gate."
            output = await expert_runner.run(expert, user_input, history, [])
            rt.guard_post({"output": output, "errors": []})
            return output
        # Use Agent's own system_prompt with LLM directly
        messages = [{"role": "system", "content": agent.system_prompt or f"You are {agent.name}."}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        result = await llm_service.chat(messages=messages, temperature=0.1)
        return result.get("content", "") if isinstance(result, dict) else str(result)

    async def _run_fixed_order(
        self, agent: Agent, user_input: str, history: list[dict],
        experts: list[Expert], start: float, rt: DeterministicRuntime,
    ) -> dict:
        """Call all experts in fixed order, pass output forward. Gated by Runtime."""
        results = []
        current_input = user_input
        for exp in experts:
            action = f"call_{self._slug(exp.name)}"
            gate = rt.guard(action, "agent_runner")
            rt.audit.record("expert_call", actor="agent_runner", payload={
                "expert": exp.name, "action": action, "gate": gate.value,
            })
            if gate == GateOutcome.DENY:
                results.append({"expert": exp.name, "output": f"[Denied] {action}"})
                continue
            output = await expert_runner.run(exp, current_input, [], [])
            rt.guard_post({"output": output, "errors": []})
            results.append({"expert": exp.name, "output": output[:500]})
            current_input = f"Previous expert ({exp.name}) output:\n{output}\n\nOriginal request:\n{user_input}"

        final = results[-1]["output"] if results else ""
        rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
        return {
            "agent": agent.name,
            "expert_count": len(experts),
            "routing": "fixed_order",
            "experts_used": [e.name for e in experts],
            "output": final,
            "steps": results,
            "processing_time_ms": int((time.time() - start) * 1000),
        }

    async def _run_llm_planned(
        self, agent: Agent, user_input: str, history: list[dict],
        experts: list[Expert], start: float, rt: DeterministicRuntime,
    ) -> dict:
        """Use LLM to plan which experts to call, then execute the plan. Gated by Runtime."""
        expert_list = "\n".join(
            f"- {e.name}: {e.description} (capabilities: {', '.join(e.capabilities or [])})"
            for e in experts
        )
        prompt = ROUTING_SYSTEM_PROMPT.format(expert_list=expert_list)

        plan = {"steps": []}
        try:
            plan = await llm_service.extract_json(
                prompt=prompt,
                text=user_input,
                schema_hint="plan with steps array"
            )
        except Exception as e:
            logger.warning(f"LLM planning failed for Agent {agent.name}: {e}, using fixed order")

        steps = plan.get("steps", [])
        if not steps:
            return await self._run_fixed_order(agent, user_input, history, experts, start, rt)

        name_map = {e.name: e for e in experts}
        results = []
        current_input = user_input

        for step in steps:
            exp_name = step.get("expert_name", "")
            exp = name_map.get(exp_name)
            if not exp:
                logger.warning(f"Expert '{exp_name}' not found in agent's pool, skipping")
                continue

            action = f"call_{self._slug(exp_name)}"
            gate = rt.guard(action, "agent_runner")
            rt.audit.record("expert_call", actor="agent_runner", payload={
                "expert": exp_name, "action": action, "gate": gate.value,
                "reason": step.get("reason", "")[:100],
            })
            if gate == GateOutcome.DENY:
                results.append({"expert": exp_name, "reason": step.get("reason", ""), "output": f"[Denied] {action}"})
                continue

            logger.info(f"Agent {agent.name}: calling {exp_name} for: {step.get('reason', '')[:80]}")
            output = await expert_runner.run(exp, current_input, [], [])
            rt.guard_post({"output": output, "errors": []})
            results.append({
                "expert": exp_name,
                "reason": step.get("reason", ""),
                "output": output[:500],
            })
            current_input = f"Previous expert ({exp_name}) output:\n{output}\n\nOriginal request:\n{user_input}"

        final = results[-1]["output"] if results else ""
        rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
        return {
            "agent": agent.name,
            "expert_count": len(steps),
            "routing": "llm_planned",
            "reasoning": plan.get("reasoning", ""),
            "experts_used": [r["expert"] for r in results],
            "output": final,
            "steps": results,
            "processing_time_ms": int((time.time() - start) * 1000),
        }

    async def _stream_single(
        self, agent: Agent, user_input: str, history: list[dict],
        expert: Expert | None, rt: DeterministicRuntime,
    ) -> AsyncGenerator[str, None]:
        """Stream from a single Expert. Gated by Runtime."""
        if expert:
            action = f"call_{self._slug(expert.name)}"
            gate = rt.guard(action, "agent_runner")
            rt.audit.record("expert_call", actor="agent_runner", payload={
                "expert": expert.name, "action": action, "gate": gate.value,
            })
            if gate == GateOutcome.DENY:
                yield json.dumps({"type": "error", "message": f"Action '{action}' denied by runtime guard"})
                return
            async for token in expert_runner.stream_run(expert, user_input, history):
                yield json.dumps({"type": "token", "text": token})
        else:
            messages = [{"role": "system", "content": agent.system_prompt or f"You are {agent.name}."}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_input})
            async for token in llm_service.chat_stream(messages=messages, temperature=0.1):
                yield json.dumps({"type": "token", "text": token})

    async def _stream_fixed_order(
        self, agent: Agent, user_input: str, history: list[dict],
        experts: list[Expert], rt: DeterministicRuntime,
    ) -> AsyncGenerator[str, None]:
        """Stream results from sequential expert calls. Gated by Runtime."""
        yield json.dumps({
            "type": "info",
            "message": f"Agent using {len(experts)} expert(s): {', '.join(e.name for e in experts)}",
        })

        current_input = user_input
        for i, exp in enumerate(experts):
            action = f"call_{self._slug(exp.name)}"
            gate = rt.guard(action, "agent_runner")
            rt.audit.record("expert_call", actor="agent_runner", payload={
                "expert": exp.name, "action": action, "gate": gate.value,
            })
            if gate == GateOutcome.DENY:
                yield json.dumps({"type": "error", "message": f"Step {i+1}: {exp.name} denied by runtime guard"})
                continue

            yield json.dumps({"type": "info", "message": f"Step {i+1}/{len(experts)}: {exp.name}"})

            accumulated = ""
            async for token in expert_runner.stream_run(exp, current_input, []):
                accumulated += token
                yield json.dumps({"type": "token", "text": token})

            current_input = f"Previous expert ({exp.name}) output:\n{accumulated[:1000]}\n\nOriginal request:\n{user_input}"

        rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
        yield json.dumps({
            "type": "done", "expert_count": len(experts), "routing": "fixed_order",
        })

    async def _stream_llm_planned(
        self, agent: Agent, user_input: str, history: list[dict],
        experts: list[Expert], rt: DeterministicRuntime,
    ) -> AsyncGenerator[str, None]:
        """Stream results from LLM-planned expert calls. Gated by Runtime."""
        expert_list = "\n".join(
            f"- {e.name}: {e.description} (capabilities: {', '.join(e.capabilities or [])})"
            for e in experts
        )
        prompt = ROUTING_SYSTEM_PROMPT.format(expert_list=expert_list)

        plan = {"steps": []}
        try:
            plan = await llm_service.extract_json(
                prompt=prompt, text=user_input, schema_hint="plan with steps array",
            )
        except Exception as e:
            logger.warning(f"LLM planning failed for Agent {agent.name}: {e}")

        steps = plan.get("steps", [])
        if not steps:
            async for token in self._stream_fixed_order(agent, user_input, history, experts, rt):
                yield token
            return

        yield json.dumps({
            "type": "info",
            "message": f"Planned {len(steps)} step(s): {plan.get('reasoning', '')[:100]}",
        })

        name_map = {e.name: e for e in experts}
        current_input = user_input
        for i, step in enumerate(steps):
            exp_name = step.get("expert_name", "")
            exp = name_map.get(exp_name)
            if not exp:
                continue

            action = f"call_{self._slug(exp_name)}"
            gate = rt.guard(action, "agent_runner")
            rt.audit.record("expert_call", actor="agent_runner", payload={
                "expert": exp_name, "action": action, "gate": gate.value,
                "reason": step.get("reason", "")[:100],
            })
            if gate == GateOutcome.DENY:
                yield json.dumps({"type": "error", "message": f"Step {i+1}: {exp_name} denied by runtime guard"})
                continue

            yield json.dumps({"type": "info", "message": f"Step {i+1}/{len(steps)}: {exp_name}"})

            accumulated = ""
            async for token in expert_runner.stream_run(exp, current_input, []):
                accumulated += token
                yield json.dumps({"type": "token", "text": token})

            current_input = f"Previous expert ({exp_name}) output:\n{accumulated[:1000]}\n\nOriginal request:\n{user_input}"

        rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")
        yield json.dumps({
            "type": "done", "expert_count": len(steps),
            "routing": "llm_planned", "reasoning": plan.get("reasoning", ""),
        })

    # ── Tool-Native Execution (Contract-Enforced) ──────────────────────────

    async def _run_tool_native(
        self, agent: Agent, user_input: str, history: list[dict],
        start: float, rt: DeterministicRuntime,
    ) -> dict:
        """Execute Agent using contract-enforced tool calling.

        The LLM autonomously decides which tools to call. The Harness enforces
        pre/post-conditions on every tool call. Contract violations are fed back
        to the LLM for correction.

        Tools are resolved from agent.config.tools.enabled, with Tier 1 tools
        auto-injected when agent.config.tools.tier1_enforce is true.
        """
        tools_config = (agent.config or {}).get("tools", {})
        enabled_ids = tools_config.get("enabled", [])
        tier1_enforce = tools_config.get("tier1_enforce", True)

        # Resolve tool IDs — if empty, default to all Tier 2 coding tools
        if not enabled_ids:
            enabled_ids = [
                "extract_evidence", "search_icd10_index", "search_icd9_index",
                "assign_diagnosis_code", "assign_procedure_code",
                "verify_evidence", "format_report",
            ]

        # Auto-inject Tier 1 accuracy tools
        if tier1_enforce:
            enabled_ids = self._inject_tier1_tools(enabled_ids)

        # Resolve tool definitions from registry
        tool_defs = []
        for tid in enabled_ids:
            td = global_tool_registry.get(tid)
            if td:
                tool_defs.append(td)
            else:
                rt.audit.record("tool_not_found", actor="agent_runner", payload={"tool_id": tid})

        if not tool_defs:
            rt.audit.record("no_tools_available", actor="agent_runner")
            return {
                "agent": agent.name, "output": "No tools available for this agent.",
                "routing": "tool_native", "tools_used": [],
            }

        rt.audit.record("tool_native_start", actor="agent_runner", payload={
            "agent_id": agent.id, "tool_count": len(tool_defs),
            "tool_ids": [t.id for t in tool_defs],
        })

        # Build OpenAI-format tool definitions for LLM
        openai_tools = self._build_openai_tools(tool_defs)
        system_prompt = self._build_tool_system_prompt(agent, tool_defs)

        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_input},
        ]

        # Initialize contract-enforced symbolic state
        symbolic_state = SymbolicState()
        executed_tools: list[str] = []
        max_iterations = 20
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            rt.check_timeout()

            try:
                response = await llm_service.chat_with_tools(
                    messages=messages, tools=openai_tools, temperature=0.1,
                )
            except Exception as e:
                logger.error(f"LLM tool-calling error: {e}")
                break

            # Check if LLM is done
            if isinstance(response, dict) and response.get("content"):
                final_content = response["content"]
                break

            # Check for tool calls
            tool_calls = response.get("tool_calls", []) if isinstance(response, dict) else []
            if not tool_calls:
                # No tool calls and no content — provide default output
                final_content = str(response)
                break

            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                func_args_str = tc.get("function", {}).get("arguments", "{}")

                try:
                    func_args = json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                except json.JSONDecodeError:
                    func_args = {}

                # Find tool definition
                td = global_tool_registry.get(func_name)
                if not td:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{iteration}"),
                        "content": json.dumps({"error": f"Tool '{func_name}' not found"}),
                    })
                    continue

                # ── Harness: pre_check ──
                pre_result, pre_reason = evaluate_precondition(
                    " and ".join(td.requires) if td.requires else "",
                    symbolic_state,
                )

                if pre_result == ContractResult.DENY:
                    rt.audit.record("contract_pre_denied", actor="agent_runner", payload={
                        "tool": func_name, "reason": pre_reason,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{iteration}"),
                        "content": json.dumps({
                            "error": "Contract precondition not met",
                            "reason": pre_reason,
                            "suggestion": f"Call required prerequisite tools first. Required: {td.requires}",
                        }),
                    })
                    continue

                # ── Harness: permission check ──
                perm_policy = self._load_permission_policy(agent)
                perm_outcome = perm_policy.check(func_name)

                if perm_outcome == PermissionOutcome.DENY:
                    rt.audit.record("permission_denied", actor="agent_runner", payload={
                        "tool": func_name, "reason": "Tool not allowed in current policy",
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{iteration}"),
                        "content": json.dumps({
                            "error": "Permission denied",
                            "reason": f"Tool '{func_name}' is not allowed by the current permission policy.",
                            "suggestion": "Update the agent's permission policy or use a different tool.",
                        }),
                    })
                    continue

                if perm_outcome == PermissionOutcome.NEEDS_HUMAN:
                    rt.audit.record("permission_needs_human", actor="agent_runner", payload={
                        "tool": func_name,
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{iteration}"),
                        "content": json.dumps({
                            "error": "Human approval required",
                            "reason": f"Tool '{func_name}' requires human approval before execution.",
                            "suggestion": "This tool affects clinical decisions. A human reviewer must approve it.",
                        }),
                    })
                    continue

                # ── Execute tool ──
                try:
                    result = await global_tool_registry.execute(func_name, func_args)
                except Exception as e:
                    logger.error(f"Tool execution error [{func_name}]: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{iteration}"),
                        "content": json.dumps({"error": f"Tool execution failed: {str(e)}"}),
                    })
                    continue

                # ── Harness: post_check ──
                all_passed = True
                for guarantee_expr in td.guarantees:
                    post_result, post_reason = validate_postcondition(
                        guarantee_expr, result, symbolic_state,
                    )
                    if post_result == ContractResult.DENY:
                        rt.audit.record("contract_post_denied", actor="agent_runner", payload={
                            "tool": func_name, "reason": post_reason,
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", f"call_{iteration}"),
                            "content": json.dumps({
                                "error": "Contract postcondition not met",
                                "reason": post_reason,
                                "output": str(result)[:500],
                            }),
                        })
                        all_passed = False
                        break

                if not all_passed:
                    continue

                # ── Commit verified result to state ──
                symbolic_state.merge(result, tool_id=func_name)
                perm_policy.record(func_name)  # Track invocation count
                executed_tools.append(func_name)

                # Feed verified result back to LLM
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{iteration}"),
                    "content": json.dumps(result, ensure_ascii=False),
                })

                rt.audit.record("tool_executed", actor="agent_runner", payload={
                    "tool": func_name, "iteration": iteration,
                    "state_keys": list(symbolic_state._data.keys()),
                })

            # After processing all tool calls in this round, check if LLM should continue
            if not tool_calls:
                break

        # Build final output
        final = final_content if 'final_content' in dir() else ""
        if not final:
            # No explicit text response — synthesize from state
            final = self._synthesize_tool_output(symbolic_state, executed_tools)

        rt.guard_post({"output": final, "errors": []})
        rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")

        return {
            "agent": agent.name,
            "tool_count": len(tool_defs),
            "tools_used": executed_tools,
            "output": final,
            "routing": "tool_native",
            "state_snapshot": symbolic_state.snapshot(),
            "processing_time_ms": int((time.time() - start) * 1000),
        }

    async def _stream_tool_native(
        self, agent: Agent, user_input: str, history: list[dict],
        rt: DeterministicRuntime,
    ) -> AsyncGenerator[str, None]:
        """Stream version of tool-native execution.

        Yields step_start, token, and tool_result events so the frontend
        can show real-time progress of each tool call.
        """
        tools_config = (agent.config or {}).get("tools", {})
        enabled_ids = tools_config.get("enabled", [])
        tier1_enforce = tools_config.get("tier1_enforce", True)

        if not enabled_ids:
            enabled_ids = [
                "extract_evidence", "search_icd10_index", "search_icd9_index",
                "assign_diagnosis_code", "assign_procedure_code",
                "verify_evidence", "format_report",
            ]
        if tier1_enforce:
            enabled_ids = self._inject_tier1_tools(enabled_ids)

        tool_defs = [td for tid in enabled_ids if (td := global_tool_registry.get(tid))]
        if not tool_defs:
            yield json.dumps({"type": "error", "message": "No tools available"})
            return

        openai_tools = self._build_openai_tools(tool_defs)
        system_prompt = self._build_tool_system_prompt(agent, tool_defs)

        messages = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_input},
        ]

        symbolic_state = SymbolicState()
        max_iterations = 20

        for iteration in range(max_iterations):
            rt.check_timeout()

            try:
                response = await llm_service.chat_with_tools(
                    messages=messages, tools=openai_tools, temperature=0.1,
                )
            except Exception as e:
                yield json.dumps({"type": "error", "message": f"LLM error: {str(e)}"})
                break

            if isinstance(response, dict) and response.get("content"):
                final = response["content"]
                yield json.dumps({"type": "token", "text": final})
                break

            tool_calls = response.get("tool_calls", []) if isinstance(response, dict) else []
            if not tool_calls:
                break

            for tc in tool_calls:
                func_name = tc.get("function", {}).get("name", "")
                func_args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    func_args = json.loads(func_args_str) if isinstance(func_args_str, str) else func_args_str
                except json.JSONDecodeError:
                    func_args = {}

                td = global_tool_registry.get(func_name)
                if not td:
                    yield json.dumps({"type": "tool_error", "tool": func_name, "error": "Tool not found"})
                    continue

                yield json.dumps({
                    "type": "step_start", "tool": func_name, "tool_name": td.name,
                    "tier": td.tier.value,
                })

                # Pre-check
                pre_result, pre_reason = evaluate_precondition(
                    " and ".join(td.requires) if td.requires else "",
                    symbolic_state,
                )
                if pre_result == ContractResult.DENY:
                    yield json.dumps({
                        "type": "contract_denied", "tool": func_name,
                        "stage": "precondition", "reason": pre_reason,
                    })
                    messages.append({
                        "role": "tool", "tool_call_id": tc.get("id", f"call_{iteration}"),
                        "content": json.dumps({"error": "Precondition not met", "reason": pre_reason}),
                    })
                    continue

                # Permission check
                perm_policy = self._load_permission_policy(agent)
                perm_outcome = perm_policy.check(func_name)
                if perm_outcome != PermissionOutcome.ALLOW:
                    yield json.dumps({
                        "type": "permission_denied", "tool": func_name,
                        "reason": perm_outcome.value,
                    })
                    continue

                # Execute
                try:
                    result = await global_tool_registry.execute(func_name, func_args)
                except Exception as e:
                    yield json.dumps({"type": "tool_error", "tool": func_name, "error": str(e)})
                    continue

                # Post-check
                all_passed = True
                for guarantee_expr in td.guarantees:
                    post_result, post_reason = validate_postcondition(
                        guarantee_expr, result, symbolic_state,
                    )
                    if post_result == ContractResult.DENY:
                        yield json.dumps({
                            "type": "contract_denied", "tool": func_name,
                            "stage": "postcondition", "reason": post_reason,
                        })
                        all_passed = False
                        break

                if not all_passed:
                    continue

                symbolic_state.merge(result, tool_id=func_name)

                yield json.dumps({
                    "type": "tool_result", "tool": func_name,
                    "summary": str(result)[:200],
                })

                messages.append({
                    "role": "tool", "tool_call_id": tc.get("id", f"call_{iteration}"),
                    "content": json.dumps(result, ensure_ascii=False),
                })

        rt.transition(CaseState.FACTS_EXTRACTED, actor="agent_runner")

    def _load_permission_policy(self, agent: Agent) -> PermissionPolicy:
        """Load the agent's permission policy from config."""
        perm_config = (agent.config or {}).get("permissions", {})
        preset = (agent.config or {}).get("permission_preset", "")

        if preset and preset in PRESET_POLICIES:
            return PRESET_POLICIES[preset]["policy"]

        if perm_config:
            return PermissionPolicy.from_config(perm_config)

        # Default: full_access for backward compatibility
        return PermissionPolicy.full_access()

    def _inject_tier1_tools(self, enabled_ids: list[str]) -> list[str]:
        """Auto-inject Tier 1 accuracy guarantee tools based on enabled Tier 2 tools."""
        result = list(enabled_ids)
        seen = set(result)
        tags_needed: set[str] = set()

        # Collect accuracy tags from enabled tools
        for tid in enabled_ids:
            td = global_tool_registry.get(tid)
            if td:
                tags_needed.update(td.accuracy_tags)

        # Inject injectable Tier 1 tools that match needed tags
        for tag in tags_needed:
            for injectable in global_tool_registry.get_injectable_by_tag(tag):
                if injectable.id not in seen:
                    result.append(injectable.id)
                    seen.add(injectable.id)

        # Always inject safety tools if not present
        for safety_id in ["guard_input", "guard_output"]:
            if safety_id not in seen:
                result.append(safety_id)
                seen.add(safety_id)

        return result

    def _build_openai_tools(self, tool_defs: list) -> list[dict]:
        """Convert ToolDefinitions to OpenAI function-calling format."""
        tools = []
        for td in tool_defs:
            properties = {}
            required = []

            if td.input_schema:
                properties = td.input_schema.get("properties", {})
                required = td.input_schema.get("required", [])

            tools.append({
                "type": "function",
                "function": {
                    "name": td.id,
                    "description": (
                        f"[Tier {td.tier.value}] {td.description}"
                        + (f" Requires: {', '.join(td.requires)}" if td.requires else "")
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        return tools

    def _build_tool_system_prompt(self, agent: Agent, tool_defs: list) -> str:
        """Build system prompt that explains the tool contract model to the LLM."""
        base = agent.system_prompt or f"You are {agent.name}."

        tool_descriptions = "\n".join(
            f"- {td.id} (Tier {td.tier.value}, {td.category}): {td.description}"
            for td in tool_defs
        )

        tier1_tools = [td.id for td in tool_defs if td.tier.value == 1]
        tier1_desc = ", ".join(tier1_tools) if tier1_tools else "None"

        contract_instructions = f"""
AVAILABLE TOOLS:
{tool_descriptions}

CONTRACT RULES (IMPORTANT):
- Tier 1 tools ({tier1_desc}) are DETERMINISTIC (zero LLM). They provide verified data.
- Some tools have PRECONDITIONS. If you call a tool before its prerequisites are met,
  the system will REJECT the call and tell you what to do first.
- Some tools have POSTCONDITIONS. If your tool output fails validation,
  the system will REJECT the result.
- Always read the rejection message and adjust your plan accordingly.
- You have freedom in tool ordering, but logical dependencies must be respected.
- Verify all codes against the ICD index before finalizing (call search_icd10_index).
- Evidence ranking and confidence calibration are automatically injected when needed.
"""

        return f"{base}\n\n{contract_instructions}"

    def _synthesize_tool_output(self, state: SymbolicState, tools_used: list[str]) -> str:
        """Synthesize a human-readable output from the symbolic state."""
        parts = []

        # Diagnosis codes
        candidates = state.get("diagnosis_candidates", [])
        if candidates:
            codes = [
                f"- {c.get('assigned_code', c.get('code', '?'))}: {c.get('name', 'Unknown')}"
                for c in candidates[:20]
            ]
            parts.append(f"## 诊断编码 ({len(candidates)}个)\n" + "\n".join(codes))

        # Evidence ranking
        ranking = state.get("evidence_ranking", {})
        if ranking:
            parts.append(f"\n## 证据排名\n{len(ranking.get('ranked_candidates', []))} 个编码已排名, "
                         f"{len(ranking.get('unsupported_codes', []))} 个无证据支持")

        # Confidence
        routing = state.get("routing_decisions", [])
        if routing:
            tiers = {"auto": 0, "review": 0, "escalate": 0}
            for r in routing:
                t = r.get("tier", "review")
                tiers[t] = tiers.get(t, 0) + 1
            parts.append(f"\n## 置信度校准\nAUTO: {tiers['auto']}, REVIEW: {tiers['review']}, "
                         f"ESCALATE: {tiers['escalate']}")

        # Report
        report = state.get("report", "")
        if report:
            parts.append(f"\n## 审核报告\n{report[:2000]}")

        # Tool summary
        parts.append(f"\n\n---\n*工具调用序列: {' → '.join(tools_used)}*")

        return "\n".join(parts) if parts else "No output generated. Tools executed: " + ", ".join(tools_used)

    async def _denied_result(self, agent: Agent, run_id: str, rt: DeterministicRuntime,
                             start: float, db=None) -> dict:
        """Build a result dict when a Runtime gate has denied execution."""
        rt.audit.record("execution_denied", actor="agent_runner")
        rt.transition(CaseState.ARCHIVED, actor="agent_runner")
        rt._total_processing_ms = int((time.time() - start) * 1000)
        if db:
            await rt.flush_to_db(db)
        return {
            "agent": agent.name, "expert_count": 0,
            "output": "Request denied by safety gate. Please revise your input.",
            "routing": "denied",
            "run_id": run_id, "runtime_state": rt.state.value,
            "processing_time_ms": int((time.time() - start) * 1000),
        }

    @staticmethod
    def _slug(name: str) -> str:
        """Convert an expert name to a slug for guard actions."""
        return name.lower().replace(" ", "_").replace("-", "_")


agent_runner = AgentRunner()
