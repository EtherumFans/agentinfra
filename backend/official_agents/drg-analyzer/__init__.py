"""iCoDer DRG/DIP risk-review Agent Pack.

Agent ref: icoder/drg-analyzer@1.1.3
Category: 医保 (Medical Insurance)
Security tier: Tier 1 (read-only tools)

This agent:
1. Receives encoded medical record (primary diagnosis + secondary + procedures)
2. Reviews evidence-backed coding risks without calling a settlement grouper
3. Requires manual review for every result
4. Declares its unverified rule authority and non-billing status
5. Never assigns an official DRG/DIP group or payment value

The importable Agent entry point lives at
``official_agents.drg_analyzer.agent`` and delegates deterministic grouping
risk analysis to ``app.services.drg_analyzer_service``.  The hyphen-named
directory remains the canonical manifest location.
"""
