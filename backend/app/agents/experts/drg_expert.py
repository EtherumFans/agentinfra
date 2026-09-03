# DEPRECATED (P1.3 Stage 5, 2026-07-02) — Legacy 单体 expert. Phase 2 切换到 app/icoder/agent_runtime/experts/ 后删. 见 docs/architecture/MAINLINE_VS_LEGACY.md §3.1.
# iCoDer - DRG/DIP Expert + Documentation Gap + Evidence Verification Experts
import time
from app.agents.base import BaseExpert
from app.config import settings
from app.services.drg_grouper import group_drg


class DRGDIPExpert(BaseExpert):
    name = "DRG/DIP Expert"
    description = "Development-only DRG/DIP coding risk review; not a payment engine"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("analyzing DRG/DIP impact", context)

        primary_diag = context.get("primary_diagnosis", {})
        main_proc = context.get("main_procedure", {})
        secondary_diag = context.get("secondary_diagnoses", [])
        other_proc = context.get("other_procedures", [])

        # Risk analysis based on coding patterns
        risks = []
        recommendations = []

        diag_code = primary_diag.get("code", "")
        proc_code = main_proc.get("code", "") if main_proc else ""

        # Rule-based DRG risk detection
        if diag_code.startswith("M80"):
            risks.append({
                "type": "grouping_risk",
                "severity": "low",
                "description": "骨质疏松伴病理性骨折通常分入骨科DRG组。确保与创伤性骨折正确区分，后者可能分入不同DRG组。",
            })

        if diag_code.endswith(".9") and not diag_code.startswith("Z"):
            risks.append({
                "type": "specificity_risk",
                "severity": "medium",
                "description": f"主诊断 {diag_code} 为未特指编码。如果能从病历中获取更特异信息，建议使用更特异的编码以提高DRG分组精度。",
            })
            recommendations.append("仅在病历证据支持时使用更特异的诊断编码；不得为分组收益推断未记录事实。")

        # Check for missing MCC/CC
        known_mcc = ["N17", "J96", "I50", "A41", "R57", "K72", "J80", "G93", "I61", "I62", "I63"]
        has_mcc = any(s.get("code", "").startswith(tuple(known_mcc)) for s in secondary_diag)
        if not has_mcc:
            recommendations.append("请仅依据病历证据核实是否遗漏重要合并症/并发症(MCC/CC)编码，不得为提高权重补码。")

        # Procedure mismatch check
        if proc_code and diag_code:
            if proc_code.startswith("81.6") and not any(k in diag_code for k in ["M80", "M81", "S32", "S22"]):
                risks.append({
                    "type": "code_mismatch",
                    "severity": "high",
                    "description": f"主要手术 {proc_code}（脊柱手术）与主诊断 {diag_code} 不匹配。请核实诊断与手术的对应关系。",
                })

        return self._timed_result(start, {
            "expert": self.name,
            "drg_risks": risks,
            "recommendations": recommendations,
            "drg_result": self._group_drg(diag_code, proc_code),
        })

    def _group_drg(self, diag_code: str, proc_code: str) -> dict:
        """Return a governed, non-authoritative development candidate."""
        try:
            return group_drg([diag_code], proc_code or None)
        except Exception:
            return {
                "drg": "",
                "drg_name": "开发期规则资产治理门未满足",
                "coverage": False,
                "candidate_only": True,
                "billing_authoritative": False,
                "manual_review_required": True,
                "status": "unavailable",
            }


class DocumentationGapExpert(BaseExpert):
    name = "Documentation Gap Expert"
    description = "Identifies missing or insufficient documentation affecting coding accuracy"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("analyzing documentation gaps", context)

        evidence = context.get("evidence", {})
        diagnosis_candidates = context.get("diagnosis_candidates", [])
        procedure_candidates = context.get("procedure_candidates", [])
        primary_diag = context.get("primary_diagnosis", {})

        gaps = []

        # Check for unspecified codes with insufficient evidence
        for c in diagnosis_candidates:
            code = c.get("code", "")
            if code and code.endswith(".9"):
                gaps.append({
                    "severity": "medium",
                    "type": "specificity_gap",
                    "code": code,
                    "finding": c.get("finding", ""),
                    "description": f"诊断 {code}（{c.get('name', '')}）使用了未特指编码。请确认病历中是否有更特异的诊断依据。",
                    "suggestion": f"建议补充：{c.get('finding', '')}的具体分型、部位、病因或分期信息。",
                })

        # Check procedures without clear body site
        for c in procedure_candidates:
            if not c.get("body_site"):
                gaps.append({
                    "severity": "low",
                    "type": "anatomical_site_gap",
                    "code": c.get("code", ""),
                    "finding": c.get("procedure_name", ""),
                    "description": f"手术 {c.get('procedure_name', '')} 缺少明确的解剖部位记录。",
                    "suggestion": "建议在手术记录中补充手术部位和解剖层次描述。",
                })

        # Check diagnosis without etiology
        for c in diagnosis_candidates:
            finding = c.get("finding", "")
            if any(kw in finding for kw in ["骨折", "感染", "炎症", "出血"]) and c.get("score", 0) > 0.5:
                has_etiology = any(
                    kw in finding for kw in ["骨质疏松", "创伤", "细菌", "病毒", "手术后", "肿瘤"]
                )
                if not has_etiology:
                    gaps.append({
                        "severity": "low",
                        "type": "etiology_gap",
                        "finding": finding,
                        "description": f"诊断 '{finding}' 未明确病因，可能影响编码特异性和DRG分组。",
                        "suggestion": "建议在病程记录或出院小结中补充病因信息。",
                    })

        return self._timed_result(start, {
            "expert": self.name,
            "documentation_gaps": gaps,
            "gap_count": len(gaps),
            "suggestions_for_clinicians": [g["suggestion"] for g in gaps],
        })


class EvidenceVerificationExpert(BaseExpert):
    name = "Evidence Verification Expert"
    description = "Verifies every code has supporting evidence from the medical record"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("verifying evidence bindings", context)

        diagnosis_candidates = context.get("diagnosis_candidates", [])
        procedure_candidates = context.get("procedure_candidates", [])
        primary_diag = context.get("primary_diagnosis", {})

        verifications = []
        all_candidates = diagnosis_candidates + procedure_candidates

        for c in all_candidates:
            has_evidence = bool(c.get("evidence_text", ""))
            evidence_quality = "good" if len(c.get("evidence_text", "")) > 20 else (
                "marginal" if c.get("evidence_text") else "none"
            )

            is_negated = c.get("negation", False)
            confidence = c.get("score", 0)
            certainty = c.get("certainty", "")

            # Determine support status
            if is_negated:
                status = "unsupported"
                reason = "Finding is negated/ruled out."
            elif not has_evidence:
                status = "needs_review"
                reason = "No direct evidence found in medical record text."
            elif evidence_quality == "marginal":
                status = "needs_review"
                reason = "Evidence text is brief — verify against full record."
            elif confidence < settings.AGENT_CONFIDENCE_THRESHOLD:
                status = "needs_review"
                reason = f"Confidence below threshold ({confidence:.2f} < {settings.AGENT_CONFIDENCE_THRESHOLD})."
            else:
                status = "supported"
                reason = "Evidence found and confidence meets threshold."

            verifications.append({
                "code": c.get("code", ""),
                "name": c.get("name", ""),
                "status": status,
                "has_evidence": has_evidence,
                "evidence_quality": evidence_quality,
                "confidence": confidence,
                "reason": reason,
            })

        # Calculate metrics
        total = len(verifications)
        supported = sum(1 for v in verifications if v["status"] == "supported")
        unsupported = sum(1 for v in verifications if v["status"] == "unsupported")
        needs_review = sum(1 for v in verifications if v["status"] == "needs_review")

        return self._timed_result(start, {
            "expert": self.name,
            "verifications": verifications,
            "summary": {
                "total_codes": total,
                "supported": supported,
                "unsupported": unsupported,
                "needs_review": needs_review,
                "evidence_binding_rate": round(supported / total, 2) if total > 0 else 0,
            },
        })
