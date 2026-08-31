"""Fail-closed client for the development-only China DRG/DIP risk review."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, TypedDict, cast

from ..client import iCoDerClient
from ..request_options import RequestOptions


class DrgDipGovernance(TypedDict):
    asset_id: Literal["cn.drg_dip.risk_heuristics"]
    version: Literal["1.0.0-development"]
    asset_type: Literal["risk_review_rule_pack"]
    jurisdiction: Literal["CN_GENERIC_DEVELOPMENT"]
    authority_status: Literal["experimental_unverified"]
    license_status: Literal["external_review_required"]
    effective_from: str | None
    effective_to: str | None
    billing_authoritative: Literal[False]
    manual_review_required: Literal[True]
    use_restriction: Literal[
        "development_risk_review_only_not_for_grouping_payment_or_settlement"
    ]


class _DrgDipCodeRequired(TypedDict):
    code: str


class DrgDipCode(_DrgDipCodeRequired, total=False):
    name: str
    description: str
    confidence: float


class DrgDipRisk(TypedDict):
    rule_id: str
    severity: str
    risk_type: str
    message: str
    suggestion: str


class DrgDipImpact(TypedDict):
    """Experimental candidate fields; all numeric payment fields must be zero."""

    predicted_drg: str
    drg_name: str
    mdc: str
    mdc_name: str
    adrg: str
    cc_level: str
    grouping_method: str
    coverage: bool
    payment_weight: float
    payment_estimate_yuan: float
    billing_authoritative: Literal[False]
    result_status: Literal["experimental_candidate"]


class DipImpact(TypedDict):
    dip_score: float
    dip_score_ceiling: float
    payment_estimate_yuan: float
    note: str
    billing_authoritative: Literal[False]


class DrgDipRule(TypedDict):
    id: str
    name: str
    severity: str
    category: str
    description: str


class DrgDipRulesResponse(TypedDict):
    rule_set: Literal["drg_dip"]
    total: int
    rules: list[DrgDipRule]
    governance: DrgDipGovernance


class DrgDipAnalyzeResponse(TypedDict):
    primary_diagnosis: dict[str, Any]
    secondary_diagnoses: list[dict[str, Any]]
    procedures: list[dict[str, Any]]
    drg_impact: DrgDipImpact
    dip_impact: DipImpact
    risks: list[DrgDipRisk]
    recommendations: list[str]
    quality_flags: dict[str, Any]
    governance: DrgDipGovernance
    manual_review_required: Literal[True]
    review_conclusion: Literal["WARNING", "FAIL"]
    confidence: float
    notes: str
    provider: str
    model: str
    is_mock: bool
    error: Literal[False]
    error_reason: Literal[""]


class DrgDipRiskReviewResource:
    """Development risk review; never an official grouper or payment API."""

    def __init__(self, client: iCoDerClient):
        self._client = client

    def get_governance(
        self, request_options: RequestOptions | None = None,
    ) -> DrgDipGovernance:
        response = self._client.get(
            "/api/drg/governance", request_options=request_options,
        )
        response.raise_for_status()
        payload = response.json()
        _assert_development_governance(payload)
        return cast(DrgDipGovernance, payload)

    def list_rules(
        self, request_options: RequestOptions | None = None,
    ) -> DrgDipRulesResponse:
        response = self._client.get(
            "/api/drg/rules", request_options=request_options,
        )
        response.raise_for_status()
        payload = response.json()
        _assert_development_governance(payload.get("governance"))
        return cast(DrgDipRulesResponse, payload)

    def analyze(
        self,
        primary_diagnosis: DrgDipCode,
        *,
        secondary_diagnoses: Sequence[DrgDipCode] = (),
        procedures: Sequence[DrgDipCode] = (),
        patient_gender: Literal["M", "F", ""] = "",
        patient_age: int | None = None,
        request_options: RequestOptions | None = None,
    ) -> DrgDipAnalyzeResponse:
        _validate_code(primary_diagnosis, "primary_diagnosis")
        for index, item in enumerate(secondary_diagnoses):
            _validate_code(item, f"secondary_diagnoses[{index}]")
        for index, item in enumerate(procedures):
            _validate_code(item, f"procedures[{index}]")
        if patient_gender not in ("M", "F", ""):
            raise ValueError("patient_gender must be M, F, or empty")
        if patient_age is not None and (
            not isinstance(patient_age, int)
            or isinstance(patient_age, bool)
            or patient_age < 0
            or patient_age > 150
        ):
            raise ValueError("patient_age must be an integer between 0 and 150")

        response = self._client.post(
            "/api/drg/analyze",
            json={
                "primary_diagnosis": dict(primary_diagnosis),
                "secondary_diagnoses": [dict(item) for item in secondary_diagnoses],
                "procedures": [dict(item) for item in procedures],
                "patient_gender": patient_gender,
                "patient_age": patient_age,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        payload = response.json()
        _assert_development_analysis(payload)
        return cast(DrgDipAnalyzeResponse, payload)


def _assert_development_governance(payload: Any) -> None:
    if not isinstance(payload, dict) or any((
        payload.get("asset_id") != "cn.drg_dip.risk_heuristics",
        payload.get("version") != "1.0.0-development",
        payload.get("jurisdiction") != "CN_GENERIC_DEVELOPMENT",
        payload.get("authority_status") != "experimental_unverified",
        payload.get("license_status") != "external_review_required",
        payload.get("billing_authoritative") is not False,
        payload.get("manual_review_required") is not True,
        payload.get("use_restriction")
        != "development_risk_review_only_not_for_grouping_payment_or_settlement",
    )):
        raise ValueError(
            "DRG/DIP governance response is not a development-only, "
            "manual-review contract"
        )


def _assert_development_analysis(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("DRG/DIP response is not an object")
    _assert_development_governance(payload.get("governance"))
    drg = payload.get("drg_impact")
    dip = payload.get("dip_impact")
    if not isinstance(drg, dict) or not isinstance(dip, dict) or any((
        payload.get("manual_review_required") is not True,
        payload.get("error") is not False,
        payload.get("review_conclusion") not in ("WARNING", "FAIL"),
        drg.get("billing_authoritative") is not False,
        drg.get("result_status") != "experimental_candidate",
        drg.get("payment_weight") != 0,
        drg.get("payment_estimate_yuan") != 0,
        dip.get("billing_authoritative") is not False,
        dip.get("dip_score") != 0,
        dip.get("dip_score_ceiling") != 0,
        dip.get("payment_estimate_yuan") != 0,
    )):
        raise ValueError(
            "DRG/DIP response violated the non-authoritative, non-payment contract"
        )


def _validate_code(item: DrgDipCode, field: str) -> None:
    if not isinstance(item, dict):
        raise TypeError(f"{field} must be an object")
    code = item.get("code")
    if (
        not isinstance(code, str)
        or not code.strip()
        or len(code) > 64
        or any(ord(char) < 32 or ord(char) == 127 for char in code)
    ):
        raise ValueError(
            f"{field}.code must contain between 1 and 64 printable characters"
        )
    confidence = item.get("confidence")
    if confidence is not None and (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or confidence < 0
        or confidence > 1
    ):
        raise ValueError(f"{field}.confidence must be between 0 and 1")
