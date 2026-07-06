"""iCoDer Medical Coding Agent — official Agent Pack.

Agent ref: icoder/medical-coding-agent@2.0.0
Category: medical-coding (display: Coding and Revenue Cycle / 编码与收入周期)
Security tier: Tier 1 (read-only tools)
Maturity: MVP (production_ready=false, human_review=required)

This agent (Corti-style, MVP):
1. Receives patient encounter text (Chinese hospital EMR)
2. Synthesizes encounter summary (chief complaint / treatment course / key findings)
3. Extracts clinical evidence with char-anchored spans (no inference without evidence)
4. Searches coding candidates (ICD-10-CN + ICD-9-CM-3) via internal engine
5. Assigns codes with per-code evidence + confidence
6. Validates coding against MedCodERRetrievalRuleSet
7. Identifies documentation gaps + uncodable items
8. Generates review summary (PASS/WARNING/FAIL + manual_review_required)

Internal engine: icoder/medcoder-coding-review-agent@1.0.0 (5-stage MedCodER
NAACL 2025 pipeline — Extraction → Retrieval → Merge → Re-Rank → Calibration).
The 5-stage pipeline is an implementation detail; user-facing contract is the
Corti-style 8-field MedicalCodingAgentOutputV2.

MVP red lines enforced via system_prompt + permissions:
- No upcoding (selecting higher-paying codes without evidence)
- No inference (coding without explicit textual support)
- No "fully automated" language — every code requires human review
- No F1 / model effect display
"""
