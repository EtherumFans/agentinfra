# Confidence Calibration & Selective Automation Schemas
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class RoutingTier(str, Enum):
    AUTO = "auto"
    REVIEW = "review"
    ESCALATE = "escalate"


class CodingConfidence(BaseModel):
    """Calibrated confidence for a single code."""

    code: str
    code_type: str = Field(default="diagnosis", description="diagnosis / procedure")
    raw_score: float = Field(default=0.5, ge=0.0, le=1.0)
    calibrated_score: float = Field(default=0.5, ge=0.0, le=1.0)
    inputs: dict = Field(default_factory=dict, description="Breakdown of input scores")
    calibration_rationale: str = Field(default="")


class RoutingDecision(BaseModel):
    """Automation routing decision for a single code."""

    code: str
    code_name: str = Field(default="")
    calibrated_score: float = Field(default=0.5)
    tier: RoutingTier = Field(default=RoutingTier.REVIEW)
    risk_factors: list[str] = Field(default_factory=list)
    override_reason: str = Field(default="", description="Why tier was forced up from auto-eligible")
    auto_eligible: bool = Field(default=False, description="Would have been auto but policy overrode")


class CalibrationMetrics(BaseModel):
    """Aggregate calibration quality metrics."""

    total_codes: int = 0
    auto_count: int = 0
    review_count: int = 0
    escalate_count: int = 0
    auto_accept_rate: float = 0.0
    override_count: int = Field(default=0, description="Codes that were auto-eligible but overridden")
    calibration_error_avg: float = Field(default=0.0, description="Mean |calibrated - gold_correctness|")
    false_confidence_rate: float = Field(default=0.0, description="% of high-confidence codes that were actually wrong")


class ConfidenceCalibrationResult(BaseModel):
    """Complete calibration output for a review."""

    coding_confidences: list[CodingConfidence] = Field(default_factory=list)
    routing_decisions: list[RoutingDecision] = Field(default_factory=list)
    metrics: CalibrationMetrics = Field(default_factory=CalibrationMetrics)
