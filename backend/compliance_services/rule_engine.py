"""RuleEngine — domain-independent compliance rule validation framework.

Supports multiple rule_sets. Each rule_set defines its own rules.
Agents invoke the RuleEngine by specifying a rule_set name.

Usage:
    engine = RuleEngine()
    result = engine.validate("medical_coding", structured_output, context)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RuleIssue:
    severity: str = "info"  # critical | high | medium | low | info
    rule_id: str = ""
    message: str = ""
    suggestion: str = ""
    category: str = ""  # coding | quality | consistency | safety

    def to_dict(self) -> dict:
        return {
            "severity": self.severity, "rule_id": self.rule_id,
            "message": self.message, "suggestion": self.suggestion,
            "category": self.category,
        }


@dataclass
class RuleValidationResult:
    passed: bool = True
    rule_set: str = ""
    total_rules: int = 0
    rules_fired: list[str] = field(default_factory=list)
    issues: list[RuleIssue] = field(default_factory=list)
    quality_flags: dict[str, bool] = field(default_factory=dict)
    manual_review_required: bool = False

    def to_dict(self) -> dict:
        return {
            "passed": self.passed, "rule_set": self.rule_set,
            "total_rules": self.total_rules, "rules_fired": self.rules_fired,
            "issues": [i.to_dict() for i in self.issues],
            "quality_flags": self.quality_flags,
            "manual_review_required": self.manual_review_required,
        }


class BaseRuleSet:
    """Abstract rule set. Subclass for each compliance domain."""

    name: str = "base"
    rules: dict[str, dict] = {}

    def validate(self, structured_output: dict, context: dict) -> RuleValidationResult:
        raise NotImplementedError


class RuleEngine:
    """Domain-independent rule engine. Validates structured output against a named rule_set."""

    SUPPORTED_RULE_SETS = {
        "medical_coding", "drg_dip", "insurance_audit",
        "charge_compliance", "document_evidence",
    }

    def __init__(self):
        self._rule_sets: dict[str, BaseRuleSet] = {}

    def register(self, rule_set: BaseRuleSet):
        self._rule_sets[rule_set.name] = rule_set

    def validate(
        self,
        rule_set: str,
        structured_output: dict,
        context: dict | None = None,
    ) -> RuleValidationResult:
        """Validate structured output against the named rule_set."""
        ctx = context or {}

        if rule_set not in self._rule_sets:
            return RuleValidationResult(
                passed=False, rule_set=rule_set,
                issues=[RuleIssue(severity="critical", rule_id="ENGINE_001",
                         message=f"Unknown rule_set: {rule_set}",
                         suggestion=f"Supported: {sorted(self.SUPPORTED_RULE_SETS)}")],
            )

        return self._rule_sets[rule_set].validate(structured_output, ctx)

    @property
    def available_rule_sets(self) -> list[str]:
        return sorted(self._rule_sets.keys())

    def health_check(self) -> dict:
        return {
            "status": "healthy",
            "loaded_rule_sets": self.available_rule_sets,
            "total_rule_sets": len(self._rule_sets),
        }
