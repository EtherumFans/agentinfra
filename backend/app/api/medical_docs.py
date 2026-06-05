"""Medical Document Generation — structured Chinese clinical document templates.

Corti-style: Template Assembler maps generated sections to EHR fields.
iCoDer: template-based medical document generation from encounter data.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/medical-docs", tags=["medical-docs"])

# ── Template definitions ──

TEMPLATES = {
    "admission": {
        "name": "入院记录",
        "description": "24小时内完成的入院患者综合记录",
        "sections": [
            {"key": "chief_complaint", "label": "主诉", "required": True, "hint": "患者主要症状及持续时间"},
            {"key": "present_illness", "label": "现病史", "required": True, "hint": "发病情况、症状演变、诊疗经过"},
            {"key": "past_history", "label": "既往史", "required": True, "hint": "既往疾病、手术、过敏史"},
            {"key": "personal_history", "label": "个人史", "required": False, "hint": "出生地、职业、生活习惯"},
            {"key": "family_history", "label": "家族史", "required": False, "hint": "家族遗传病史"},
            {"key": "physical_exam", "label": "体格检查", "required": True, "hint": "T/BP/HR/系统检查阳性体征"},
            {"key": "auxiliary_exam", "label": "辅助检查", "required": False, "hint": "实验室、影像学检查结果"},
            {"key": "admission_diagnosis", "label": "入院诊断", "required": True, "hint": "ICD-10编码 + 诊断名称"},
            {"key": "treatment_plan", "label": "诊疗计划", "required": True, "hint": "检查、治疗、用药计划"},
            {"key": "doctor_signature", "label": "医师签名", "required": True, "hint": ""},
        ],
    },
    "discharge": {
        "name": "出院小结",
        "description": "患者出院时的治疗总结和随访建议",
        "sections": [
            {"key": "admission_date", "label": "入院日期", "required": True},
            {"key": "discharge_date", "label": "出院日期", "required": True},
            {"key": "admission_reason", "label": "入院情况", "required": True, "hint": "主诉及入院诊断"},
            {"key": "hospital_course", "label": "诊疗经过", "required": True, "hint": "住院期间主要检查和治疗"},
            {"key": "discharge_diagnosis", "label": "出院诊断", "required": True, "hint": "ICD-10编码 + 诊断名称"},
            {"key": "discharge_status", "label": "出院情况", "required": True, "hint": "症状体征变化，出院时状态"},
            {"key": "discharge_medication", "label": "出院医嘱", "required": True, "hint": "用药、复查、生活指导"},
            {"key": "follow_up", "label": "随访建议", "required": False, "hint": "复诊时间、科室"},
            {"key": "doctor_signature", "label": "医师签名", "required": True},
        ],
    },
    "surgery": {
        "name": "手术记录",
        "description": "手术过程详细记录",
        "sections": [
            {"key": "surgery_date", "label": "手术日期", "required": True},
            {"key": "preop_diagnosis", "label": "术前诊断", "required": True},
            {"key": "postop_diagnosis", "label": "术后诊断", "required": True},
            {"key": "surgery_name", "label": "手术名称", "required": True, "hint": "ICD-9-CM-3编码 + 手术名称"},
            {"key": "surgeon", "label": "手术者", "required": True},
            {"key": "anesthesia", "label": "麻醉方式", "required": True},
            {"key": "surgery_process", "label": "手术经过", "required": True, "hint": "体位、切口、术中所见、操作步骤"},
            {"key": "findings", "label": "术中发现", "required": True},
            {"key": "specimens", "label": "标本送检", "required": False, "hint": "病理检查项目"},
            {"key": "blood_loss", "label": "出血量", "required": False},
            {"key": "doctor_signature", "label": "术者签名", "required": True},
        ],
    },
    "progress_note": {
        "name": "病程记录",
        "description": "每日病程记录",
        "sections": [
            {"key": "record_date", "label": "记录日期", "required": True},
            {"key": "subjective", "label": "主观资料", "required": True, "hint": "患者主诉、症状变化"},
            {"key": "objective", "label": "客观资料", "required": True, "hint": "体征、检查结果"},
            {"key": "assessment", "label": "评估", "required": True, "hint": "病情分析、诊断调整"},
            {"key": "plan", "label": "计划", "required": True, "hint": "诊疗计划调整"},
            {"key": "doctor_signature", "label": "医师签名", "required": True},
        ],
    },
    "consultation": {
        "name": "会诊记录",
        "description": "科室间会诊申请与意见",
        "sections": [
            {"key": "consult_date", "label": "会诊日期", "required": True},
            {"key": "request_dept", "label": "申请科室", "required": True},
            {"key": "consult_dept", "label": "会诊科室", "required": True},
            {"key": "reason", "label": "会诊原因", "required": True},
            {"key": "patient_summary", "label": "病情摘要", "required": True},
            {"key": "consult_opinion", "label": "会诊意见", "required": True, "hint": "诊断、治疗建议"},
            {"key": "consult_doctor", "label": "会诊医师", "required": True},
        ],
    },
}


class GenerateRequest(BaseModel):
    template_key: str = "admission"
    encounter_data: dict = {}
    output_language: str = "zh-CN"


class GenerateResponse(BaseModel):
    template_key: str
    template_name: str
    sections: list[dict]
    raw_output: str = ""


@router.get("/templates")
async def list_templates():
    """List all available medical document templates."""
    return {
        "templates": [
            {"key": k, "name": v["name"], "description": v["description"],
             "section_count": len(v["sections"])}
            for k, v in TEMPLATES.items()
        ],
        "total": len(TEMPLATES),
    }


@router.get("/templates/{template_key}")
async def get_template(template_key: str):
    """Get a specific template with all sections."""
    if template_key not in TEMPLATES:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_key}")
    tpl = TEMPLATES[template_key]
    return {"key": template_key, "name": tpl["name"], "description": tpl["description"], "sections": tpl["sections"]}


@router.post("/generate", response_model=GenerateResponse)
async def generate_document(body: GenerateRequest):
    """Generate a medical document from encounter data and template."""
    if body.template_key not in TEMPLATES:
        raise HTTPException(status_code=400, detail=f"Unknown template: {body.template_key}")

    tpl = TEMPLATES[body.template_key]
    encounter = body.encounter_data

    # Build structured prompt for LLM
    sections_desc = "\n".join(
        f"- {s['key']}: {s['label']}" + (f" ({s['hint']})" if s.get('hint') else "")
        + (" [必需]" if s['required'] else "")
        for s in tpl["sections"]
    )

    prompt = f"""请根据以下病历信息，生成一份{tpl['name']}。

模板结构:
{sections_desc}

病历信息:
{encounter.get('raw_text', str(encounter))}

请按模板结构的每个字段，从病历信息中提取或推断相应的内容。无法确定的内容标记为"待补充"。
输出JSON格式: {{"section_key": "内容", ...}}  """

    # Try LLM generation, fallback to extraction from encounter data
    try:
        from app.services.llm_service import llm_service
        result = await llm_service.generate_text(prompt)
        import json
        generated = json.loads(result) if isinstance(result, str) else result
    except Exception:
        # Fallback: extract from encounter data keys + LLM call via text-gen
        generated = {}
        try:
            from app.services.llm_service import llm_service
            text_result = await llm_service.generate_text(
                f"基于以下病历生成{tpl['name']}的各字段内容，JSON格式：\\n" + str(encounter)[:2000]
            )
            generated = json.loads(text_result) if isinstance(text_result, str) else {}
        except:
            pass
        if not generated:
            for s in tpl["sections"]:
                key = s["key"]
                generated[key] = encounter.get(key, encounter.get(s["label"], "待补充"))

    # Format sections with the generated/fallback data
    sections = []
    for s in tpl["sections"]:
        key = s["key"]
        value = generated.get(key, "待补充")
        sections.append({
            "key": key,
            "label": s["label"],
            "value": str(value),
            "required": s["required"],
            "filled": str(value) != "待补充",
        })

    return GenerateResponse(
        template_key=body.template_key,
        template_name=tpl["name"],
        sections=sections,
        raw_output=str(generated),
    )
