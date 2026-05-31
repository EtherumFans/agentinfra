# iCoDer - Encounter Schemas
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class DocumentInput(BaseModel):
    doc_type: str = Field(..., description="入院记录/出院记录/手术记录/检查报告/病程记录")
    title: str = ""
    content: str = Field(..., min_length=10)


class ExistingCode(BaseModel):
    code: str
    name: str = ""


class EncounterCreate(BaseModel):
    patient_id: str = Field(..., description="脱敏ID")
    department: str = Field(..., min_length=1)
    admission_time: Optional[str] = None
    discharge_time: Optional[str] = None
    admission_reason: Optional[str] = None
    documents: List[DocumentInput] = []
    existing_diagnosis_codes: List[ExistingCode] = []
    existing_procedure_codes: List[ExistingCode] = []


class EncounterTextInput(BaseModel):
    """Simplified input: paste raw text, let system parse."""
    raw_text: str = Field(..., min_length=20, description="完整病历文本或出院小结")
    department: str = "内科"
    patient_id: str = "ANONYMOUS"
    existing_diagnosis_codes: List[ExistingCode] = []
    existing_procedure_codes: List[ExistingCode] = []


class DocumentResponse(BaseModel):
    id: str
    doc_type: str
    title: str
    content: str
    doc_order: int
    created_at: datetime
    model_config = {"from_attributes": True}


class EncounterResponse(BaseModel):
    id: str
    encounter_id: str
    patient_id: str
    department: str
    admission_time: Optional[datetime] = None
    discharge_time: Optional[datetime] = None
    admission_reason: Optional[str] = None
    existing_diagnosis_codes: Optional[list] = None
    existing_procedure_codes: Optional[list] = None
    status: str
    document_count: int = 0
    documents: list = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

    @classmethod
    def from_encounter(cls, encounter, documents: list = None):
        docs = documents or []
        return cls(
            id=encounter.id,
            encounter_id=encounter.encounter_id,
            patient_id=encounter.patient_id,
            department=encounter.department,
            admission_time=encounter.admission_time,
            discharge_time=encounter.discharge_time,
            admission_reason=encounter.admission_reason,
            existing_diagnosis_codes=encounter.existing_diagnosis_codes,
            existing_procedure_codes=encounter.existing_procedure_codes,
            status=encounter.status,
            document_count=len(docs),
            documents=[{"id": d.id, "doc_type": d.doc_type, "title": d.title, "content": d.content, "doc_order": d.doc_order} for d in docs],
            created_at=encounter.created_at,
            updated_at=encounter.updated_at,
        )


class EncounterListResponse(BaseModel):
    items: List[EncounterResponse]
    total: int
    page: int
    page_size: int
