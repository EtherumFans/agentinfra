"""MedCodERRetrievalRuleSet — validates the Stage 2 retrieval output.

Checks applied to the per-diagnosis retrieved code list:
  MR-001: every CandidateCode.code must exist in the ICD-10-CN catalog
  MR-002: at least one retrieved code must have score >= 0.5 (high-similarity
          hit; below this threshold the BGE-M3 + FAISS match is too weak to
          trust)
  MR-003: the top-1 retrieved code's chapter should not be empty
          (catalog metadata must be present)

These are **advisory** — MedCodER is a suggestion pipeline, the human
reviewer is the final authority. The rule set flags a manual-review
required state if MR-001 fires (unknown code suggests catalog drift).
"""
from __future__ import annotations

import logging
from typing import Any

from .rule_engine import BaseRuleSet, RuleIssue, RuleValidationResult

logger = logging.getLogger(__name__)

# Similarity threshold below which a BGE-M3 hit is considered weak.
HIGH_SIMILARITY_THRESHOLD = 0.5


class MedCodERRetrievalRuleSet(BaseRuleSet):
    """Stage 2 retrieval validation (catalog compliance + score sanity)."""

    name = "medcoder_retrieval"
    rules: dict[str, dict] = {
        "MR-001": {
            "description": "All retrieved codes must be in the ICD-10-CN catalog",
            "severity": "high",
        },
        "MR-002": {
            "description": "At least one retrieved code must have score >= 0.5",
            "severity": "medium",
        },
        "MR-003": {
            "description": "Top-1 retrieved code must have non-empty chapter",
            "severity": "low",
        },
    }

    def validate(self, structured_output: dict, context: dict) -> RuleValidationResult:
        result = RuleValidationResult(
            passed=True,
            rule_set=self.name,
            total_rules=len(self.rules),
        )

        # Only operate on medcoder-mode outputs
        if structured_output.get("mode") != "medcoder":
            return result  # No-op for legacy modes

        extracted = structured_output.get("extracted_diagnoses") or []
        if not extracted:
            # MedCodER mode with no extractions is itself a flag
            result.issues.append(RuleIssue(
                severity="high",
                rule_id="MR-000",
                message="MedCodER pipeline produced no extracted_diagnoses",
                suggestion="Check LLM Stage-1 prompt; verify model is responding",
                category="consistency",
            ))
            result.passed = False
            return result

        # Pull catalog hasher from context (default: use the loader if present)
        catalog_has = context.get("catalog_has")

        for dx_idx, dx in enumerate(extracted):
            retrieved = dx.get("retrieved_codes") or []
            tag = f"diagnosis[{dx_idx}]({dx.get('disease_text', '?')[:20]})"

            # MR-001: all codes in catalog
            unknown: list[str] = []
            for c in retrieved:
                code = c.get("code", "")
                if not code:
                    continue
                if catalog_has is not None and not catalog_has(code):
                    unknown.append(code)
            if unknown:
                result.rules_fired.append("MR-001")
                result.issues.append(RuleIssue(
                    severity="high",
                    rule_id="MR-001",
                    message=f"{tag}: {len(unknown)} code(s) not in catalog: {unknown[:3]}",
                    suggestion="Refresh FAISS index from current catalog; investigate drift",
                    category="coding",
                ))
                result.passed = False

            # MR-002: at least one high-similarity hit
            high_sim = [c for c in retrieved
                        if float(c.get("score", 0.0)) >= HIGH_SIMILARITY_THRESHOLD]
            if retrieved and not high_sim:
                result.rules_fired.append("MR-002")
                result.issues.append(RuleIssue(
                    severity="medium",
                    rule_id="MR-002",
                    message=f"{tag}: no retrieved code reached score {HIGH_SIMILARITY_THRESHOLD} "
                            f"(max={max((float(c.get('score', 0.0)) for c in retrieved), default=0.0):.3f})",
                    suggestion="Consider synonym expansion, multi-vector query, or a fallback LLM pass",
                    category="quality",
                ))
                result.manual_review_required = True

            # MR-003: top-1 chapter must be non-empty
            if retrieved:
                top = retrieved[0]
                if not (top.get("chapter") or "").strip():
                    result.rules_fired.append("MR-003")
                    result.issues.append(RuleIssue(
                        severity="low",
                        rule_id="MR-003",
                        message=f"{tag}: top-1 code {top.get('code', '?')} has empty chapter metadata",
                        suggestion="Rebuild metadata.pkl from current catalog",
                        category="quality",
                    ))

        return result


# ── Optional: convenience registration helper ──


def register_with(engine) -> None:
    """Register this rule set with the given RuleEngine instance."""
    engine.register(MedCodERRetrievalRuleSet())
    # Add to engine's known set (the SUPPORTED_RULE_SETS is a frozenset-like
    # in some implementations, so guard with getattr).
    supported = getattr(engine, "SUPPORTED_RULE_SETS", None)
    if supported is not None and isinstance(supported, set):
        supported.add("medcoder_retrieval")
