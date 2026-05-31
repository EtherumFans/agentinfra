"""Text Generation endpoints using LLM service"""
from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services.llm_service import llm_service

router = APIRouter(prefix="/api/text-gen", tags=["text-generation"])


class GenerateRequest(BaseModel):
    text: str = Field(default="", description="Input text / prompt for text generation")
    style: str = Field(default="discharge_summary", description="Generation style")
    template: str = Field(default="", description="Template name (alternative to style)")
    language: str = Field(default="zh-CN", description="Output language")
    context: dict | None = Field(default=None, description="Context for template-based generation")
    max_tokens: int = Field(default=2048, ge=64, le=4096)
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)


class GenerateResponse(BaseModel):
    output: str
    model: str
    usage: dict | None = None


class TemplateInfo(BaseModel):
    key: str
    name: str
    desc: str
    category: str
    sample: str


class TemplateListResponse(BaseModel):
    templates: List[TemplateInfo]


# Default templates — can be replaced with DB-backed storage in the future
DEFAULT_TEMPLATES = [
    {"key": "discharge_summary", "name": "出院小结", "desc": "标准出院小结，包含入院情况、诊疗经过、出院诊断、出院医嘱", "category": "住院", "sample": "患者，男，65岁，因\"反复胸闷、心悸3年，加重1周\"入院。"},
    {"key": "admission_record", "name": "入院记录", "desc": "完整入院记录，含主诉、现病史、既往史、体格检查、初步诊断", "category": "住院", "sample": "主诉：腰痛4个月余。"},
    {"key": "progress_note", "name": "日常病程记录", "desc": "SOAP格式病程记录：主观、客观、评估、计划", "category": "住院", "sample": "S（主观）：患者诉腰痛较前缓解。"},
    {"key": "preop_discussion", "name": "术前讨论记录", "desc": "术前讨论：手术指征、手术方案、风险评估、替代方案", "category": "手术", "sample": "讨论时间：2026年5月9日"},
    {"key": "operation_record", "name": "手术记录", "desc": "手术经过、术中所见、标本送检、术中特殊情况", "category": "手术", "sample": "手术名称：T7、T9、T12、L2经皮穿刺脊柱后凸成形术"},
    {"key": "referral_letter", "name": "转诊信", "desc": "转诊至其他科室或医院，含转诊原因、已有检查、治疗建议", "category": "门诊", "sample": "转诊科室：心血管内科"},
    {"key": "outpatient_note", "name": "门诊就诊记录", "desc": "通用门诊就诊记录，含主诉、查体、诊断、处理意见", "category": "门诊", "sample": "主诉：咳嗽、咳痰3天。"},
    {"key": "emergency_note", "name": "急诊记录", "desc": "急诊就诊记录：来院方式、生命体征、急诊处理、离院方式", "category": "急诊", "sample": "来院方式：120急救车送入。"},
    {"key": "consultation_record", "name": "会诊记录", "desc": "科间会诊申请与意见：会诊目的、病史摘要、会诊意见", "category": "住院", "sample": "会诊申请科室：骨科 申请会诊科室：心内科"},
    {"key": "nursing_note", "name": "护理记录", "desc": "护理观察记录：生命体征、护理措施、病情变化、交班要点", "category": "护理", "sample": "生命体征：T 36.5°C，P 78次/分，R 18次/分。"},
    {"key": "patient_summary", "name": "患者摘要", "desc": "面向非医学专业人士的患者就诊摘要，通俗易懂", "category": "通用", "sample": "就诊日期：2026年5月9日"},
]


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(user: User = Depends(get_current_user)):
    """Return available text generation templates dynamically.

    In the future, templates can be sourced from a database table
    to allow runtime management without code changes.
    """
    return TemplateListResponse(templates=[TemplateInfo(**t) for t in DEFAULT_TEMPLATES])


STYLE_PROMPTS = {
    "discharge_summary": "Based on the following clinical notes, generate a professional discharge summary in Chinese medical format:",
    "progress_note": "Based on the following clinical information, generate a structured daily progress note in Chinese medical format:",
    "referral_letter": "Based on the following clinical information, generate a formal referral letter between departments in Chinese medical format:",
    "system_prompt": "",
    "general": "",
}

SYSTEM_PROMPT_GENERATOR = """你是一个 AI 智能体的 System Prompt 设计专家。根据用户提供的智能体信息，生成一个专业、结构化的 System Prompt。

要求：
1. 用中文编写
2. 明确智能体的角色和专业领域
3. 列出智能体的核心能力和任务
4. 定义输出格式和行为规范
5. 包含必要的注意事项和限制
6. 长度控制在 200-500 字

请直接输出 System Prompt 文本，不要包含解释或前缀。"""


@router.post("/generate", response_model=GenerateResponse)
async def generate_text(
    req: GenerateRequest,
    user: User = Depends(get_current_user),
):
    """Generate text using LLM, with optional template-based context"""
    style = req.template or req.style
    system_prompt = STYLE_PROMPTS.get(style, STYLE_PROMPTS["general"])

    # Build user message
    if style == "system_prompt" and req.context:
        context = req.context
        user_text = f"""请为以下智能体生成 System Prompt：

智能体名称：{context.get('agent_name', '')}
描述：{context.get('description', '未提供')}
类别：{context.get('category', '未分类')}

请生成一个专业的中文 System Prompt。"""
    elif req.text:
        user_text = req.text
    else:
        user_text = "请生成文本。"

    if system_prompt:
        system_msg = system_prompt + "\nRespond in Chinese medical language."
    else:
        system_msg = SYSTEM_PROMPT_GENERATOR if style == "system_prompt" else "You are a medical documentation assistant. Generate professional clinical text."

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_text},
    ]
    result = await llm_service.chat(
        messages=messages,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    content = result.get("content", "") if isinstance(result, dict) else ""
    usage = result.get("usage", None) if isinstance(result, dict) else None
    return GenerateResponse(
        output=content,
        model=llm_service.model if hasattr(llm_service, 'model') else "deepseek-chat",
        usage=usage,
    )
