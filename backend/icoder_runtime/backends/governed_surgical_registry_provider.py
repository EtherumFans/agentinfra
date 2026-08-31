"""Governed local extraction baseline for surgical quality registration.

The provider deliberately implements a conservative lexical baseline.  It
copies only explicitly labelled or tightly bounded facts from the redacted
source text, records an exact source quote for every populated field, leaves
unknown fields empty, and always requires a registrar review.  It does not
infer clinical facts or write to a registry.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, AsyncIterator, Iterable

from .contracts import (
    AgentBackendProvider,
    AgentRunContext,
    BackendRequest,
    BackendResponse,
    BackendType,
    ProviderCapability,
    ProviderHealth,
    ProviderStatus,
)


logger = logging.getLogger(__name__)

_REGISTRY_FIELDS = (
    "procedure",
    "indications",
    "comorbidities",
    "operative_details",
    "anesthesia",
    "outcomes",
    "complications",
)
_BOUNDARY = r"[^，,。；;\r\n]"


def _first_group(
    text: str,
    patterns: Iterable[str],
    *,
    group: str = "value",
) -> tuple[str, str]:
    """Return a bounded value and the exact full-match source quote."""

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is None:
            continue
        value = str(match.group(group)).strip(" \t:：，,。；;")
        evidence = match.group(0).strip(" \t，,。；;")
        if value and evidence and evidence in text:
            return value, evidence
    return "", ""


def _extract_anesthesia(text: str) -> tuple[str, str]:
    patterns = (
        (r"静吸复合全麻(?:下)?", "静吸复合全麻"),
        (r"全身麻醉(?:下)?", "全身麻醉"),
        (r"全麻(?:下)?", "全麻"),
        (r"椎管内麻醉(?:下)?", "椎管内麻醉"),
        (r"硬膜外麻醉(?:下)?", "硬膜外麻醉"),
        (r"腰麻(?:下)?", "腰麻"),
        (r"局部麻醉(?:下)?", "局部麻醉"),
        (r"局麻(?:下)?", "局麻"),
        (r"神经阻滞麻醉(?:下)?", "神经阻滞麻醉"),
        (r"静脉麻醉(?:下)?", "静脉麻醉"),
    )
    for pattern, canonical in patterns:
        match = re.search(pattern, text)
        if match is not None:
            return canonical, match.group(0)
    return "", ""


def _extract_procedure(text: str) -> tuple[str, str]:
    labelled = _first_group(
        text,
        (
            rf"(?:手术名称|术式)\s*[:：]\s*(?P<value>{_BOUNDARY}{{2,80}})",
        ),
    )
    if labelled[0]:
        return labelled

    # ``行/施行/完成 + ...术`` is intentionally narrower than a generic
    # procedure recognizer.  The action word is retained as exact evidence,
    # while the public value contains only the explicitly written procedure.
    match = re.search(
        rf"(?:施行|完成|行)(?P<value>{_BOUNDARY}{{2,64}}?(?:手术|术))",
        text,
    )
    if match is None:
        return "", ""
    value = match.group("value").strip()
    evidence = match.group(0).strip()
    return (value, evidence) if value and evidence in text else ("", "")


def _extract_complications(text: str) -> tuple[str, str]:
    labelled = _first_group(
        text,
        (
            rf"(?:术中并发症|并发症)\s*[:：]\s*(?P<value>{_BOUNDARY}{{1,96}})",
        ),
    )
    if labelled[0]:
        return labelled

    # Explicit negative findings are registry facts, not missing data.  Keep
    # the pattern bounded to common complication nouns to avoid treating an
    # arbitrary ``无...`` sentence as a clinical conclusion.
    match = re.search(
        rf"(?P<value>(?:未见|未发生|无){_BOUNDARY}{{0,40}}?"
        r"(?:损伤|并发症|感染|栓塞|瘘|死亡))",
        text,
    )
    if match is None:
        return "", ""
    value = match.group("value").strip()
    return (value, value) if value and value in text else ("", "")


def extract_surgical_registry(text: str) -> dict[str, Any]:
    """Extract conservative registry fields from already-redacted text."""

    source = str(text or "")[:20_000]
    values = {field: "" for field in _REGISTRY_FIELDS}
    evidence: dict[str, str] = {}

    value, quote = _extract_procedure(source)
    if value:
        values["procedure"] = value
        evidence["procedure"] = quote

    value, quote = _first_group(
        source,
        (rf"(?:手术指征|适应证)\s*[:：]\s*(?P<value>{_BOUNDARY}{{1,256}})",),
    )
    if value:
        values["indications"] = value
        evidence["indications"] = quote

    value, quote = _first_group(
        source,
        (rf"(?:合并症|合并疾病)\s*[:：]\s*(?P<value>{_BOUNDARY}{{1,256}})",),
    )
    if value:
        values["comorbidities"] = value
        evidence["comorbidities"] = quote

    value, quote = _first_group(
        source,
        (rf"(?P<value>术中{_BOUNDARY}{{1,512}})",),
    )
    if value:
        values["operative_details"] = value
        evidence["operative_details"] = quote

    value, quote = _extract_anesthesia(source)
    if value:
        values["anesthesia"] = value
        evidence["anesthesia"] = quote

    value, quote = _first_group(
        source,
        (rf"(?:术后转归|转归|术后情况)\s*[:：]\s*(?P<value>{_BOUNDARY}{{1,256}})",),
    )
    if value:
        values["outcomes"] = value
        evidence["outcomes"] = quote

    value, quote = _extract_complications(source)
    if value:
        values["complications"] = value
        evidence["complications"] = quote

    missing = [field for field in _REGISTRY_FIELDS if not values[field]]
    return {
        **values,
        "evidence_spans": evidence,
        "missing_fields": missing,
        "manual_review_required": True,
    }


class GovernedSurgicalRegistryProvider:
    provider_id = "icoder.governed-surgical-registry.v1"
    backend_type: BackendType = "rule_engine"
    supports_tool_calling = False
    supports_streaming = False
    deterministic = True
    _OUTPUT_CONTRACT_REF = "icoder/SurgicalRegistryOutput/v4"

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            state="ok",
            latency_ms=0,
            details={
                "provider_id": self.provider_id,
                "backend_type": self.backend_type,
                "policy_id": "cn.surgical-registry.explicit-source-facts",
                "policy_version": "1.0.0",
                "network_required": False,
                "llm_required": False,
                "production_writeback_blocked": True,
            },
        )

    async def invoke(
        self,
        req: BackendRequest,
        ctx: AgentRunContext,
        *,
        request: Any = None,
    ) -> BackendResponse:
        del request
        started = time.perf_counter()
        input_data = dict(req.input or {})
        text = str(input_data.get("text") or req.user_input or ctx.redacted_input or "")
        public = extract_surgical_registry(text)
        populated = [field for field in _REGISTRY_FIELDS if public[field]]
        input_required = not bool(text.strip())
        status: ProviderStatus = "incomplete" if input_required else "requires_review"
        latency_ms = int((time.perf_counter() - started) * 1000)
        self._emit_backend_metadata(
            ctx,
            latency_ms=latency_ms,
            status=status,
            evidence_items_count=len(populated),
        )
        return BackendResponse(
            status=status,
            summary=(
                "请提供已脱敏的手术、麻醉或出院记录。"
                if input_required
                else f"已从原文定位 {len(populated)} 个登记字段，提交前须登记员复核。"
            ),
            latency_ms=latency_ms,
            cost_usd=0.0,
            finish_state="input-required" if input_required else "completed",
            finish_reason="surgical_record_required" if input_required else None,
            backend_provider=self.provider_id,
            backend_type=self.backend_type,
            fallback_used=False,
            raw_provider_response=dict(public),
            markdown=json.dumps(public, ensure_ascii=False, sort_keys=True),
            evidence_refs=[],
            trace_refs=[f"{ctx.run_id}:governed-surgical-registry"],
        )

    async def stream(
        self,
        req: BackendRequest,
        ctx: AgentRunContext,
    ) -> AsyncIterator[Any]:
        response = await self.invoke(req, ctx)
        yield {"step": "backend_invoked", "payload": response}
        yield {"step": "finished", "payload": {"state": response.finish_state}}

    def output_contract(self) -> str:
        return self._OUTPUT_CONTRACT_REF

    def fallback_chain(self) -> list[AgentBackendProvider] | None:
        return None

    def capabilities(self) -> ProviderCapability:
        return ProviderCapability(
            provider_id=self.provider_id,
            backend_type=self.backend_type,
            supports_tool_calling=False,
            supports_streaming=False,
            deterministic=True,
            default_output_contract=self._OUTPUT_CONTRACT_REF,
            supported_tools=[],
            description=(
                "Extracts only explicit surgical-registry facts and exact source "
                "quotes; unknown fields remain empty and always require review."
            ),
        )

    def _emit_backend_metadata(
        self,
        ctx: AgentRunContext,
        *,
        latency_ms: int,
        status: ProviderStatus,
        evidence_items_count: int,
    ) -> None:
        try:
            from app.icoder.agent_runtime.orchestrator.run_trace import (
                emit_backend_metadata_event,
                get_default_store,
            )

            output_contract = str(
                (ctx.agent_pack.get("output_contract") or {}).get("schema_ref")
                or self.output_contract()
            )
            emit_backend_metadata_event(
                ctx.run_id,
                backend_provider=self.provider_id,
                backend_type=self.backend_type,
                provider_latency_ms=latency_ms,
                provider_status=status,
                provider_deterministic=True,
                supports_tool_calling=False,
                fallback_used=False,
                output_contract=output_contract,
                tool_rounds=0,
                model_cost_usd=0.0,
                llm_call_count=0,
                evidence_items_count=evidence_items_count,
                store=get_default_store(),
            )
        except Exception as exc:
            logger.warning(
                "GovernedSurgicalRegistryProvider trace emit failed error_type=%s",
                type(exc).__name__,
            )


__all__ = [
    "GovernedSurgicalRegistryProvider",
    "extract_surgical_registry",
]
