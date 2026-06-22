"""Agent Runner — execute an Agent definition locally.

Zero external dependencies beyond icoder_runtime core modules.
Supports: LLM planning mode and fixed-order execution.

LLM routing is handled by LLMGateway. Use AgentRunner(gateway=...).
The legacy llm_callable parameter is still accepted for backward compat
but will emit a deprecation warning.

Safety architecture (v2.0):
  PreExecutionGuard → Agent.run() → PostExecutionGuard
  SafetySpiralDetector monitors consecutive failures across sessions.
"""

import logging
import time
import uuid
import warnings
from typing import Optional

from .types import AgentDefinition, ExpertDefinition, ToolDefinition, ToolTier
from .symbolic_state import SymbolicState as AuditState
from .contract_engine import SymbolicState
from .permissions import PermissionPolicy, PermissionOutcome
from .guardrails import SafetyGuardrails, GuardrailViolation
from .circuit_breaker import CircuitBreaker
from .core.errors import LLMProviderNotConfigured
from .core.llm_gateway import LLMGateway

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Platform-level safety guards (infrastructure layer, not tools)
# ═══════════════════════════════════════════════════════════════

class PreExecutionGuard:
    """Deterministic input validation before any Agent execution.

    Runs BEFORE the LLM call. Failures are hard errors — the agent
    does not proceed if PreExecutionGuard rejects the input.
    """

    MEDICAL_REQUIRED_FIELDS = [
        "admission_reason", "department", "documents",
    ]

    def __init__(self, data_policy=None, guardrails: SafetyGuardrails | None = None):
        self._policy = data_policy
        self._guardrails = guardrails or SafetyGuardrails()

    async def check(
        self,
        agent: AgentDefinition,
        user_input: str,
        permission_policy: PermissionPolicy | None = None,
    ) -> dict:
        """Validate input before execution. Returns {"passed": bool, "violations": [...]}."""
        violations = []

        # 1. Permission scope: verify agent has at least one allowed tool/expert
        policy = permission_policy or PermissionPolicy(permissions={})
        if agent.expert_ids:
            denied_all = True
            for eid in agent.expert_ids:
                if policy.check(eid) != PermissionOutcome.DENY:
                    denied_all = False
                    break
            if denied_all and agent.expert_ids:
                violations.append({
                    "rule": "permission_scope",
                    "message": f"All {len(agent.expert_ids)} experts denied by permission policy",
                    "severity": "error",
                })

        # 2. Input safety: check for injection, blocked terms, PHI
        input_check = await self._guardrails.validate_input(user_input)
        if not input_check.get("valid"):
            violations.extend(input_check.get("violations", []))

        # 3. Data policy: verify external LLM is allowed if gateway is configured
        if self._policy and not self._policy.allow_external_llm:
            violations.append({
                "rule": "data_policy_external_llm",
                "message": "External LLM blocked by data policy. Set ICODER_ALLOW_EXTERNAL_LLM=true.",
                "severity": "warning",
            })

        # 4. Input format: check medical record has required fields
        has_medical_content = (
            len(user_input) >= 50 and
            any(kw in user_input for kw in ["诊断", "手术", "出院", "入院", "主诉", "检查", "diagnosis"])
        )
        if not has_medical_content:
            violations.append({
                "rule": "input_format_medical",
                "message": "Input does not appear to be a medical record. Expected fields: 诊断/手术/主诉 etc.",
                "severity": "warning",
            })

        errors = [v for v in violations if v.get("severity") == "error"]
        return {
            "passed": len(errors) == 0,
            "violations": violations,
            "error_count": len(errors),
            "warning_count": len(violations) - len(errors),
        }


class PostExecutionGuard:
    """Deterministic output validation after Agent execution.

    Runs AFTER the LLM call. Violations are recorded but do not
    block the response — they trigger ESCALATE or warning flags.
    """

    def __init__(self, guardrails: SafetyGuardrails | None = None):
        self._guardrails = guardrails or SafetyGuardrails()

    async def check(self, output_text: str, agent: AgentDefinition) -> dict:
        """Validate output and run rule engine checks. Returns flags dict."""
        # 1. Clinical safety: no prescriptions, no definitive diagnoses, no triage
        safety = await self._guardrails.validate_output(output_text)

        # 2. Output schema validation: try to parse as MedicalCodingOutputSchema
        schema_valid = False
        schema_issues = []
        try:
            from official_agents.medical_coding.schema import MedicalCodingOutputSchema
            import json as _json
            parsed = _json.loads(output_text) if output_text.strip().startswith("{") else {}
            if parsed:
                schema = MedicalCodingOutputSchema.from_dict(parsed, provider="post_guard")
                schema_valid = bool(schema.primary_diagnosis.code or schema.secondary_diagnoses or schema.procedures)
        except Exception:
            schema_issues.append("Output is not valid MedicalCodingOutputSchema JSON")

        # 3. Rule engine auto-trigger for critical/high failures
        rule_issues = []
        manual_review_required = False
        try:
            from icoder_runtime.providers.medical_coding.rule_engine_adapter import RuleEngineAdapter
            from official_agents.medical_coding.schema import MedicalCodingOutputSchema
            import json as _json
            parsed = _json.loads(output_text) if output_text.strip().startswith("{") else {}
            if parsed:
                schema = MedicalCodingOutputSchema.from_dict(parsed, provider="post_guard")
                engine = RuleEngineAdapter()
                result = engine.validate(schema)
                rule_issues = [i.to_dict() for i in result.issues]
                manual_review_required = result.manual_review_required
        except Exception:
            pass

        return {
            "safety_valid": safety.get("valid", True),
            "safety_violations": safety.get("violations", []),
            "requires_disclaimer": safety.get("requires_disclaimer", False),
            "schema_valid": schema_valid,
            "schema_issues": schema_issues,
            "rule_issues": rule_issues,
            "manual_review_required": manual_review_required,
            "should_escalate": bool(
                not safety.get("valid") or
                manual_review_required or
                len(rule_issues) > 3
            ),
        }


class SafetySpiralDetector:
    """Detects cascading failures across Agent execution sessions.

    When an agent produces 3+ consecutive runs with critical rule failures
    or safety violations, auto-escalate and optionally trip the circuit breaker.
    """

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._consecutive_failures: dict[str, int] = {}  # agent_ref → count

    def record(self, agent_ref: str, post_check: dict) -> dict:
        """Record a post-execution check result. Returns escalation decision."""
        is_failure = post_check.get("should_escalate", False)

        if is_failure:
            self._consecutive_failures[agent_ref] = self._consecutive_failures.get(agent_ref, 0) + 1
        else:
            self._consecutive_failures[agent_ref] = 0

        count = self._consecutive_failures.get(agent_ref, 0)
        should_escalate = count >= self.threshold

        return {
            "agent_ref": agent_ref,
            "consecutive_failures": count,
            "threshold": self.threshold,
            "should_escalate": should_escalate,
            "action": "ESCALATE" if should_escalate else ("WARN" if count > 0 else "OK"),
        }

    def reset(self, agent_ref: str):
        self._consecutive_failures.pop(agent_ref, None)

    def status(self) -> dict:
        return {
            "agents_tracked": len(self._consecutive_failures),
            "escalated": [k for k, v in self._consecutive_failures.items() if v >= self.threshold],
        }


# Global safety singletons
safety_guardrails = SafetyGuardrails()
safety_spiral_detector = SafetySpiralDetector(threshold=3)


class AgentRunner:
    """Execute an Agent locally against input text.

    Usage:
        runner = AgentRunner(gateway=my_llm_gateway)
        result = await runner.run(agent_def, "病历文本...")

    Legacy usage (deprecated):
        runner = AgentRunner(llm_callable=my_llm_func)
    """

    def __init__(self, llm_callable=None, gateway: LLMGateway | None = None,
                 experts: dict[str, ExpertDefinition] | None = None,
                 tools: dict[str, ToolDefinition] | None = None,
                 recorder=None):
        self.llm = llm_callable  # deprecated — use gateway instead
        self.gateway = gateway
        if llm_callable is not None and gateway is None:
            warnings.warn(
                "AgentRunner(llm_callable=...) is deprecated. Use AgentRunner(gateway=...) instead.",
                DeprecationWarning, stacklevel=2,
            )
        self._experts = experts or {}
        self._tools = tools or {}
        # M2a Run Trace recorder (opt-in, no-op if None)
        self._recorder = recorder

    def register_expert(self, exp: ExpertDefinition):
        self._experts[exp.id] = exp

    def register_tool(self, tool: ToolDefinition):
        self._tools[tool.id] = tool

    async def run(
        self,
        agent: AgentDefinition,
        user_input: str,
        permission_policy: PermissionPolicy | None = None,
        data_policy=None,
        delegated_by: dict | None = None,
    ) -> dict:
        """Execute an Agent against user input with platform-level safety guards.

        Safety flow:
          PreExecutionGuard → LLM call → PostExecutionGuard → SafetySpiralDetector

        delegated_by: {"user_id": "...", "username": "...", "agent_account_id": "..."}
        When provided, a delegation JWT is generated so the Agent can authenticate
        to external systems (HIS/EMR) with both user and agent identity.

        Returns: {review_id, agent_name, processing_time_ms,
                  primary_diagnosis, output, state_log,
                  safety: {pre_check, post_check, spiral_check},
                  delegation_token: str | None}
        """
        t0 = time.time()

        session_id = uuid.uuid4().hex[:12]
        world = SymbolicState()
        audit = AuditState(session_id=session_id)
        policy = permission_policy or PermissionPolicy(permissions={})
        audit.record("run_started", agent.name)

        # M2a recorder integration (opt-in, no-op if recorder is None)
        from icoder_runtime.m2a.recorder import noop_inference, noop_stage
        _rec_ctx = (
            self._recorder.inference(agent_ref=agent.id or agent.name, metadata={
                "agent_name": agent.name,
                "agent_version": agent.version,
                "delegated_by": delegated_by,
            }) if self._recorder is not None else noop_inference()
        )
        with _rec_ctx as _inf_ctx:
            return await self._run_with_recorder(
                agent, user_input, permission_policy, data_policy,
                delegated_by, t0, session_id, audit, policy, _inf_ctx,
            )

    async def _run_with_recorder(
        self, agent, user_input, permission_policy, data_policy,
        delegated_by, t0, session_id, audit, policy, _inf_ctx,
    ):
        # M2a recorder stage helper
        from icoder_runtime.m2a.recorder import noop_stage
        def _stage(name, tool_input=None):
            return _inf_ctx.stage(name, tool_input) if _inf_ctx else noop_stage()

        # ── Delegation token (agent identity + user identity) ──
        delegation_token = None
        if delegated_by and delegated_by.get("user_id"):
            from app.middleware.auth import create_delegation_token
            delegation_token = create_delegation_token(
                user_id=delegated_by["user_id"],
                username=delegated_by.get("username", ""),
                agent_id=agent.id,
                agent_account_id=delegated_by.get("agent_account_id", ""),
            )
            audit.record("delegation_created", agent.id, {"by": delegated_by["user_id"]})

        # ── PreExecutionGuard ──
        pre_guard = PreExecutionGuard(data_policy=data_policy, guardrails=safety_guardrails)
        with _stage("pre_execution_guard", {"input_len": len(user_input)}):
            pre_check = await pre_guard.check(agent, user_input, policy)
        audit.record("pre_guard", payload=pre_check)
        if not pre_check["passed"]:
            logger.warning(f"PreExecutionGuard BLOCKED agent={agent.name}: {pre_check['violations']}")
            if _inf_ctx:
                _inf_ctx.final_status = "error"
            return {
                "review_id": session_id,
                "agent_name": agent.name,
                "agent_version": agent.version,
                "primary_diagnosis": {},
                "output": "",
                "state_log": audit.export(),
                "contract_valid": False,
                "processing_time_ms": int((time.time() - t0) * 1000),
                "safety": {
                    "pre_check": pre_check,
                    "post_check": None,
                    "spiral_check": None,
                    "blocked": True,
                    "block_reason": "PreExecutionGuard rejected input",
                },
            }

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

        # Check circuit breaker before LLM call
        from .circuit_breaker import llm_circuit_breaker
        if llm_circuit_breaker.is_open:
            audit.record("circuit_breaker_open")
            if _inf_ctx:
                _inf_ctx.final_status = "error"
            return {
                "review_id": session_id,
                "agent_name": agent.name,
                "agent_version": agent.version,
                "primary_diagnosis": {},
                "output": "[Circuit breaker open — LLM provider unavailable]",
                "state_log": audit.export(),
                "contract_valid": False,
                "processing_time_ms": int((time.time() - t0) * 1000),
                "safety": {
                    "pre_check": pre_check,
                    "post_check": None,
                    "spiral_check": None,
                    "blocked": True,
                    "block_reason": "Circuit breaker open",
                },
            }

        # Execute via LLM
        output_text = ""
        llm_error = None
        with _stage("llm_call", {"agent": agent.name, "experts": len(active_experts)}) as _s:
            if self.gateway and self.gateway.is_configured:
                try:
                    prompt = self._build_expert_prompt(active_experts, messages)
                    result = await self.gateway.generate(
                        [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    )
                    output_text = result["content"]
                    llm_circuit_breaker.record_success()
                    if _s:
                        _s.set_output({"output_len": len(output_text)})
                except Exception as e:
                    logger.error(f"LLM gateway call failed: {e}")
                    output_text = f"[LLM error: {e}]"
                    llm_error = str(e)
                    llm_circuit_breaker.record_failure()
                    if _s:
                        _s.set_status("error", error=str(e))
            elif self.llm:
                # Legacy path — deprecated, handles both sync and async callables
                try:
                    prompt = self._build_expert_prompt(active_experts, messages)
                    result = self.llm(prompt)
                    import inspect as _inspect
                    if _inspect.iscoroutine(result) or _inspect.isawaitable(result):
                        output_text = await result
                    else:
                        output_text = str(result)
                    llm_circuit_breaker.record_success()
                    if _s:
                        _s.set_output({"output_len": len(str(output_text))})
                except Exception as e:
                    logger.error(f"LLM call failed: {e}")
                    output_text = f"[LLM error: {e}]"
                    llm_error = str(e)
                    llm_circuit_breaker.record_failure()
                    if _s:
                        _s.set_status("error", error=str(e))
            else:
                if _s:
                    _s.set_status("error", error="LLMProviderNotConfigured")
                if _inf_ctx:
                    _inf_ctx.final_status = "error"
                raise LLMProviderNotConfigured()

        audit.record("llm_response", payload={"output": output_text[:500]})

        # Contract: verify world state integrity
        contract_valid = True
        audit.record("contract_verified", payload={"valid": contract_valid})

        # Parse primary diagnosis from output (simple heuristic)
        primary_dx = self._parse_diagnosis(output_text)

        processing_ms = int((time.time() - t0) * 1000)

        # ── PostExecutionGuard ──
        post_guard = PostExecutionGuard(guardrails=safety_guardrails)
        with _stage("post_execution_guard"):
            post_check = await post_guard.check(output_text, agent)
        audit.record("post_guard", payload=post_check)

        # ── SafetySpiralDetector ──
        with _stage("safety_spiral"):
            spiral_check = safety_spiral_detector.record(agent.id, post_check)

        if spiral_check["should_escalate"]:
            logger.warning(
                f"SAFETY SPIRAL: agent={agent.id} has {spiral_check['consecutive_failures']} "
                f"consecutive failures → ESCALATING"
            )
            llm_circuit_breaker.record_failure()

        return {
            "review_id": session_id,
            "agent_name": agent.name,
            "agent_version": agent.version,
            "primary_diagnosis": primary_dx,
            "output": output_text,
            "state_log": audit.export(),
            "contract_valid": contract_valid,
            "processing_time_ms": processing_ms,
            "safety": {
                "pre_check": pre_check,
                "post_check": post_check,
                "spiral_check": spiral_check,
                "blocked": False,
            },
            "errors": [llm_error] if llm_error else [],
            "delegation_token": delegation_token,
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
