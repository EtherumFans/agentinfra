"""iCoDer DRG Analyzer — official Agent Pack.

Agent ref: icoder/drg-analyzer@1.0.0
Category: 医保 (Medical Insurance)
Security tier: Tier 1 (read-only tools)

This agent:
1. Receives encoded medical record (primary diagnosis + secondary + procedures)
2. Runs CHS-DRG 1.1 grouping via bundled grouper
3. Validates with DRG/DIP rules (DRG001-DRG004, DIP001-DIP003)
4. Predicts DRG code + name + CC/MCC level + DIP payment impact
5. Returns risk flags for manual review

The actual Python implementation lives in:
  backend/app/services/drg_analyzer_service.py

This directory only contains the manifest (agent_pack.json) and
documentation. The Python package is hyphen-named (drg-analyzer) and
cannot be imported directly, so the service is exposed via the
importable path app.services.drg_analyzer_service.
"""

