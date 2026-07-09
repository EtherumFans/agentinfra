"""iCoDer Note Completeness Agent — official Agent Pack.

Agent ref: icoder/note-completeness-agent@1.0.0
Category: coding_revenue_cycle (display: Documentation / 病历完整性)
Security tier: Tier 1 (read-only text analysis)
Maturity: runnable (Phase 3-D1 Task 5)

This agent:
1. Receives EMR/note text (Chinese hospital discharge summary, progress
   note, etc.)
2. Detects required sections per 《病历书写基本规范》:
   - 主诉 (Chief Complaint)
   - 现病史 (History of Present Illness)
   - 既往史 (Past Medical History)
   - 体格检查 (Physical Examination)
   - 辅助检查 (Auxiliary Examinations)
   - 诊断 (Diagnosis)
   - 治疗经过 (Treatment Course)
   - 手术记录 (Operation Record, surgical cases only)
3. Computes completeness_score (present / total)
4. Returns documentation_gaps + missing_sections + review_conclusion

Deterministic — no LLM. Regex-based section detection.
"""
