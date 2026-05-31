"""Fact Extraction endpoint — extracts structured clinical facts from text"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.expert import Expert
from app.services.expert_runner import expert_runner

router = APIRouter(prefix="/api/facts", tags=["facts"])


class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw clinical text to extract facts from")
    output_language: str = Field(default="zh-CN", description="Output language code")


class ExtractResponse(BaseModel):
    facts: dict | None = None
    raw_output: str
    credits_consumed: int = 0


FACT_EXTRACTION_SYSTEM_PROMPT = """You are a Clinical Fact Extraction Agent. Your job is to extract structured clinical facts from medical text.

For the given clinical text, extract ALL of the following and output ONLY valid JSON:

{
  "chief_complaint": "Patient's main complaint / reason for visit (1 sentence)",
  "diagnosis_facts": [
    {
      "diagnosis": "Name of diagnosis or finding",
      "icd10cm_code": "Best matching ICD-10-CM code if identifiable, else empty string",
      "evidence": "Direct quote or paraphrased evidence from the text supporting this diagnosis",
      "status": "confirmed | suspected | ruled_out | history_of",
      "laterality": "left | right | bilateral | null",
      "severity": "mild | moderate | severe | null"
    }
  ],
  "procedure_facts": [
    {
      "procedure": "Name of procedure or service",
      "icd9cm3_code": "Best matching ICD-9-CM-3 code if identifiable, else empty string",
      "cpt_code": "Best matching CPT/HCPCS code if identifiable, else empty string",
      "evidence": "Direct quote or paraphrased evidence from the text",
      "status": "performed | planned | discussed"
    }
  ],
  "drug_facts": [
    {
      "drug_name": "Medication name (generic or brand)",
      "dosage": "Dose and frequency if mentioned",
      "route": "Route of administration if mentioned (oral, IV, IM, etc.)",
      "evidence": "Direct quote or paraphrased evidence from the text",
      "status": "current | prescribed | discontinued | discussed"
    }
  ],
  "lab_facts": [
    {
      "test_name": "Name of lab test or examination",
      "result": "Numerical result or finding description",
      "reference_range": "Reference/normal range if mentioned",
      "unit": "Unit of measurement if mentioned",
      "evidence": "Direct quote or paraphrased evidence from the text",
      "interpretation": "high | low | normal | abnormal | unknown"
    }
  ],
  "allergy_facts": [
    {
      "allergen": "Name of allergen (drug, food, environmental, etc.)",
      "reaction": "Description of allergic reaction",
      "severity": "mild | moderate | severe | life_threatening | unknown",
      "evidence": "Direct quote or paraphrased evidence from the text",
      "status": "active | resolved | suspected"
    }
  ],
  "social_history_facts": {
    "smoking_status": "never | former | current | unknown",
    "smoking_details": "Pack-years or description if mentioned",
    "alcohol_use": "none | occasional | moderate | heavy | unknown",
    "alcohol_details": "Description of alcohol consumption",
    "occupation": "Patient's occupation if mentioned",
    "living_situation": "Living arrangements or marital status if mentioned"
  },
  "negated_findings": [
    {
      "finding": "The finding explicitly ruled out or denied",
      "evidence": "Text showing negation"
    }
  ],
  "timing_facts": {
    "onset": "When symptoms started (if mentioned)",
    "duration": "How long the condition has persisted",
    "encounter_date": "Date of the clinical encounter (if mentioned)"
  },
  "documentation_overview": {
    "document_type": "e.g., admission_note, discharge_summary, progress_note, referral, operative_report, unknown",
    "department": "e.g., orthopedics, cardiology, general_medicine, unknown",
    "summary": "1-2 sentence summary of the clinical scenario"
  }
}

Rules:
- Only extract facts that are EXPLICITLY documented in the text. Do NOT infer or guess.
- For negated findings, include diagnoses or symptoms that were explicitly ruled out.
- If information is not mentioned, use empty string or empty array as appropriate.
- All evidence fields MUST contain the relevant text from the source.
- ICD codes: use Chinese ICD-10-CM codes (国家临床版) when possible.
- Respond in the specified output language for description fields.
"""


async def _get_or_create_fact_expert(user_id: str, db: AsyncSession) -> Expert:
    """Find or create a Fact Extraction expert for the user.

    Always updates the system_prompt to the latest version to ensure
    new fact types are supported.
    """
    # Try to find existing fact extraction expert
    result = await db.execute(
        select(Expert).where(
            Expert.name == "Fact Extraction",
            Expert.created_by == user_id,
        )
    )
    expert = result.scalar_one_or_none()
    if expert:
        if expert.system_prompt != FACT_EXTRACTION_SYSTEM_PROMPT:
            expert.system_prompt = FACT_EXTRACTION_SYSTEM_PROMPT
            await db.commit()
        return expert

    # Also check for prebuilt
    result = await db.execute(
        select(Expert).where(
            Expert.name == "Fact Extraction",
            Expert.is_prebuilt == True,
        )
    )
    expert = result.scalar_one_or_none()
    if expert:
        if expert.system_prompt != FACT_EXTRACTION_SYSTEM_PROMPT:
            expert.system_prompt = FACT_EXTRACTION_SYSTEM_PROMPT
            await db.commit()
        return expert

    # Create a new fact extraction expert
    expert = Expert(
        name="Fact Extraction",
        description="从医疗转录和笔记中提取结构化临床事实",
        system_prompt=FACT_EXTRACTION_SYSTEM_PROMPT,
        icon="Stethoscope",
        category="coding",
        is_prebuilt=False,
        is_published=False,
        created_by=user_id,
    )
    db.add(expert)
    await db.commit()
    await db.refresh(expert)
    return expert


@router.post("/extract", response_model=ExtractResponse)
async def extract_facts(
    req: ExtractRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Extract structured clinical facts from raw text"""
    try:
        expert = await _get_or_create_fact_expert(user.id, db)
        output = await expert_runner.run(
            expert=expert,
            user_input=req.text,
            conversation_history=[],
            mcp_servers=[],
        )

        # Try to parse JSON from output
        facts = None
        raw_output = output
        try:
            import json
            # Handle markdown code blocks
            text = output.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:]) if len(lines) > 1 else text
                if text.endswith("```"):
                    text = text[:-3]
            facts = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # If parsing fails, return raw output
            pass

        return ExtractResponse(
            facts=facts,
            raw_output=raw_output,
            credits_consumed=1,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fact extraction failed: {str(e)}")
