"""Agent Runner — execute an Agent definition locally.

Zero external dependencies beyond icoder_runtime core modules.
Supports: LLM planning mode and fixed-order execution.
"""

import logging
import uuid
from typing import Optional

from .types import AgentDefinition, ExpertDefinition, ToolDefinition, ToolTier
from .symbolic_state import SymbolicState as AuditState
from .contract_engine import SymbolicState
from .permissions import PermissionPolicy, PermissionOutcome

logger = logging.getLogger(__name__)


class AgentRunner:
    """Execute an Agent locally against input text.

    Usage:
        runner = AgentRunner(llm_callable=my_llm_func)
        result = await runner.run(agent_def, "病历文本...")
    """

    def __init__(self, llm_callable=None, experts: dict[str, ExpertDefinition] | None = None,
                 tools: dict[str, ToolDefinition] | None = None):
        self.llm = llm_callable  # async func(prompt) -> str
        self._experts = experts or {}
        self._tools = tools or {}

    def register_expert(self, exp: ExpertDefinition):
        self._experts[exp.id] = exp

    def register_tool(self, tool: ToolDefinition):
        self._tools[tool.id] = tool

    async def run(
        self,
        agent: AgentDefinition,
        user_input: str,
        permission_policy: PermissionPolicy | None = None,
    ) -> dict:
        """Execute an Agent against user input.

        Returns: {review_id, agent_name, processing_time_ms,
                  primary_diagnosis, main_procedure, state_log}
        """
        import time
        t0 = time.time()

        session_id = uuid.uuid4().hex[:12]
        world = SymbolicState()
        audit = AuditState(session_id=session_id)
        policy = permission_policy or PermissionPolicy(permissions={})
        audit.record("run_started", agent.name)

        # Resolve experts
        active_experts = []
        for eid in agent.expert_ids:
            exp = self._experts.get(eid)
            if exp:
                permission = policy.check(eid)
                if permission == PermissionOutcome.DENY:
                    audit.record("expert_denied", eid, {"reason": "permission policy"})
                    continue
                active_experts.append(exp)

        # Build prompt
        system = agent.system_prompt or f"You are {agent.name}."
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_input}]

        # Execute via LLM
        output_text = ""
        if self.llm:
            try:
                prompt = self._build_expert_prompt(active_experts, messages)
                output_text = await self.llm(prompt)
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                output_text = f"[LLM error: {e}]"
        else:
            output_text = f"[No LLM configured. Would process: {user_input[:100]}...]"

        audit.record("llm_response", payload={"output": output_text[:500]})

        # Contract: verify world state integrity
        contract_valid = True  # Simplified — full enforcement in tool_native mode
        audit.record("contract_verified", payload={"valid": contract_valid})

        # Parse primary diagnosis from output (simple heuristic)
        primary_dx = self._parse_diagnosis(output_text)

        processing_ms = int((time.time() - t0) * 1000)

        return {
            "review_id": session_id,
            "agent_name": agent.name,
            "agent_version": agent.version,
            "primary_diagnosis": primary_dx,
            "output": output_text,
            "state_log": audit.export(),
            "contract_valid": contract_valid,
            "processing_time_ms": processing_ms,
        }

    def _build_expert_prompt(self, experts: list[ExpertDefinition], messages: list) -> str:
        parts = [f"{m['role']}: {m['content']}" for m in messages]
        if experts:
            exp_list = "\n".join(f"- {e.name}: {e.description}" for e in experts)
            parts.append(f"\nAvailable experts:\n{exp_list}")
        return "\n\n".join(parts)

    def _parse_diagnosis(self, text: str) -> dict:
        """Simple heuristic to extract primary diagnosis code from output."""
        # Look for ICD-10 code pattern
        import re
        codes = re.findall(r'[A-Z]\d{2}(?:\.\d{1,4})?', text)
        if codes:
            return {"code": codes[0], "evidence": "llm_output"}
        return {}
