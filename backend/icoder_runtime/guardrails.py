"""Safety Guardrails — clinical safety enforcement layer.

iCoDer Agentic Framework equivalent: "Safety enforcement — enforces guardrails,
type validation, and policy-driven constraints to ensure safe operation in
clinical environments."

Difficulty: MEDIUM — rule-based validation engine, clinical safety rules,
input/output validation. Not an ML system, just a thorough rule checker.
"""
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class GuardrailViolation(Exception):
    """Raised when a safety guardrail check fails."""
    def __init__(self, rule: str, message: str, severity: str = "error"):
        self.rule = rule
        self.message = message
        self.severity = severity
        super().__init__(f"[{severity}] {rule}: {message}")


class SafetyGuardrails:
    """Centralized safety enforcement for clinical AI operations.

    Rules are organized by category:
    - input_validation: Check user input before processing
    - output_validation: Check LLM output before returning to user
    - clinical_safety: Healthcare-specific safety rules
    - data_privacy: PII/PHI detection
    """

    # Clinical safety — must-have checks
    CLINICAL_SAFETY_RULES = [
        {
            "name": "no_medication_prescription",
            "pattern": r"(prescribe|处方|take\s+\d+\s*mg|服用\s*\d+\s*毫克)",
            "message": "AI does not prescribe medications. Suggest consulting a physician.",
            "severity": "error",
        },
        {
            "name": "no_diagnosis_without_disclaimer",
            "pattern": r"(确诊|definitively\s+diagnos)",
            "message": "Coding suggestions are not clinical diagnoses. Add disclaimer.",
            "severity": "warning",
        },
        {
            "name": "no_emergency_triage",
            "pattern": r"(immediately\s+go\s+to\s+ER|立即去急诊|call\s+911|拨打\s*120)",
            "message": "AI does not perform emergency triage. Direct to emergency services.",
            "severity": "error",
        },
    ]

    # Data privacy — PHI detection patterns (China-specific)
    PHI_PATTERNS = [
        # Chinese ID card (18 digits with checksum pattern)
        (r"\b[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b", "中国居民身份证号"),
        # Chinese mobile phone (1xx-xxxx-xxxx)
        (r"\b1[3-9]\d[-\s]?\d{4}[-\s]?\d{4}\b", "中国手机号码"),
        # Medical Record Number (住院号/病历号 pattern)
        (r"(住院号|病历号|病案号|MRN|patient_id)[:\s：]*[A-Za-z0-9\-]+", "病历号"),
        # Email address
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "电子邮箱"),
        # Credit card number
        (r"\b\d{15,19}\b", "银行卡号"),
    ]

    # Input validation
    MAX_INPUT_LENGTH = 50000  # 50KB max input
    MIN_INPUT_LENGTH = 10
    BLOCKED_TERMS = ["hack", "exploit", "inject", "bypass", "override safety"]

    async def validate_input(self, text: str, context: dict | None = None) -> dict:
        """Validate user input before processing.

        Returns {"valid": bool, "violations": [...], "sanitized": str}
        """
        violations = []

        # Length checks
        if len(text) < self.MIN_INPUT_LENGTH:
            violations.append({"rule": "min_length", "message": "Input too short", "severity": "warning"})
        if len(text) > self.MAX_INPUT_LENGTH:
            violations.append({"rule": "max_length", "message": f"Input exceeds {self.MAX_INPUT_LENGTH} chars", "severity": "error"})

        # Blocked terms
        for term in self.BLOCKED_TERMS:
            if term.lower() in text.lower():
                violations.append({"rule": "blocked_term", "message": f"Blocked term detected: {term}", "severity": "error"})

        # PHI check
        for pattern, label in self.PHI_PATTERNS:
            if re.search(pattern, text):
                violations.append({"rule": "phi_detected", "message": f"Potential {label} in input", "severity": "warning"})

        has_errors = any(v["severity"] == "error" for v in violations)
        return {"valid": not has_errors, "violations": violations, "warnings": len(violations)}

    async def validate_output(self, text: str, context: dict | None = None) -> dict:
        """Validate LLM output before returning to user.

        Returns {"valid": bool, "violations": [...], "requires_disclaimer": bool}
        """
        violations = []
        requires_disclaimer = False

        for rule in self.CLINICAL_SAFETY_RULES:
            if re.search(rule["pattern"], text, re.IGNORECASE):
                violations.append({"rule": rule["name"], "message": rule["message"], "severity": rule["severity"]})
                if rule["name"] == "no_diagnosis_without_disclaimer":
                    requires_disclaimer = True

        # Check for hallucinated codes (plausible but wrong format)
        suspicious_codes = re.findall(r'\b[A-Z]\d{2}\.\d{4,}\b', text)
        if suspicious_codes:
            violations.append({"rule": "suspicious_code_format", "message": f"Unusually specific codes: {suspicious_codes[:3]}", "severity": "warning"})

        has_errors = any(v["severity"] == "error" for v in violations)
        result = {"valid": not has_errors, "violations": violations, "requires_disclaimer": requires_disclaimer}

        if requires_disclaimer and not has_errors:
            result["suggestion"] = "Consider adding: 'This is an AI-assisted coding suggestion. Clinical judgment required.'"

        return result

    async def enforce_all(self, input_text: str, output_text: str) -> dict:
        """Run all guardrail checks and return a combined report."""
        input_result = await self.validate_input(input_text)
        output_result = await self.validate_output(output_text)

        all_violations = input_result["violations"] + output_result["violations"]
        errors = [v for v in all_violations if v["severity"] == "error"]

        return {
            "passed": len(errors) == 0,
            "input_valid": input_result["valid"],
            "output_valid": output_result["valid"],
            "violations": all_violations,
            "error_count": len(errors),
            "warning_count": len([v for v in all_violations if v["severity"] == "warning"]),
        }


guardrails = SafetyGuardrails()
