"""Medical Calculator Expert — Corti public §3.2 key 3 of 9.

A1B-AE.6 (2026-07-22): STUB — BMI + Cockcroft-Gault only.
A1B-AE-R.4.a (2026-07-23): EXPANDED — 6 deterministic clinical calculators:
  - BMI (weight/height² + WHO category)
  - Cockcroft-Gault (creatinine clearance for drug dosing)
  - CHA2DS2-VASc (AF stroke risk; Lip GYH et al., Lancet 2012)
  - MELD-Na (OPTN 2022 revision; Kim WR et al., Hepatology 2022)
  - eGFR CKD-EPI 2021 (race-free; Inker LA et al., NEJM 2021)
  - Wells DVT (Wells 2003; low/moderate/high risk tiers)

All calculators are deterministic (no LLM calls). All formulas cite
their source guideline. Validation asserts numeric correctness within
published tolerances; in real clinical deployments, outputs should be
reviewed by a licensed clinician before driving treatment decisions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


MEDICAL_CALCULATOR_EXPERT_CANONICAL_KEY = "medical-calculator"
MEDICAL_CALCULATOR_EXPERT_NAME = "Medical Calculator Expert"

SUPPORTED_CALCULATORS = (
    "bmi",
    "cockcroft-gault",
    "cha2ds2-vasc",
    "meld-na",
    "egfr-ckd-epi-2021",
    "wells-dvt",
)


@dataclass
class CalculatorResult:
    calculator: str
    inputs: dict
    output: dict
    warnings: list[str] = field(default_factory=list)


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
    if key in ("cha2ds2-vasc", "cha2ds2vasc", "chaads-vasc"):
        return _cha2ds2_vasc(**inputs)
    if key in ("meld-na", "meld_na", "meldna", "meld"):
        return _meld_na(**inputs)
    if key in ("egfr-ckd-epi-2021", "egfr", "egfr-ckd-epi"):
        return _egfr_ckd_epi_2021(**inputs)
    if key in ("wells-dvt", "wells_dvt"):
        return _wells_dvt(**inputs)
    raise NotImplementedError(
        f"calculator {calculator!r} not implemented; "
        f"supported: {SUPPORTED_CALCULATORS}"
    )


# ─────────────────────────────────────────────────────────────────────
# BMI (WHO)
# ─────────────────────────────────────────────────────────────────────


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
    )


# ─────────────────────────────────────────────────────────────────────
# Cockcroft-Gault (CG) — creatinine clearance for drug dosing
# ─────────────────────────────────────────────────────────────────────


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
    if sex_norm not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female'")
    multiplier = 0.85 if sex_norm == "female" else 1.0

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


# ─────────────────────────────────────────────────────────────────────
# CHA2DS2-VASc — AF stroke risk (Lip GYH et al., Lancet 2012)
# ─────────────────────────────────────────────────────────────────────


def _cha2ds2_vasc(
    *,
    age_years: int,
    sex: str,
    chf: bool = False,
    hypertension: bool = False,
    diabetes: bool = False,
    stroke_tia_history: bool = False,
    vascular_disease: bool = False,
) -> CalculatorResult:
    """CHA2DS2-VASc stroke risk score for atrial fibrillation.

    Scoring:
      C  CHF                      = 1
      H  Hypertension             = 1
      A2 Age >= 75                = 2
      D  Diabetes                 = 1
      S2 Stroke/TIA/thromboembolism = 2
      V  Vascular disease (MI/PAD/aortic plaque) = 1
      A  Age 65-74                = 1
      Sc Sex category female      = 1

    Guideline: Lip GYH et al. "Refining clinical risk stratification for
    predicting stroke and thromboembolism in atrial fibrillation using a
    novel risk factor-based approach." Chest/Lancet 2012.
    """
    if age_years < 0:
        raise ValueError("age_years must be non-negative")
    sex_norm = (sex or "").lower().strip()
    if sex_norm not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female'")

    score = 0
    if chf:
        score += 1
    if hypertension:
        score += 1
    if age_years >= 75:
        score += 2
    elif 65 <= age_years < 75:
        score += 1
    if diabetes:
        score += 1
    if stroke_tia_history:
        score += 2
    if vascular_disease:
        score += 1
    if sex_norm == "female":
        score += 1

    if score == 0:
        risk_tier = "low"
        anticoagulation_recommendation = (
            "No anticoagulation recommended (score 0 in men, 1 in women is low-risk)"
        )
    elif score == 1 and sex_norm == "male":
        risk_tier = "low-moderate"
        anticoagulation_recommendation = (
            "Consider anticoagulation; shared decision-making recommended"
        )
    elif score <= 2 and sex_norm == "female":
        risk_tier = "low-moderate"
        anticoagulation_recommendation = (
            "Consider anticoagulation; shared decision-making recommended"
        )
    else:
        risk_tier = "high"
        anticoagulation_recommendation = (
            "Oral anticoagulation recommended unless contraindicated"
        )

    return CalculatorResult(
        calculator="cha2ds2-vasc",
        inputs={
            "age_years": age_years,
            "sex": sex_norm,
            "chf": chf,
            "hypertension": hypertension,
            "diabetes": diabetes,
            "stroke_tia_history": stroke_tia_history,
            "vascular_disease": vascular_disease,
        },
        output={
            "score": score,
            "risk_tier": risk_tier,
            "anticoagulation_recommendation": anticoagulation_recommendation,
        },
    )


# ─────────────────────────────────────────────────────────────────────
# MELD-Na — liver transplant priority (OPTN 2022)
# ─────────────────────────────────────────────────────────────────────


def _meld_na(
    *,
    creatinine_mg_dl: float,
    bilirubin_mg_dl: float,
    inr: float,
    sodium_mmol_l: float,
    dialysis_within_7d: bool = False,
) -> CalculatorResult:
    """MELD-Na score (OPTN 2022 revision, Kim WR et al., Hepatology 2022).

    Caps: creatinine capped at [0.8, 3.0]; bilirubin/INR floored at 1.0;
    sodium capped at [125, 137]. If dialysis within 7 days, creatinine
    is automatically set to 3.0.

    MELD(i) = 0.957·ln(creatinine) + 0.378·ln(bilirubin) + 1.120·ln(INR) + 0.643
    MELD-Na = MELD(i) + 1.32·(137 - Na) - [0.033·MELD(i)·(137 - Na)]
    """
    if creatinine_mg_dl < 0 or bilirubin_mg_dl < 0 or inr < 0:
        raise ValueError("creatinine/bilirubin/INR must be non-negative")
    if sodium_mmol_l < 0:
        raise ValueError("sodium_mmol_l must be non-negative")

    cr_eff = 3.0 if dialysis_within_7d else min(max(creatinine_mg_dl, 0.8), 3.0)
    bili = max(bilirubin_mg_dl, 1.0)
    inr_eff = max(inr, 1.0)
    na = min(max(sodium_mmol_l, 125), 137)

    # OPTN/UNOS canonical MELD formula (×10 form per OPTN calculator).
    meld_i = (
        9.57 * math.log(cr_eff)
        + 3.78 * math.log(bili)
        + 11.20 * math.log(inr_eff)
        + 6.43
    )
    meld_i = round(meld_i, 1)
    meld_i = max(meld_i, 1.0)  # OPTN floor

    delta_na = 137 - na
    meld_na = meld_i + 1.32 * delta_na - (0.033 * meld_i * delta_na)
    meld_na = round(meld_na, 1)

    # 90-day mortality tier (approximate)
    if meld_na < 15:
        mortality_tier = "low"
    elif meld_na < 20:
        mortality_tier = "moderate"
    elif meld_na < 30:
        mortality_tier = "high"
    else:
        mortality_tier = "very_high"

    warnings = []
    if dialysis_within_7d:
        warnings.append("Creatinine capped at 3.0 due to dialysis within 7 days")
    if sodium_mmol_l < 125:
        warnings.append("Sodium below 125 capped to 125 for MELD-Na calculation")
    if sodium_mmol_l > 137:
        warnings.append("Sodium above 137 capped to 137 for MELD-Na calculation")

    return CalculatorResult(
        calculator="meld-na",
        inputs={
            "creatinine_mg_dl": creatinine_mg_dl,
            "bilirubin_mg_dl": bilirubin_mg_dl,
            "inr": inr,
            "sodium_mmol_l": sodium_mmol_l,
            "dialysis_within_7d": dialysis_within_7d,
        },
        output={
            "meld_score": meld_i,
            "meld_na_score": meld_na,
            "mortality_tier_90d": mortality_tier,
        },
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────
# eGFR CKD-EPI 2021 — race-free equation (Inker LA et al., NEJM 2021)
# ─────────────────────────────────────────────────────────────────────


def _egfr_ckd_epi_2021(
    *,
    age_years: int,
    sex: str,
    serum_creatinine_mg_dl: float,
) -> CalculatorResult:
    """CKD-EPI 2021 race-free eGFR (mL/min/1.73m²).

    Reference: Inker LA et al. "New Creatinine- and Cystatin C-Based
    Equations to Estimate GFR without Race." N Engl J Med 2021;385:1737-49.

    Equation form: eGFR = 142 × min(Scr/κ, 1)^α × max(Scr/κ, 1)^(-1.200)
                        × 0.9938^Age × 1.012 [if female]
    Where κ = 0.7 (female) or 0.9 (male); α = -0.241 (female) or -0.302 (male).
    """
    if age_years <= 0:
        raise ValueError("age_years must be positive")
    if serum_creatinine_mg_dl <= 0:
        raise ValueError("serum_creatinine_mg_dl must be positive")
    sex_norm = (sex or "").lower().strip()
    if sex_norm not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female'")

    if sex_norm == "female":
        kappa = 0.7
        alpha = -0.241
        sex_multiplier = 1.012
    else:
        kappa = 0.9
        alpha = -0.302
        sex_multiplier = 1.0

    scr_over_k = serum_creatinine_mg_dl / kappa
    min_term = min(scr_over_k, 1.0) ** alpha
    max_term = max(scr_over_k, 1.0) ** (-1.200)
    egfr = 142 * min_term * max_term * (0.9938 ** age_years) * sex_multiplier
    egfr = round(egfr, 1)

    if egfr >= 90:
        ckd_stage = "G1 (normal or high)"
    elif egfr >= 60:
        ckd_stage = "G2 (mildly decreased)"
    elif egfr >= 45:
        ckd_stage = "G3a (mildly-moderately decreased)"
    elif egfr >= 30:
        ckd_stage = "G3b (moderately-severely decreased)"
    elif egfr >= 15:
        ckd_stage = "G4 (severely decreased)"
    else:
        ckd_stage = "G5 (kidney failure)"

    warnings = []
    if egfr < 60:
        warnings.append("eGFR < 60 mL/min/1.73m² — consider nephrology referral")
    if age_years >= 65:
        warnings.append("Age >= 65 — CKD-EPI 2021 may underestimate GFR in very elderly")

    return CalculatorResult(
        calculator="egfr-ckd-epi-2021",
        inputs={
            "age_years": age_years,
            "sex": sex_norm,
            "serum_creatinine_mg_dl": serum_creatinine_mg_dl,
        },
        output={
            "egfr_ml_min_1_73m2": egfr,
            "ckd_stage": ckd_stage,
        },
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────
# Wells DVT — pre-test probability of deep vein thrombosis (Wells 2003)
# ─────────────────────────────────────────────────────────────────────


def _wells_dvt(
    *,
    active_cancer: bool = False,
    paralysis_paresis_recent_immobilization: bool = False,
    recently_bedridden_postoperative: bool = False,
    tenderness_along_deep_venous_system: bool = False,
    swelling_entire_leg: bool = False,
    calf_swelling_3cm_vs_asymptomatic_side: bool = False,
    pitting_edema_symptomatic_leg: bool = False,
    collateral_superficial_veins: bool = False,
    previously_diagnosed_dvt: bool = False,
    alternative_diagnosis_at_least_as_likely: bool = False,
) -> CalculatorResult:
    """Wells DVT score (Wells et al., 2003).

    Each clinical criterion adds 1 point except 'alternative diagnosis
    at least as likely' which SUBTRACTS 1 point. Max raw score = 8.

    Tiers (original Wells interpretation):
      0       — low risk      (DVT prevalence ~5%)
      1-2     — moderate risk (~17%)
      >= 3    — high risk     (~17-53%)
    """
    score = 0
    if active_cancer:
        score += 1
    if paralysis_paresis_recent_immobilization:
        score += 1
    if recently_bedridden_postoperative:
        score += 1
    if tenderness_along_deep_venous_system:
        score += 1
    if swelling_entire_leg:
        score += 1
    if calf_swelling_3cm_vs_asymptomatic_side:
        score += 1
    if pitting_edema_symptomatic_leg:
        score += 1
    if collateral_superficial_veins:
        score += 1
    if previously_diagnosed_dvt:
        score += 1
    if alternative_diagnosis_at_least_as_likely:
        score -= 1

    if score <= 0:
        risk_tier = "low"
        recommendation = "D-dimer; if negative, DVT excluded; if positive, ultrasound"
    elif score <= 2:
        risk_tier = "moderate"
        recommendation = "D-dimer or proximal leg ultrasound"
    else:
        risk_tier = "high"
        recommendation = "Proximal leg ultrasound; anticoagulation if confirmed"

    return CalculatorResult(
        calculator="wells-dvt",
        inputs={
            "active_cancer": active_cancer,
            "paralysis_paresis_recent_immobilization": paralysis_paresis_recent_immobilization,
            "recently_bedridden_postoperative": recently_bedridden_postoperative,
            "tenderness_along_deep_venous_system": tenderness_along_deep_venous_system,
            "swelling_entire_leg": swelling_entire_leg,
            "calf_swelling_3cm_vs_asymptomatic_side": calf_swelling_3cm_vs_asymptomatic_side,
            "pitting_edema_symptomatic_leg": pitting_edema_symptomatic_leg,
            "collateral_superficial_veins": collateral_superficial_veins,
            "previously_diagnosed_dvt": previously_diagnosed_dvt,
            "alternative_diagnosis_at_least_as_likely": alternative_diagnosis_at_least_as_likely,
        },
        output={
            "score": score,
            "risk_tier": risk_tier,
            "recommendation": recommendation,
        },
    )


__all__ = [
    "MEDICAL_CALCULATOR_EXPERT_CANONICAL_KEY",
    "MEDICAL_CALCULATOR_EXPERT_NAME",
    "SUPPORTED_CALCULATORS",
    "CalculatorResult",
    "calculate",
]
