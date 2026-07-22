"""Medical Calculator Expert — Corti public §3.2 key 3 of 9 (A1B-AE.6 stub).

Corti public docs describe this Expert as providing validated clinical
calculators (e.g. CHA2DS2-VASc, MELD-Na, CURB-65). iCoDer's A1B-AE.6
scope is the Expert Registry entry + a deterministic BMI + creatinine
clearance (Cockcroft-Gault) calculator as proof-of-presence.

This is NOT a comprehensive clinical calculator library. It is a
stub that:
1. Registers under canonical_key='medical-calculator' with
   corti_alignment='CORTI_ADAPTED' (iCoDer ships a subset of Corti's
   calculator catalogue).
2. Returns deterministic numerical results for the 2 implemented
   calculators (BMI, Cockcroft-Gault).
3. Raises NotImplementedError for any other calculator key, so
   callers know the boundary explicitly.

Out-of-scope: CHA2DS2-VASc, MELD-Na, CURB-65, etc. These are
candidates for A1B-AE.9 tech-debt liquidation or later phases.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


MEDICAL_CALCULATOR_EXPERT_CANONICAL_KEY = "medical-calculator"
MEDICAL_CALCULATOR_EXPERT_NAME = "Medical Calculator Expert"

# Implemented calculators (subset of Corti's catalogue)
SUPPORTED_CALCULATORS = ("bmi", "cockcroft-gault")


@dataclass
class CalculatorResult:
    calculator: str
    inputs: dict
    output: dict
    warnings: list[str]


def calculate(calculator: str, **inputs) -> CalculatorResult:
    """Dispatch to a named calculator.

    Raises NotImplementedError for unknown calculators. Callers should
    catch this explicitly and surface a fallback rather than letting
    it propagate as a 500.
    """
    key = (calculator or "").lower().strip()
    if key == "bmi":
        return _bmi(**inputs)
    if key in ("cockcroft-gault", "cockcroft_gault", "crcl"):
        return _cockcroft_gault(**inputs)
    raise NotImplementedError(
        f"calculator {calculator!r} not implemented; "
        f"supported: {SUPPORTED_CALCULATORS}"
    )


def _bmi(*, weight_kg: float, height_m: float) -> CalculatorResult:
    if weight_kg <= 0 or height_m <= 0:
        raise ValueError("weight_kg and height_m must be positive")
    bmi = weight_kg / (height_m * height_m)
    if bmi < 18.5:
        category = "underweight"
    elif bmi < 25:
        category = "normal"
    elif bmi < 30:
        category = "overweight"
    else:
        category = "obese"
    return CalculatorResult(
        calculator="bmi",
        inputs={"weight_kg": weight_kg, "height_m": height_m},
        output={"bmi": round(bmi, 2), "category": category},
        warnings=[],
    )


def _cockcroft_gault(
    *,
    age_years: int,
    weight_kg: float,
    serum_creatinine_mg_dl: float,
    sex: str,
) -> CalculatorResult:
    """Cockcroft-Gault creatinine clearance estimate (mL/min).

    Sex: 'male' or 'female' (case-insensitive). Females multiply by 0.85.
    """
    if age_years <= 0:
        raise ValueError("age_years must be positive")
    if weight_kg <= 0 or serum_creatinine_mg_dl <= 0:
        raise ValueError("weight_kg and serum_creatinine_mg_dl must be positive")
    sex_norm = (sex or "").lower().strip()
    multiplier = 0.85 if sex_norm == "female" else 1.0
    if sex_norm not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female'")

    crcl = ((140 - age_years) * weight_kg) / (72 * serum_creatinine_mg_dl)
    crcl *= multiplier

    warnings = []
    if crcl < 30:
        warnings.append("CrCl < 30 mL/min — renal dose adjustment may be required")
    if age_years >= 65:
        warnings.append("Age >= 65 — consider frailty-adjusted dosing")

    return CalculatorResult(
        calculator="cockcroft-gault",
        inputs={
            "age_years": age_years,
            "weight_kg": weight_kg,
            "serum_creatinine_mg_dl": serum_creatinine_mg_dl,
            "sex": sex_norm,
        },
        output={"crcl_ml_min": round(crcl, 2)},
        warnings=warnings,
    )


__all__ = [
    "MEDICAL_CALCULATOR_EXPERT_CANONICAL_KEY",
    "MEDICAL_CALCULATOR_EXPERT_NAME",
    "SUPPORTED_CALCULATORS",
    "CalculatorResult",
    "calculate",
]
