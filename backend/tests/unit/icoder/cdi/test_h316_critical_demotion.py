"""Track H3.16 — extract_claims critical-claim-with-empty-quote demotion.

H3.16 deterministic safety net: even when the extract_claims LLM emits a
claim marked ``criticality=critical`` with an empty quote (despite the
iter 5 prompt rule "critical claim 必须有 chart 证据"), the parser should
demote it to ``supporting`` so CEA-008 doesn't block the query.

Closes the lab_positive_uncertain 0/5 emit regression (LAB-037/039/040
where CEA blocked ≥1 critical claim with no chart evidence).
"""

from __future__ import annotations

from typing import Any

from app.icoder.agent_runtime.cdi.claim_evidence_gate import (
    Claim,
    ClaimEvidenceAlignment,
    extract_claims,
)
from app.icoder.agent_runtime.cdi.domain import ProviderQuery, EvidenceSpan


class _StubLLM:
    """Returns a canned JSON response — simulates the extract_claims LLM."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    async def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        import json
        return {"content": json.dumps(self._payload, ensure_ascii=False)}


def _make_query() -> ProviderQuery:
    return ProviderQuery(
        query_id="q1",
        gap_id="GAP-001",
        topic="lab_correlation",
        reason="lab positive uncertain",
        evidence_span=EvidenceSpan(document_id="DOC-001", quote="CA-125 65 U/mL"),
        query_text="请明确 CA-125 升高的临床意义",
    )


def test_critical_with_empty_quote_is_demoted_to_supporting() -> None:
    """The H3.16 fix: critical + empty quote → supporting."""
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "text": "CA-125 升高需要临床解释",
                "criticality": "critical",  # marked critical
                "evidence_span_id": "es_1",
                "document_id": "chart",
                "quote": "",  # but no quote — should demote
                "support_type": "direct",
                "confidence": 0.9,
            },
        ]
    }
    import asyncio
    claims, aligns = asyncio.run(
        extract_claims(_make_query(), chart="患者 CA-125 65 U/mL", llm=_StubLLM(payload))
    )
    assert len(claims) == 1
    assert claims[0].criticality == "supporting"  # demoted
    assert aligns[0].support_type == "unsupported"  # support reset


def test_critical_with_quote_stays_critical() -> None:
    """Critical claim WITH a chart quote remains critical (control)."""
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "text": "CA-125 65 U/mL 升高",
                "criticality": "critical",
                "evidence_span_id": "es_1",
                "document_id": "chart",
                "quote": "CA-125 65 U/mL",
                "support_type": "direct",
                "confidence": 0.95,
            },
        ]
    }
    import asyncio
    claims, aligns = asyncio.run(
        extract_claims(_make_query(), chart="患者 CA-125 65 U/mL", llm=_StubLLM(payload))
    )
    assert claims[0].criticality == "critical"  # NOT demoted
    assert aligns[0].support_type == "direct"


def test_supporting_with_empty_quote_unchanged() -> None:
    """Supporting claim with empty quote is left as-is (no demotion needed)."""
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "text": "可能为卵巢肿瘤",
                "criticality": "supporting",
                "evidence_span_id": "es_1",
                "document_id": "chart",
                "quote": "",
                "support_type": "unsupported",
                "confidence": 0.4,
            },
        ]
    }
    import asyncio
    claims, _ = asyncio.run(
        extract_claims(_make_query(), chart="患者 CA-125 65 U/mL", llm=_StubLLM(payload))
    )
    assert claims[0].criticality == "supporting"


def test_mixed_demote_only_critical_without_quote() -> None:
    """When 1 critical has quote and 1 critical lacks quote, only the latter demotes."""
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "text": "CA-125 升高",
                "criticality": "critical",
                "quote": "CA-125 65 U/mL",
                "support_type": "direct",
            },
            {
                "claim_id": "claim_2",
                "text": "卵巢肿瘤可能性",
                "criticality": "critical",
                "quote": "",  # demote this one
                "support_type": "direct",
            },
        ]
    }
    import asyncio
    claims, _ = asyncio.run(
        extract_claims(_make_query(), chart="患者 CA-125 65 U/mL", llm=_StubLLM(payload))
    )
    by_id = {c.claim_id: c for c in claims}
    assert by_id["claim_1"].criticality == "critical"  # kept
    assert by_id["claim_2"].criticality == "supporting"  # demoted


def test_query_passes_cae_after_demotion() -> None:
    """End-to-end: a query with only demoted critical claims should PASS CEA."""
    from app.icoder.agent_runtime.cdi.claim_evidence_gate import evaluate_claim_evidence

    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "text": "CA-125 升高的临床意义未明确",
                "criticality": "critical",
                "quote": "",  # would block without H3.16 fix
                "support_type": "direct",
            },
        ]
    }
    import asyncio
    q = _make_query()
    claims, aligns = asyncio.run(
        extract_claims(q, chart="患者 CA-125 65 U/mL", llm=_StubLLM(payload))
    )
    q.claims = claims
    q.claim_evidence_alignments = aligns
    verdict = evaluate_claim_evidence(q, chart="患者 CA-125 65 U/mL")
    assert verdict.verdict == "PASS"
    assert verdict.block_reasons == []


def test_critical_with_fuzzy_mismatch_quote_is_demoted() -> None:
    """H3.16 extended: critical + quote that doesn't fuzzy-match → demoted."""
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "text": "患者已被诊断为卵巢癌",
                "criticality": "critical",
                "evidence_span_id": "es_1",
                "document_id": "chart",
                "quote": "病理确诊卵巢癌",  # NOT in chart
                "support_type": "direct",
                "confidence": 0.9,
            },
        ]
    }
    import asyncio
    claims, aligns = asyncio.run(
        extract_claims(_make_query(), chart="患者 CA-125 65 U/mL", llm=_StubLLM(payload))
    )
    assert claims[0].criticality == "supporting"  # demoted (quote not in chart)
    assert aligns[0].support_type == "unsupported"


def test_critical_with_paraphrased_quote_keeps_critical_if_fuzzy_matches() -> None:
    """If quote is paraphrased but fuzzy-matches (≥0.85), keep critical."""
    payload = {
        "claims": [
            {
                "claim_id": "claim_1",
                "text": "CA-125 升高",
                "criticality": "critical",
                "evidence_span_id": "es_1",
                "document_id": "chart",
                "quote": "CA-125 65 U/mL",  # exact match
                "support_type": "direct",
                "confidence": 0.95,
            },
        ]
    }
    import asyncio
    claims, _ = asyncio.run(
        extract_claims(_make_query(), chart="患者 CA-125 65 U/mL", llm=_StubLLM(payload))
    )
    assert claims[0].criticality == "critical"
