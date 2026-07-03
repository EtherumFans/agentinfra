# DEPRECATED (P1.3 Stage 5, 2026-07-02) — Phase 2 合并到 v2_tools_facts.py. 见 docs/architecture/MAINLINE_VS_LEGACY.md §3.3.
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


FACT_EXTRACTION_SYSTEM_PROMPT = """你是临床事实提取专家。你的任务是从病历文本中提取结构化临床事实。

对给定的临床文本，提取以下所有内容，仅输出有效的 JSON：

{
  "chief_complaint": "患者主诉/就诊原因（一句话）",
  "diagnosis_facts": [
    {
      "diagnosis": "诊断或发现名称",
      "icd10cm_code": "如可识别的最佳 ICD-10-CM 编码，否则为空字符串",
      "evidence": "来自文本的直接引用或转述证据",
      "status": "已确诊 | 疑似 | 已排除 | 既往史",
      "laterality": "左侧 | 右侧 | 双侧 | 无",
      "severity": "轻度 | 中度 | 重度 | 无"
    }
  ],
  "procedure_facts": [
    {
      "procedure": "手术或操作名称",
      "icd9cm3_code": "如可识别的最佳 ICD-9-CM-3 编码，否则为空字符串",
      "evidence": "来自文本的直接引用或转述证据",
      "status": "已执行 | 计划中 | 已讨论"
    }
  ],
  "drug_facts": [
    {
      "drug_name": "药物名称（通用名或商品名）",
      "dosage": "剂量和频率（如有提及）",
      "route": "给药途径（口服、静脉、肌注等）",
      "evidence": "来自文本的直接引用或转述证据",
      "status": "正在使用 | 已开具 | 已停药 | 已讨论"
    }
  ],
  "lab_facts": [
    {
      "test_name": "化验或检查名称",
      "result": "数值结果或发现描述",
      "reference_range": "参考范围（如有提及）",
      "unit": "计量单位（如有提及）",
      "evidence": "来自文本的直接引用或转述证据",
      "interpretation": "偏高 | 偏低 | 正常 | 异常 | 未知"
    }
  ],
  "allergy_facts": [
    {
      "allergen": "过敏原名称（药物、食物、环境等）",
      "reaction": "过敏反应描述",
      "severity": "轻度 | 中度 | 重度 | 危及生命 | 未知",
      "evidence": "来自文本的直接引用或转述证据",
      "status": "现存 | 已消退 | 疑似"
    }
  ],
  "social_history_facts": {
    "smoking_status": "从不 | 曾吸烟 | 正在吸烟 | 未知",
    "smoking_details": "包年数或吸烟描述（如有提及）",
    "alcohol_use": "不饮酒 | 偶尔 | 中度 | 大量 | 未知",
    "alcohol_details": "饮酒情况描述",
    "occupation": "患者职业（如有提及）",
    "living_situation": "居住状况或婚姻状况（如有提及）"
  },
  "negated_findings": [
    {
      "finding": "被明确排除或否认的发现",
      "evidence": "显示否定的文本"
    }
  ],
  "timing_facts": {
    "onset": "症状开始时间（如有提及）",
    "duration": "持续时间",
    "encounter_date": "就诊日期（如有提及）"
  },
  "documentation_overview": {
    "document_type": "例如：入院记录、出院小结、病程记录、转诊单、手术报告、未知",
    "department": "例如：骨科、心内科、普内科、未知",
    "summary": "临床场景的1-2句话总结"
  }
}

规则:
- 只提取文本中明确记录的事实。不得推断或猜测。
- 对于否定发现，包含被明确排除的诊断或症状。
- 如信息未提及，使用空字符串或空数组。
- 所有 evidence 字段必须包含原文中的相关文本。
- ICD 编码：尽可能使用中国 ICD-10-CM 编码（国家临床版）。
- 描述字段使用中文输出。
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
