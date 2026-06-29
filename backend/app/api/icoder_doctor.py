"""iCoDer Doctor API — runtime productization health surface (P1.0-C).

Thin wrapper around ``scripts/icoder_doctor.py`` so the frontend
``/runtime/doctor`` page can fetch the same report as the CLI:

* ``GET /api/icoder/doctor`` — full report (all 20 checks)
* ``GET /api/icoder/doctor/{check_id}`` — single check by full or prefix id

Design rules:
* No fake data. Doctor reads from filesystem + app.state.
* Runs in-process (no subprocess) so it can introspect ``app.state``
  post-lifespan, identical to what the CLI sees.
* Exit-code semantics are surfaced as ``verdict`` (OK / WARN / FAIL).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/icoder/doctor", tags=["agent-hub"])


# Lazy import so the doctor script (and its transitive deps) is only
# loaded when the endpoint is hit, not at module-load time. Also
# guarantees a clean sys.path: the script lives in backend/scripts/.
_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "icoder_doctor.py"


def _ensure_doctor_importable() -> None:
    backend_root = str(_SCRIPT_PATH.parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)


@router.get("")
async def get_doctor_report() -> dict[str, Any]:
    """Run the full doctor (20 checks) and return the structured report.

    Returns the same shape as ``icoder_doctor.py --json`` so the
    frontend can render it directly without remapping.
    """
    _ensure_doctor_importable()
    try:
        from scripts.icoder_doctor import run_doctor
    except Exception as e:
        logger.exception("icoder_doctor import failed")
        raise HTTPException(
            status_code=500,
            detail={
                "error_code": "DOCTOR_IMPORT_FAILED",
                "message": f"Failed to import icoder_doctor: {e}",
            },
        )
    report = run_doctor()
    return report.to_dict()


@router.get("/{check_id}")
async def get_doctor_check(check_id: str) -> dict[str, Any]:
    """Run a single check by full id (``19.fewshot_flag_default_off``)
    or short prefix (``19``)."""
    _ensure_doctor_importable()
    try:
        from scripts.icoder_doctor import run_doctor
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error_code": "DOCTOR_IMPORT_FAILED", "message": str(e)},
        )
    report = run_doctor(check_ids={check_id})
    if not report.checks:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "DOCTOR_CHECK_NOT_FOUND",
                "check_id": check_id,
                "message": f"No doctor check matches id={check_id!r}",
            },
        )
    return {
        "verdict": report.verdict,
        "check": report.checks[0].to_dict(),
    }


__all__ = ["router"]