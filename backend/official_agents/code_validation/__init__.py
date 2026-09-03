"""iCoDer Code Validation Agent — official Agent Pack.

Agent ref: icoder/code-validation-agent@1.0.0
Category: coding_revenue_cycle (display: Coding and Revenue Cycle / 编码与收入周期)
Security tier: Tier 1 (read-only rule engine)
Maturity: runnable (Phase 3-D1 Task 5)

This agent:
1. Receives a coding set (JSON or free text containing ICD-10 + ICD-9-CM-3 codes)
2. Parses the input into a structured coding set (primary_dx / secondary_dx / procedures)
3. Runs MedicalCodingRuleSet (R001-R010 + MC-R-M80-001) via the RuleEngine
4. Returns issues_found + review_conclusion (PASS / WARNING / FAIL) + fired_rules

Deterministic — no LLM. The RuleEngine is the source of truth.
"""
