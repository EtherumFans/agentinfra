"""iCoDer Compliance Guardrail Agent — official Agent Pack.

Agent ref: icoder/compliance-guardrail-agent@1.0.0
Category: coding_revenue_cycle
Security tier: Tier 1 (read-only rule engine + heuristics)
Maturity: runnable (Phase 3-D1 Task 5)

This agent:
1. Receives a coding set (JSON or free text) + optional EMR context
2. Runs MedicalCodingRuleSet (R001-R010 + MC-R-M80-001)
3. Runs compliance guardrail checks:
   - Primary diagnosis present
   - No upcoding heuristics (M80.x vs M48.x for osteoporotic vertebral fx)
   - Procedure-diagnosis consistency (sample rule: no procedure without dx)
   - DRG readiness (primary dx + at least one procedure for surgical DRGs)
4. Returns issues_found + review_conclusion + drg_suggestion

Deterministic — no LLM. The RuleEngine + compliance heuristics are the
source of truth.
"""
