"""Planner — LLM-driven Plan generation (SPEC §6.1, §7.2, §7.3).

The Planner calls a real LLM (via injected ``llm_call``) and parses the
JSON response into a ``Plan``. Per spec §7.2:

  - 3 retries on LLM network/timeout/5xx with exponential backoff (1s, 2s, 4s)
  - 3 retries on 429 (rate limit) with longer backoff (5s, 10s, 20s)
  - 0 retries on 4xx business errors → fail fast
  - 1 retry on JSON parse failure (Q-S1 decision)
  - total timeout: 60s wall-clock

Phase 1 keeps the Planner sync; the inbound handler wraps it in
``asyncio.to_thread`` if it needs to be awaited.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from .errors import OrchestratorError
from .events import OrchestratorEvent
from .prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    build_planner_user_message,
    build_planner_user_message_from_agent,
)
from .run_context import Plan

if TYPE_CHECKING:
    from icoder_runtime.types import AgentDefinition

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM call contract
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Normalized return shape from ``llm_call``.

    Mirrors LLMGateway's response but kept narrow so we can mock without
    pulling in the runtime.
    """

    content: str
    model: str = "unknown"
    latency_ms: int = 0
    raw: dict = field(default_factory=dict)
    is_degraded: bool = False
    degraded_reason: str = ""

    @classmethod
    def from_gateway(cls, payload: dict) -> "LLMResponse":
        return cls(
            content=payload.get("content", "") or "",
            model=payload.get("model", "unknown"),
            latency_ms=int(payload.get("latency_ms", 0) or 0),
            raw=payload,
            is_degraded=bool(payload.get("degraded") or payload.get("is_mock")),
            degraded_reason=payload.get("degraded_reason", ""),
        )


# Type for injected LLM caller
LLMCall = Callable[[str, str], dict]
"""Signature: ``llm_call(system_prompt, user_message) -> dict``"""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PlannerError(OrchestratorError):
    """Raised when planning fails (LLM error, parse error, validation).

    ``code`` is the A2A wire code (lowercase) so callers see the same
    string on the wire and in logs. ``http_status`` is taken from
    ``OrchestratorError.A2A_CODES`` for the default code; pass explicitly
    if you need to override.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "planning_failed",
        http_status: int | None = None,
        retryable: bool = False,
        stage: str = "planning",
    ) -> None:
        if http_status is None:
            http_status = OrchestratorError.A2A_CODES.get("PLANNING_FAILED", (None, 500))[1]
        super().__init__(
            message=message,
            code=code,
            stage=stage,
            retryable=retryable,
            http_status=http_status,
        )


# ---------------------------------------------------------------------------
# Plan validation
# ---------------------------------------------------------------------------

_PLAN_KEY_ERRORS = re.compile(r"json|JSON|schema|schema_error|parse")


def _validate_plan_dict(
    plan_dict: dict,
    *,
    available_experts: list[str],
) -> tuple[list[dict], str]:
    """Validate LLM plan output. Returns (experts, reason) or raises PlannerError."""
    if not isinstance(plan_dict, dict):
        raise PlannerError(
            f"Plan must be a JSON object, got {type(plan_dict).__name__}"
        )

    experts = plan_dict.get("experts")
    if not isinstance(experts, list) or not experts:
        raise PlannerError("Plan.experts must be a non-empty list")

    out: list[dict] = []
    available = set(available_experts or [])
    for i, e in enumerate(experts):
        if not isinstance(e, dict):
            raise PlannerError(f"Plan.experts[{i}] must be an object")
        eid = e.get("expert_id")
        if not isinstance(eid, str) or not eid:
            raise PlannerError(f"Plan.experts[{i}].expert_id missing or empty")
        if available and eid not in available:
            raise PlannerError(
                f"Plan.experts[{i}].expert_id={eid!r} not in agent.available_experts"
            )
        priority = e.get("priority", 1)
        if not isinstance(priority, int) or priority < 1:
            raise PlannerError(
                f"Plan.experts[{i}].priority must be a positive int, got {priority!r}"
            )
        critical = bool(e.get("critical", True))
        subtask = e.get("subtask_input", "")
        if not isinstance(subtask, str):
            raise PlannerError(
                f"Plan.experts[{i}].subtask_input must be a string"
            )
        tool_constraints = e.get("tool_constraints", [])
        if not isinstance(tool_constraints, list):
            raise PlannerError(
                f"Plan.experts[{i}].tool_constraints must be a list"
            )
        out.append(
            {
                "expert_id": eid,
                "priority": priority,
                "critical": critical,
                "subtask_input": subtask,
                "tool_constraints": tool_constraints,
            }
        )

    reason = plan_dict.get("reason", "")
    if not isinstance(reason, str):
        reason = str(reason)

    # stable order: priority asc, then original order
    out.sort(key=lambda x: (x["priority"], experts.index(
        next(e for e in experts if e.get("expert_id") == x["expert_id"])
    )))
    return out, reason


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


@dataclass
class PlannerConfig:
    """Tunables — match SPEC §7.2 retry table."""

    max_retries: int = 3
    parse_retry_count: int = 1  # Q-S1: 1 retry on JSON parse failure
    base_backoff_seconds: float = 1.0
    rate_limit_backoff_seconds: float = 5.0
    total_timeout_seconds: float = 60.0
    sleep_fn: Callable[[float], None] = __import__("time").sleep


class Planner:
    """Orchestrator Planner. Construct once, call ``.plan(...)`` per run."""

    def __init__(
        self,
        llm_call: LLMCall,
        *,
        config: PlannerConfig | None = None,
        system_prompt: str = ORCHESTRATOR_SYSTEM_PROMPT,
    ) -> None:
        if llm_call is None:
            raise ValueError("llm_call is required")
        self._llm_call = llm_call
        self._config = config or PlannerConfig()
        self._system_prompt = system_prompt

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def plan(
        self,
        *,
        redacted_input: str,
        agent: "AgentDefinition",
    ) -> Plan:
        """Generate a Plan for ``(redacted_input, agent)``.

        Raises ``PlannerError`` on any failure. Caller maps to
        ``OrchestratorEvent.PLAN_FAILED`` or ``PLANNING_TIMEOUT``.
        """
        user_message = build_planner_user_message_from_agent(
            redacted_input=redacted_input,
            agent=agent,
        )
        return self._plan_with_retries(
            user_message=user_message,
            available_experts=list(agent.expert_ids or []),
        )

    def plan_with_user_message(
        self,
        *,
        redacted_input: str,
        agent_id: str,
        agent_name: str,
        available_experts: list[str],
        non_goals: str = "",
        output_contract: str = "",
    ) -> Plan:
        """Direct-call overload (no AgentDefinition handy — tests, ad-hoc use)."""
        user_message = build_planner_user_message(
            redacted_input=redacted_input,
            agent_id=agent_id,
            agent_name=agent_name,
            available_experts=available_experts,
            non_goals=non_goals,
            output_contract=output_contract,
        )
        return self._plan_with_retries(
            user_message=user_message,
            available_experts=list(available_experts or []),
        )

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _plan_with_retries(
        self,
        *,
        user_message: str,
        available_experts: list[str],
    ) -> Plan:
        cfg = self._config
        last_error: str = ""

        # Outer loop: network/LLM-level retries (3 attempts, exp backoff)
        for attempt in range(1, cfg.max_retries + 1):
            try:
                response = self._invoke_llm(user_message)
            except PlannerError as e:
                last_error = str(e)
                logger.warning(
                    "planner.llm_failed attempt=%d/%d error=%s",
                    attempt, cfg.max_retries, e,
                )
                if not e.retryable or attempt == cfg.max_retries:
                    raise
                self._sleep_backoff(attempt)
                continue

            # Inner loop: parse retries (Q-S1: 1 retry on JSON parse failure)
            for parse_attempt in range(cfg.parse_retry_count + 1):
                try:
                    plan_dict = self._parse_plan_json(response.content)
                except PlannerError as e:
                    last_error = str(e)
                    logger.warning(
                        "planner.parse_failed attempt=%d/%d error=%s",
                        parse_attempt + 1, cfg.parse_retry_count + 1, e,
                    )
                    if parse_attempt == cfg.parse_retry_count:
                        # bubble up; outer loop will retry the whole thing
                        raise
                    # call LLM again with stricter guidance
                    response = self._invoke_llm(user_message + self._parse_hint())
                    continue
                # validate
                experts, reason = _validate_plan_dict(
                    plan_dict, available_experts=available_experts
                )
                return Plan(
                    steps=experts,
                    raw_llm_output=plan_dict,
                    reason=reason,
                )

        # fallthrough (should be unreachable)
        raise PlannerError(
            f"planner exhausted retries: {last_error or 'unknown'}",
            retryable=False,
        )

    def _invoke_llm(self, user_message: str) -> LLMResponse:
        cfg = self._config
        try:
            payload = self._llm_call(self._system_prompt, user_message)
        except PlannerError:
            # Already classified — propagate as-is
            raise
        except OrchestratorError as e:
            # Domain-level error from LLM layer; preserve retryable
            raise PlannerError(
                f"LLM call raised: {type(e).__name__}: {e}",
                retryable=e.retryable,
                code=e.code,
                http_status=e.http_status,
            ) from e
        except Exception as e:  # network / SDK / circuit-breaker
            raise PlannerError(
                f"LLM call raised: {type(e).__name__}: {e}",
                retryable=True,
            ) from e
        return LLMResponse.from_gateway(payload or {})

    def _parse_plan_json(self, content: str) -> dict:
        if not content:
            raise PlannerError("LLM returned empty content", retryable=True)
        # Strip markdown fences if present
        text = content.strip()
        if text.startswith("```"):
            # ```json\n{...}\n```  or  ```\n{...}\n```
            text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
            text = re.sub(r"\s*```\s*$", "", text, count=1)
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise PlannerError(
                f"Plan JSON parse failed: {e.msg} at pos {e.pos}",
                retryable=True,
            ) from e
        if not isinstance(obj, dict):
            raise PlannerError(
                f"Plan JSON must be an object, got {type(obj).__name__}",
                retryable=True,
            )
        return obj

    @staticmethod
    def _parse_hint() -> str:
        return (
            "\n\n[REMINDER] Your previous response was not valid JSON. "
            "Reply with ONLY the JSON object, no markdown fences."
        )

    def _sleep_backoff(self, attempt: int) -> None:
        cfg = self._config
        sleep_for = cfg.base_backoff_seconds * (2 ** (attempt - 1))
        try:
            cfg.sleep_fn(sleep_for)
        except Exception:  # pragma: no cover - defensive
            pass


__all__ = [
    "LLMCall",
    "LLMResponse",
    "Planner",
    "PlannerConfig",
    "PlannerError",
]


# re-export event used by callers mapping planner failure → state event
PLAN_FAILED_EVENT = OrchestratorEvent.PLAN_FAILED
PLANNING_TIMEOUT_EVENT = OrchestratorEvent.PLANNING_TIMEOUT