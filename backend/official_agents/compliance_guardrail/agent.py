"""Compliance Guardrail Agent — implementation.

Phase 3-D1 Task 5: 3 Runnable Agents.

Input: text containing a coding set + optional EMR context. Accepted
formats (auto-detected):
  1. JSON object with primary_diagnosis / secondary_diagnoses / procedures
     + optional encounter_text
  2. Plain text containing ICD-10 + ICD-9-CM-3 codes (parsed via regex)

Output (ComplianceGuardrailOutputSchema):
  {
    "review_conclusion": "PASS" | "WARNING" | "FAIL",
    "issues_found": [...],
    "manual_review_required": bool,
    "drg_suggestion": str,
    "compliance_checks": {
      "primary_dx_present": bool,
      "no_upcoding_risk": bool,
      "procedure_dx_consistency": bool,
      "drg_readiness": bool
    },
    "rule_set": "medical_coding",
    "trace_refs": {"run_id", "agent_ref"}
  }

Deterministic: no LLM. RuleEngine + guardrail heuristics.
"""

from __future__ import annotations

import uuid
from typing import Any

from official_agents.code_validation.agent_legacy import _normalize_input


def _guardrail_checks(coding_set: dict, emr_text: str) -> tuple[list[dict], dict]:
    """Run compliance guardrail heuristics.

    Returns (issues, check_summary). Issues is a list of {severity, rule_id,
    message, suggestion, category} dicts in the same shape as
    RuleEngine issues, so the frontend can render them uniformly.
    """
    issues: list[dict] = []
    summary: dict[str, bool] = {
        "primary_dx_present": True,
        "no_upcoding_risk": True,
        "procedure_dx_consistency": True,
        "drg_readiness": True,
    }

    primary = coding_set.get("primary_diagnosis") or {}
    primary_code = primary.get("code", "") if isinstance(primary, dict) else ""
    secondary = coding_set.get("secondary_diagnoses") or []
    procedures = coding_set.get("procedures") or []

    # Check 1: Primary dx present
    if not primary_code:
        summary["primary_dx_present"] = False
        issues.append({
            "severity": "critical",
            "rule_id": "CG-001",
            "message": "缺少主要诊断编码 — 医保结算清单必须包含主要诊断",
            "suggestion": "请补充主要诊断 ICD-10 编码",
            "category": "compliance",
        })

    # Check 2: Upcoding heuristic — osteoporotic vertebral fracture should
    # consider M80.x, not M48.x. Only fires when EMR text mentions
    # osteoporosis + vertebral fracture AND the primary is M48.x.
    if emr_text and primary_code.startswith("M48"):
        has_osteoporosis = any(
            kw in emr_text
            for kw in ["骨质疏松", "骨量减少", "骨密度降低"]
        )
        has_vertebral_fx = any(
            kw in emr_text
            for kw in ["椎体压缩骨折", "椎体骨折", "压缩性骨折", "病理性骨折"]
        )
        if has_osteoporosis and has_vertebral_fx:
            summary["no_upcoding_risk"] = False
            issues.append({
                "severity": "high",
                "rule_id": "CG-002",
                "message": (
                    f"主诊断 {primary_code} (M48.x 椎体其他疾患) 可能存在 upcoding 风险 — "
                    "病历提示骨质疏松 + 椎体压缩骨折，应优先评估 M80.x "
                    "(骨质疏松伴病理性骨折)"
                ),
                "suggestion": "请编码员复核主诊断是否应为 M80.x",
                "category": "compliance",
            })

    # Check 3: Procedure-dx consistency — every procedure should have at
    # least one diagnosis that explains it (simplified heuristic: procedure
    # list non-empty requires primary dx non-empty).
    if procedures and not primary_code:
        summary["procedure_dx_consistency"] = False
        issues.append({
            "severity": "high",
            "rule_id": "CG-003",
            "message": "存在手术操作编码但缺少主要诊断 — 手术必须有对应诊断",
            "suggestion": "请补充与手术操作一致的主要诊断",
            "category": "consistency",
        })

    # Check 4: DRG readiness — for surgical cases (>= 1 procedure), need
    # primary dx + at least 1 procedure. For medical cases (no procedure),
    # need primary dx.
    if not primary_code:
        summary["drg_readiness"] = False
    elif procedures and not any(
        isinstance(p, dict) and p.get("code") for p in procedures
    ):
        summary["drg_readiness"] = False
        issues.append({
            "severity": "medium",
            "rule_id": "CG-004",
            "message": "手术操作列表为空壳 — DRG 分组需要至少 1 个有效手术操作编码",
            "suggestion": "请补充手术操作 ICD-9-CM-3 编码或确认本次为非手术病例",
            "category": "compliance",
        })

    return issues, summary


def _drg_suggestion(coding_set: dict, checks: dict) -> str:
    """Generate a DRG readiness suggestion string."""
    primary = coding_set.get("primary_diagnosis") or {}
    primary_code = primary.get("code", "") if isinstance(primary, dict) else ""
    procedures = coding_set.get("procedures") or []
    proc_count = sum(1 for p in procedures if isinstance(p, dict) and p.get("code"))

    if not primary_code:
        return "DRG 分组前必须补充主要诊断编码"
    if proc_count == 0:
        return (
            f"主要诊断 {primary_code} 已就绪，无手术操作 — 按内科 DRG 组评估；"
            "如本次为手术病例，请补充手术操作 ICD-9-CM-3 编码"
        )
    return (
        f"DRG 就绪：主要诊断 {primary_code} + {proc_count} 个手术操作 — "
        "可提交 DRG 分组器"
    )


def _conclusion(issues: list[dict]) -> str:
    if not issues:
        return "PASS"
    severities = {i.get("severity", "info") for i in issues}
    if severities & {"critical"}:
        return "FAIL"
    if severities & {"high"}:
        return "WARNING"
    return "PASS"


async def run(input_text: str, *, run_id: str = "") -> dict:
    """Run the Compliance Guardrail Agent."""
    from compliance_services.medical_coding_rules import MedicalCodingRuleSet
    from compliance_services.rule_engine import RuleEngine

    engine = RuleEngine()
    engine.register(MedicalCodingRuleSet())

    coding_set, emr_text = _normalize_input(input_text)
    rule_result = engine.validate(
        "medical_coding",
        coding_set,
        context={"encounter_text": emr_text},
    )
    rule_issues = [i.to_dict() for i in rule_result.issues]

    guardrail_issues, checks = _guardrail_checks(coding_set, emr_text)
    all_issues = rule_issues + guardrail_issues

    conclusion = _conclusion(all_issues)
    manual_review = bool(
        any(i.get("severity") in ("critical", "high") for i in all_issues)
        or conclusion == "FAIL"
    )

    return {
        "review_conclusion": conclusion,
        "issues_found": all_issues,
        "manual_review_required": manual_review,
        "drg_suggestion": _drg_suggestion(coding_set, checks),
        "compliance_checks": checks,
        "rule_set": "medical_coding",
        "fired_rules": rule_result.rules_fired,
        "trace_refs": {
            "run_id": run_id or str(uuid.uuid4()),
            "agent_ref": "icoder/compliance-guardrail-agent@1.0.0",
            "rule_set": "medical_coding",
        },
    }


__all__ = ["run"]
