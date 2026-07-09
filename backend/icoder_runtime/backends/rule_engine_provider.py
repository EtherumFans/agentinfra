"""RuleEngineProvider — the first concrete ``AgentBackendProvider``.

Phase 4-A Task 4 (2026-07-07): wraps iCoDer's existing rule-based
capabilities into the unified provider interface so
``AgentRunner`` / ``InboundHandler`` can route through it without
``if backend_type == 'rule_engine'`` branches.

What this provider wraps (no business-logic duplication — per Task 4
requirement #2: "复用现有 RuleEngine / MedicalCodingRuleSet / CG
heuristics / regex logic"):

  - ``icoder_runtime.providers.medical_coding.rule_engine_adapter.RuleEngineAdapter``
    (R001-R012 ICD-10/ICD-9-CM-3 format + duplicate + consistency
    checks against ``MedicalCodingOutputSchema``)
  - ``app.services.rule_engine.RuleEngineService`` (15-rule coding
    knowledge base + fuzzy retrieval — used for the
    ``compliance-guardrail`` and ``code-validation`` legacy simple-agent
    path, which currently routes via ``evaluate_compliance`` MCP tool)
  - The CG heuristics (CG-001 main-diag-not-empty / CG-002 no-upcoding
    / CG-003 proc-diag consistency / CG-004 DRG readiness) live inside
    the ``evaluate_compliance`` MCP handler — this provider does NOT
    reimplement them; it normalizes the handler's verdict into a
    ``BackendResponse``.

Provider metadata (per Task 4 spec):
  - ``provider_id = "icoder.rule-engine.v1"``
  - ``backend_type = "rule_engine"``
  - ``deterministic = True``
  - ``supports_tool_calling = False``
  - ``supports_streaming = False``

The provider is wired lazily — ``RuleEngineProvider()`` does not
construct any heavy state on init; the underlying
``RuleEngineAdapter`` and ``RuleEngineService`` are imported on first
``invoke()`` so that simply registering the provider at startup
remains cheap (Task 2 requirement #5).
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator

from .contracts import (
    AgentBackendProvider,
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    BackendType,
    OutputContract,
    OutputIssue,
    ProviderCapability,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class RuleEngineProvider:
    """Wraps iCoDer rule-based capabilities behind ``AgentBackendProvider``.

    The provider exposes ONE entry point (``invoke``) that accepts a
    ``BackendRequest`` whose ``input`` carries either:

      - ``coding_output`` (a ``MedicalCodingOutputSchema``-shaped dict)
        for direct R001-R012 validation, OR
      - ``coding_set`` (a dict of {primary, secondary, procedures}) for
        compliance-guardrail / code-validation legacy paths, OR
      - ``topic`` (a string) for ``RuleEngineService.retrieve_rules``
        (knowledge-base lookup)

    Regardless of input shape, the response is normalized to a
    ``BackendResponse`` with ``status ∈ {pass, warning, fail}`` and
    ``issues[]`` populated from triggered rules.
    """

    provider_id: str = "icoder.rule-engine.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling: bool = False
    supports_streaming: bool = False
    deterministic: bool = True

    # Schema this provider emits (used by ``OutputContract`` validation).
    _OUTPUT_CONTRACT_REF: str = "icoder/RuleEngineOutput/v1"

    def __init__(self) -> None:
        # Lazy — don't import the adapter / service until first invoke.
        # This keeps startup cheap (Task 2 requirement #5).
        self._adapter: Any = None
        self._service: Any = None

    # ── AgentBackendProvider protocol ─────────────────────────────

    async def health(self) -> ProviderHealth:
        """Cheap liveness probe — just check that we can lazy-init."""
        try:
            self._ensure_adapter()
            return ProviderHealth(
                state="ok",
                latency_ms=0,
                details={"provider_id": self.provider_id,
                         "backend_type": self.backend_type},
            )
        except Exception as e:
            return ProviderHealth(
                state="down",
                details={"error": f"{type(e).__name__}: {str(e)[:200]}"},
            )

    async def invoke(
        self, req: BackendRequest, ctx: AgentRunContext,
    ) -> BackendResponse:
        """Run rule-based validation against ``req.input``.

        Three input shapes are accepted (per the docstring above). The
        provider normalizes all three into a single
        ``BackendResponse`` with ``status`` / ``summary`` / ``issues`` /
        ``raw_provider_response`` populated.
        """
        t0 = time.perf_counter()
        self._ensure_adapter()
        backend_req_id = self._stamp_backend(req, ctx)

        input_data = req.input or {}
        try:
            if "coding_output" in input_data or "primary_diagnosis" in input_data:
                verdict = self._validate_coding_output(input_data)
            elif "coding_set" in input_data:
                verdict = self._validate_coding_set(input_data["coding_set"])
            elif "topic" in input_data:
                rules = await self._retrieve_rules(str(input_data["topic"]))
                verdict = self._format_kb_lookup(rules, str(input_data["topic"]))
            else:
                # Empty / unknown input → fail-soft with a warning.
                verdict = {
                    "status": "warning",
                    "summary": "RuleEngineProvider: empty or unrecognized input.",
                    "issues": [],
                    "raw": {"input_keys": list(input_data.keys())},
                }
        except Exception as e:
            # Defensive — never leak a stack trace; produce a fail envelope.
            logger.exception("RuleEngineProvider.invoke failed")
            return BackendResponse(
                status="fail",
                summary=f"rule engine invoke raised: {type(e).__name__}: {e}",
                finish_state="failed",
                finish_reason=f"{type(e).__name__}: {str(e)[:200]}",
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        issues = [OutputIssue(**i) for i in verdict.get("issues", []) if isinstance(i, dict)]
        resp = BackendResponse(
            status=verdict.get("status", "warning"),  # type: ignore[arg-type]
            summary=verdict.get("summary", ""),
            issues=issues,
            latency_ms=latency_ms,
            cost_usd=0.0,
            finish_state="completed",
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            raw_provider_response=verdict.get("raw", {}),
            markdown=verdict.get("summary", ""),
            evidence_refs=[i.code for i in issues],
            trace_refs=[backend_req_id],
        )
        return resp

    async def stream(
        self, req: BackendRequest, ctx: AgentRunContext,
    ) -> AsyncIterator[Any]:
        """Rule engine is non-streaming — emit a single finish event.

        Yields one dict ``{"step": "backend_invoked", "payload": BackendResponse}``
        so callers that always use ``stream()`` still get a uniform
        contract (per architecture Item 9: "provider.stream() works
        for all 8 provider types").
        """
        resp = await self.invoke(req, ctx)
        yield {"step": "backend_invoked", "payload": resp}
        yield {"step": "finished", "payload": {"state": resp.finish_state}}

    def output_contract(self) -> str:
        return self._OUTPUT_CONTRACT_REF

    def fallback_chain(self) -> list[AgentBackendProvider] | None:
        return None

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=self.provider_id,
            backend_type=self.backend_type,
            supports_tool_calling=self.supports_tool_calling,
            supports_streaming=self.supports_streaming,
            deterministic=self.deterministic,
            default_output_contract=self._OUTPUT_CONTRACT_REF,
            supported_tools=[],
            description=(
                "Deterministic rule-based provider. Wraps RuleEngineAdapter "
                "(R001-R012 ICD-10/ICD-9-CM-3 checks) and RuleEngineService "
                "(15-rule knowledge-base lookup)."
            ),
        )

    # ── Internal: lazy init + input-shape dispatch ───────────────

    def _ensure_adapter(self) -> None:
        if self._adapter is not None:
            return
        # Local imports — avoid paying for medical_coding schema import
        # at module load time.
        try:
            from icoder_runtime.providers.medical_coding.rule_engine_adapter import (
                RuleEngineAdapter,
            )
            self._adapter = RuleEngineAdapter()
        except Exception as e:
            logger.error("RuleEngineAdapter import failed: %s", e)
            self._adapter = _FallbackRuleEngineAdapter()
        try:
            from app.services.rule_engine import rule_engine_service
            self._service = rule_engine_service
        except Exception as e:
            logger.debug("RuleEngineService import skipped: %s", e)
            self._service = None

    def _stamp_backend(self, req: BackendRequest, ctx: AgentRunContext) -> str:
        """Populate backend_provider / backend_type on the request context.

        Returns a backend_req_id (used as trace_ref).
        """
        return f"{ctx.run_id}:rule-engine:{int(time.time() * 1000)}"

    def _validate_coding_output(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Run R001-R012 against a ``MedicalCodingOutputSchema``-shaped dict."""
        from official_agents.medical_coding.schema import (
            MedicalCodingOutputSchema,
        )
        coding_output_dict = input_data.get("coding_output") or input_data
        if not isinstance(coding_output_dict, dict):
            return {
                "status": "fail",
                "summary": "RuleEngineProvider: coding_output must be a dict.",
                "issues": [],
                "raw": {"input_type": str(type(coding_output_dict).__name__)},
            }
        try:
            schema = MedicalCodingOutputSchema.from_dict(coding_output_dict)
        except Exception as e:
            return {
                "status": "fail",
                "summary": f"coding_output parse failed: {type(e).__name__}: {e}",
                "issues": [],
                "raw": {"parse_error": str(e)[:300]},
            }
        if self._adapter is None:
            return {
                "status": "fail",
                "summary": "RuleEngineAdapter not initialized.",
                "issues": [],
                "raw": {},
            }
        result = self._adapter.validate(schema)  # RuleValidationResult
        # CodingIssue.severity ∈ {critical, high, medium, low, info}
        # OutputIssue.severity ∈ {info, warning, error, critical}
        severity_map = {
            "critical": "critical",
            "high": "error",
            "medium": "warning",
            "low": "info",
            "info": "info",
        }
        issues_payload = []
        for issue in result.issues:
            raw_sev = (issue.severity or "info").lower()
            issues_payload.append({
                "code": issue.code or "R???",
                "severity": severity_map.get(raw_sev, "warning"),
                "message": issue.message,
                "evidence": [issue.suggestion] if issue.suggestion else [],
                "recommended_action": issue.suggestion or None,
            })
        status: ProviderStatus = "pass" if result.passed else (
            "warning" if not any(i["severity"] == "critical" for i in issues_payload)
            else "fail"
        )
        return {
            "status": status,
            "summary": (
                f"Rule engine: {len(result.rules_fired)} rules evaluated, "
                f"{len(issues_payload)} issues found."
            ),
            "issues": issues_payload,
            "raw": {
                "fired_rules": list(result.rules_fired),
                "quality_flags": result.quality_flags,
                "passed": result.passed,
            },
        }

    def _validate_coding_set(self, coding_set: dict[str, Any]) -> dict[str, Any]:
        """Run R001-R012 against a ``coding_set`` (compliance-guardrail shape).

        ``coding_set`` is the legacy compliance-guardrail input —
        ``{primary_diagnosis: {code, ...}, secondary_diagnoses: [...],
        procedures: [...]}``. We project it to
        ``MedicalCodingOutputSchema`` shape and reuse
        ``_validate_coding_output``.
        """
        if not isinstance(coding_set, dict):
            return {
                "status": "fail",
                "summary": "coding_set must be a dict.",
                "issues": [],
                "raw": {},
            }
        primary = coding_set.get("primary_diagnosis") or {}
        if isinstance(primary, dict):
            primary_dict = primary
        elif hasattr(primary, "model_dump"):
            primary_dict = primary.model_dump()
        else:
            primary_dict = {"code": str(primary)}

        secondary_raw = coding_set.get("secondary_diagnoses") or []
        secondary_list: list[dict[str, Any]] = []
        for s in secondary_raw:
            if isinstance(s, dict):
                secondary_list.append(s)
            elif hasattr(s, "model_dump"):
                secondary_list.append(s.model_dump())

        procedures_raw = coding_set.get("procedures") or []
        proc_list: list[dict[str, Any]] = []
        for p in procedures_raw:
            if isinstance(p, dict):
                proc_list.append(p)
            elif hasattr(p, "model_dump"):
                proc_list.append(p.model_dump())

        coding_output = {
            "primary_diagnosis": primary_dict,
            "secondary_diagnoses": secondary_list,
            "procedures": proc_list,
        }
        return self._validate_coding_output({"coding_output": coding_output})

    async def _retrieve_rules(self, topic: str) -> list[dict[str, Any]]:
        """Use ``RuleEngineService.retrieve_rules`` for KB lookup."""
        if self._service is None:
            return []
        try:
            return await self._service.retrieve_rules(topic, top_k=5)
        except Exception as e:
            logger.warning("retrieve_rules failed: %s", e)
            return []

    def _format_kb_lookup(self, rules: list[dict[str, Any]], topic: str) -> dict[str, Any]:
        if not rules:
            return {
                "status": "warning",
                "summary": f"No rules matched topic {topic!r}.",
                "issues": [],
                "raw": {"topic": topic, "rule_count": 0},
            }
        issues_payload = [
            {
                "code": r.get("rule_id", "KB?"),
                "severity": "info",
                "message": r.get("title", ""),
                "evidence": [r.get("content", "")[:200]] if r.get("content") else [],
                "recommended_action": r.get("examples"),
            }
            for r in rules
        ]
        return {
            "status": "pass",
            "summary": f"Retrieved {len(rules)} rules for topic {topic!r}.",
            "issues": issues_payload,
            "raw": {"topic": topic, "rules": rules},
        }


class _FallbackRuleEngineAdapter:
    """Used if the real ``RuleEngineAdapter`` import fails.

    Only basic R001-style checks (primary diagnosis non-empty) so
    the provider can still produce a meaningful verdict instead of
    crashing. Production should never hit this — it's defensive.
    """

    def validate(self, coding_output: Any) -> Any:
        from dataclasses import dataclass, field
        from official_agents.medical_coding.schema import CodingIssue

        @dataclass
        class _Result:
            passed: bool = True
            rules_fired: list[str] = field(default_factory=list)
            issues: list[Any] = field(default_factory=list)
            quality_flags: dict[str, bool] = field(default_factory=dict)

        primary = getattr(coding_output, "primary_diagnosis", None)
        primary_code = getattr(primary, "code", "") if primary else ""
        rules_fired = ["R001"]
        issues: list[Any] = []
        if not primary_code:
            issues.append(CodingIssue(
                severity="critical", code="R001",
                message="主要诊断编码不能为空",
                suggestion="请为病历指定主要诊断 ICD-10 编码",
            ))
        return _Result(
            passed=bool(primary_code),
            rules_fired=rules_fired,
            issues=issues,
            quality_flags={"primary_diagnosis_missing": not bool(primary_code)},
        )


__all__ = ["RuleEngineProvider"]
