# Clinical Timeline Schema — single-case temporal event reconstruction
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ClinicalEvent(BaseModel):
    """A single clinical event placed on the timeline."""

    event_type: str = Field(
        description="Event category: symptom_onset, diagnosis, surgery, chemotherapy, "
                    "lab_test, imaging, admission, discharge, medication, complication, "
                    "radiotherapy, pathology, consultation, transfer, other"
    )
    description: str = Field(description="Human-readable event description in Chinese")
    timestamp: Optional[datetime] = Field(default=None, description="Absolute datetime if resolvable")
    relative_time: Optional[str] = Field(default=None, description="Relative time expression, e.g. '术后3月余', '入院第2天'")
    source_document: str = Field(description="Which document type this event came from")
    source_text: str = Field(description="Exact text excerpt from the source document")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence score 0–1")
    anchor: Optional[str] = Field(default=None, description="Which anchor point this event is relative to")


class AnchorPoints(BaseModel):
    """Key temporal anchors extracted from the medical record."""

    admission_date: Optional[datetime] = Field(default=None, description="入院日期")
    discharge_date: Optional[datetime] = Field(default=None, description="出院日期")
    surgery_date: Optional[datetime] = Field(default=None, description="手术日期 (most recent)")
    diagnosis_confirmed_date: Optional[datetime] = Field(default=None, description="确诊日期")
    other_anchors: dict = Field(default_factory=dict, description="Additional anchor points, e.g. {'chemotherapy_cycle1': '2025-02-18'}")


class ClinicalTimeline(BaseModel):
    """Complete clinical timeline for a single encounter."""

    encounter_id: str = Field(description="Encounter ID")
    anchor_points: AnchorPoints = Field(default_factory=AnchorPoints)
    events: list[ClinicalEvent] = Field(default_factory=list, description="Chronologically ordered clinical events")
    unresolved_events: list[ClinicalEvent] = Field(
        default_factory=list,
        description="Events that could not be placed on the timeline due to missing temporal info"
    )
    timeline_summary: str = Field(default="", description="Natural language summary of the clinical course")
