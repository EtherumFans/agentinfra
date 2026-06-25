"""``calibrate_confidence`` MCP handler — wraps ``confidence_calibrator.calibrate_all``.

Input shape (validated upstream by Pydantic):
  - All 8 fields of ``confidence_calibrator.calibrate_all`` signature,
    forwarded 1:1.

Output:
  - The exact dict returned by ``calibrate_all``:
      ``{coding_confidences, routing_decisions, metrics}``

Behavior:
  - Delegates to ``app.services.confidence_calibrator.calibrate_all``.
  - The 5-component weighted calibration (audit Part 7.1) is NOT
    implemented here; M2 reuses the existing 360-LOC service as-is.
    Calibration floor + risk-tier policy are unchanged.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    # Lazy import — confidence_calibrator pulls in some pydantic helpers
    # that the test suite doesn't always need at import time.
    from app.services.confidence_calibrator import calibrate_all

    result = calibrate_all(
        diagnosis_candidates=arguments.get("diagnosis_candidates") or [],
        procedure_candidates=arguments.get("procedure_candidates") or [],
        primary_diagnosis=arguments.get("primary_diagnosis") or {},
        evidence_ranking=arguments.get("evidence_ranking") or {},
        disagreement_analysis=arguments.get("disagreement_analysis") or {},
        primary_diag_reasoning=arguments.get("primary_diag_reasoning") or {},
        gold_diagnosis_codes=arguments.get("gold_diagnosis_codes"),
        gold_procedure_codes=arguments.get("gold_procedure_codes"),
    )

    # ``calibrate_all`` already returns a JSON-safe dict; pass through.
    return result


__all__ = ["handle"]