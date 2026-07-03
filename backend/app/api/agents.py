# DEPRECATED (P1.3 Stage 5, 2026-07-02) — Legacy API. Phase 2 migrate 到 /rest/v1/agent_definitions (Corti 风格). 见 docs/architecture/MAINLINE_VS_LEGACY.md §3.3.
"""Agent CRUD API — manage Agents as first-class backend entities.

iCoDer Agentic Framework equivalent: "Agent is a backend entity that composes
multiple Experts. Users create/configure Agents, which then orchestrate
Experts to complete tasks."
"""
import json
import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.models.user import User
from app.models.agent import Agent
from app.models.organization import Organization
# Phase 2.1-A (2026-07-02): legacy agent_runner stub removed.
# The `_LegacyAgentRunnerStub` symbol (Phase 2-B) is gone — any caller that
# still hits the legacy `agent_runner.run/stream` path now gets a clear 410
# Gone redirect to the A2A mainline. The new execution path lives in
# `app.icoder.agent_runtime.orchestrator.InboundHandler` (mounted via
# `mount_a2a` in app/main.py).
from app.services.agent_analytics import agent_analytics

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ---- Schemas ----

class AgentExpertBinding(BaseModel):
    expert_id: str
    expert_name: str = ""

class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    system_prompt: str = ""
    icon: str = "Bot"
    category: str = "general"
    expert_ids: list[str] = []
    default_expert_id: str = ""
    a2a_enabled: bool = False
    config: dict | None = None

class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    icon: str | None = None
    category: str | None = None
    expert_ids: list[str] | None = None
    default_expert_id: str | None = None
    a2a_enabled: bool | None = None
    config: dict | None = None
    status: str | None = None
    version: str | None = None


async def _agent_to_dict(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "icon": agent.icon,
        "category": agent.category,
        "expert_ids": agent.expert_ids or [],
        "default_expert_id": agent.default_expert_id or "",
        "a2a_enabled": agent.a2a_enabled,
        "config": agent.config or {},
        "is_prebuilt": agent.is_prebuilt,
        "is_published": agent.is_published,
        "version": agent.version or "1.0.0",
        "status": agent.status or "draft",
        "created_by": agent.created_by,
        "usage_count": agent.usage_count or 0,
        "created_at": agent.created_at.isoformat(),
        "updated_at": agent.updated_at.isoformat(),
    }


# ---- Endpoints ----

@router.get("")
async def list_agents(
    category: str = "",
    search: str = "",
    type: str = Query("all", enum=["all", "prebuilt", "custom"]),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List agents with optional filter/search."""
    q = select(Agent).where(Agent.organization_id == org.id)
    if type == "prebuilt":
        q = q.where(Agent.is_prebuilt == True)
    elif type == "custom":
        q = q.where(Agent.is_prebuilt == False)
    if category:
        q = q.where(Agent.category == category)
    if search:
        q = q.where(or_(
            Agent.name.ilike(f"%{search}%"),
            Agent.description.ilike(f"%{search}%"),
        ))
    q = q.order_by(Agent.is_prebuilt.desc(), Agent.usage_count.desc())
    result = await db.execute(q)
    agents = result.scalars().all()
    return {"agents": [await _agent_to_dict(a) for a in agents], "total": len(agents)}


@router.post("")
async def create_agent(
    body: AgentCreate,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom agent."""
    agent = Agent(
        organization_id=org.id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        icon=body.icon,
        category=body.category,
        expert_ids=body.expert_ids,
        default_expert_id=body.default_expert_id or (body.expert_ids[0] if body.expert_ids else ""),
        a2a_enabled=body.a2a_enabled,
        config=body.config or {},
        is_prebuilt=False,
        is_published=True,
        created_by=user.id,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return await _agent_to_dict(agent)


class AgentCloneRequest(BaseModel):
    name: str | None = None
    description: str | None = None

@router.post("/{agent_id}/clone")
async def clone_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    body: AgentCloneRequest | None = None,
):
    """Clone a prebuilt agent or template into a user-owned custom agent."""
    name_override = body.name if body else None
    description_override = body.description if body else None

    # 1. Try cloning from a DB Agent (prebuilt or custom)
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    source = result.scalar_one_or_none()
    if source:
        cloned = Agent(
            organization_id=org.id,
            name=name_override or f"{source.name} (Copy)",
            description=description_override or source.description,
            system_prompt=source.system_prompt,
            icon=source.icon,
            category=source.category,
            expert_ids=source.expert_ids or [],
            default_expert_id=source.default_expert_id or "",
            a2a_enabled=source.a2a_enabled,
            config=source.config or {},
            is_prebuilt=False,
            is_published=False,
            created_by=user.id,
            status="draft",
            version="1.0.0",
            usage_count=0,
        )
        db.add(cloned)
        await db.commit()
        await db.refresh(cloned)
        return await _agent_to_dict(cloned)

    # 2. Try cloning from a hardcoded template
    template = next((t for t in AGENT_TEMPLATES if t["id"] == agent_id), None)
    if not template:
        raise HTTPException(status_code=404, detail="Agent or template not found")

    cloned = Agent(
        organization_id=org.id,
        name=name_override or f"{template['title']} (Copy)",
        description=description_override or template["description"],
        system_prompt=template["system_prompt"],
        icon=template["icon"],
        category=template["category"],
        expert_ids=template.get("expert_ids", []),
        default_expert_id=template.get("expert_ids", [""])[0] if template.get("expert_ids") else "",
        a2a_enabled=False,
        config=template.get("config", {}),
        is_prebuilt=False,
        is_published=False,
        created_by=user.id,
        status="draft",
        version="1.0.0",
        usage_count=0,
    )
    db.add(cloned)
    await db.commit()
    await db.refresh(cloned)
    return await _agent_to_dict(cloned)


@router.get("/categories")
async def agent_categories(db: AsyncSession = Depends(get_db)):
    """List distinct agent categories."""
    from sqlalchemy import func
    result = await db.execute(
        select(Agent.category, func.count(Agent.id)).group_by(Agent.category)
    )
    rows = result.all()
    return {"categories": [{"name": r[0], "count": r[1]} for r in rows]}


@router.get("/templates")
async def get_agent_templates():
    """Get hardcoded list of agent templates (20 iCoDer-style templates)."""
    return {"templates": AGENT_TEMPLATES}


@router.get("/templates/{template_id}/download")
async def download_template_pack(template_id: str):
    """Download a template as a .icoder-agent package file."""
    from fastapi.responses import Response
    from icoder_runtime.agent_pack import pack_from_template

    template = next((t for t in AGENT_TEMPLATES if t["id"] == template_id), None)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    pack = pack_from_template(template)
    import json
    content = json.dumps(pack, ensure_ascii=False, indent=2)

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{template_id}-v1.0.0.icoder-agent"',
        },
    )


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get agent detail."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.organization_id == org.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await _agent_to_dict(agent)


@router.put("/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentUpdate,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.organization_id == org.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    for field in ["name", "description", "system_prompt", "icon", "category",
                   "expert_ids", "default_expert_id", "a2a_enabled", "config"]:
        val = getattr(body, field, None)
        if val is not None:
            setattr(agent, field, val)

    await db.commit()
    await db.refresh(agent)
    return await _agent_to_dict(agent)


@router.get("/{agent_id}/share")
async def get_agent_share_link(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generate a shareable link for an agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    link = f"/ai-studio/agents/{agent.id}"
    return {"share_url": link, "agent_name": agent.name, "agent_id": agent.id}


@router.post("/{agent_id}/version")
async def bump_agent_version(
    agent_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bump agent version (patch increment)."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    parts = (agent.version or "1.0.0").split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    agent.version = ".".join(parts)
    await db.commit()
    await db.refresh(agent)
    return await _agent_to_dict(agent)


# ---- Thread State (governed memory) ----
from app.services.thread_state import thread_manager

@router.post("/{agent_id}/threads")
async def create_thread(
    agent_id: str,
    user: User = Depends(get_current_user),
):
    """Create a new conversation thread for an agent."""
    thread = thread_manager.create(agent_id, user.id)
    return thread.to_dict()


@router.get("/{agent_id}/threads")
async def list_threads(
    agent_id: str,
    user: User = Depends(get_current_user),
):
    """List all threads for an agent."""
    return {"threads": thread_manager.list_by_agent(agent_id)}


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
):
    """Get a thread by ID."""
    thread = thread_manager.get(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread.to_dict()


@router.post("/threads/{thread_id}/snapshot")
async def snapshot_thread(
    thread_id: str,
    label: str = "",
):
    """Save a snapshot of the current thread state."""
    thread = thread_manager.get(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    snap = thread.save_snapshot(label)
    return {"thread_id": thread_id, "snapshot": snap}


@router.post("/threads/{thread_id}/restore")
async def restore_thread(
    thread_id: str,
    index: int = -1,
):
    """Restore thread state from a snapshot."""
    thread = thread_manager.get(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    ok = thread.restore_snapshot(index)
    return {"thread_id": thread_id, "restored": ok, "state": thread.to_dict()}


@router.get("/threads/stats")
async def thread_stats():
    """Get thread state manager statistics."""
    return thread_manager.stats()


# ---- Agent Execution (multi-Expert orchestration) ----

class AgentRunRequest(BaseModel):
    input: str = Field(..., min_length=1)
    conversation_history: list[dict] = []

@router.post("/{agent_id}/run")
async def run_agent(
    agent_id: str,
    body: AgentRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute an Agent with multi-Expert orchestration.

    Phase 2.1-A (2026-07-02): DEPRECATED for execution. The legacy
    ``agent_runner.run()`` path is removed; the new PlatformRuntime also
    no longer wraps an AgentRunner stub. Both paths now raise/redirect.

    New execution path: POST to the A2A endpoints exposed via
    ``mount_a2a`` in ``app/main.py`` (e.g. ``/a2a/v1/...``) — they route
    through the new ``InboundHandler`` orchestrator.

    This endpoint is retained for backward path-discovery: it returns
    410 Gone with a redirect message instead of a silent 500.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy `/api/agents/{id}/run` execution path removed in "
            "Phase 2.1-A. Use the A2A mainline: POST to /a2a/v1/... "
            "(exposed via `mount_a2a` in app/main.py) which routes through "
            "the new InboundHandler orchestrator."
        ),
    )


@router.post("/{agent_id}/stream")
async def stream_agent(
    agent_id: str,
    body: AgentRunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream Agent response via Server-Sent Events.

    Phase 2.1-A (2026-07-02): DEPRECATED. Returns 410 Gone — see
    ``run_agent`` above for the migration path.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy `/api/agents/{id}/stream` execution path removed in "
            "Phase 2.1-A. Use the A2A mainline (POST /a2a/v1/...)."
        ),
    )


# ---- Analytics ----

@router.get("/stats/overall")
async def get_overall_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregate stats across all Agents."""
    return await agent_analytics.get_overall_stats(db)


@router.get("/{agent_id}/stats")
async def get_agent_stats(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get usage stats for a specific Agent."""
    return await agent_analytics.get_agent_stats(agent_id, db)


# ---- Agent Templates ----

AGENT_TEMPLATES = [
    {
        "id": "icd10-navigator",
        "title": "ICD-10 Index Navigator Agent",
        "description": "从临床术语遍历ICD-10字母索引，为编码员审核提供候选编码",
        "category": "编码",
        "icon": "BookOpenText",
        "expert_ids": ["ICD-10 索引导航专家"],
        "config": {},
        "system_prompt": "<role>\nYou are an ICD-10 index navigation specialist. Your role is to help medical coders navigate the ICD-10 alphabetic index, locate candidate codes for clinical terms, and identify the correct diagnosis codes based on documentation evidence.\n</role>\n\n<output_format>\nFor each clinical term provided:\n1. List candidate ICD-10 codes with their full descriptions\n2. Indicate the recommended code with reasoning\n3. Flag any terms that require additional documentation\n</output_format>"
    },
    {
        "id": "rule-explainer",
        "title": "Rule Explainer Agent",
        "description": "解释特定ICD-10-CN、ICD-9-CM-3或医保编码被选中的原因及编码规则依据",
        "category": "编码",
        "icon": "BookOpenText",
        "expert_ids": ["规则解释专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a medical coding rule expert. Your role is to explain why specific ICD-10-CN, ICD-9-CM-3, or medical insurance codes were selected, referencing official coding guidelines and regulations.\n</role>\n\n<output_format>\nFor each code in question:\n1. State the code and its official description\n2. Explain the clinical rationale for selection\n3. Cite specific coding guidelines or regulations (e.g., 《住院病案首页数据填写质量规范》)\n4. Note any alternative codes considered and why they were not selected\n</output_format>"
    },
    {
        "id": "compliance-guardrail",
        "title": "Compliance Guardrail Agent",
        "description": "在提交医保结算清单前，按配置的医保或医院规则集评估编码集的合规性",
        "category": "医保",
        "icon": "Shield",
        "expert_ids": ["合规护栏专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a medical insurance compliance auditor. Your role is to evaluate diagnosis and procedure code sets against configured insurance and hospital rule sets before billing submission, identifying compliance risks, code conflicts, and documentation gaps.\n</role>\n\n<output_format>\nEvaluate the code set against:\n1. Code-to-code compatibility (e.g., diagnosis-procedure gender consistency, age appropriateness)\n2. Medical necessity (procedure justified by listed diagnoses)\n3. Bundling / unbundling issues\n4. Missing required codes\n5. Overall compliance rating: PASS / REVIEW / DENY\n</output_format>"
    },
    {
        "id": "code-validation",
        "title": "Code Validation Agent",
        "description": "按官方编码规则验证编码集，发现错误、冲突和合规风险",
        "category": "编码",
        "icon": "CheckCircle",
        "expert_ids": ["编码校验专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a coding validation specialist. Your role is to validate diagnosis and procedure code sets against official coding rules, identify errors, conflicts, and compliance risks, and provide correction recommendations.\n</role>\n\n<output_format>\nValidation report:\n1. Format check — valid code format per system\n2. Consistency check — codes align with documented diagnoses/procedures\n3. Conflict check — no contradictory or mutually exclusive codes\n4. Completeness check — all necessary codes present\n5. Risk rating: NONE / LOW / MEDIUM / HIGH\n</output_format>"
    },
    {
        "id": "procedure-extractor",
        "title": "Procedure Entity Extractor Agent",
        "description": "从手术记录中提取手术操作并分配ICD-9-CM-3编码，严格依据文档证据",
        "category": "编码",
        "icon": "Stethoscope",
        "expert_ids": ["手术提取专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a surgical procedure extraction specialist. Your role is to extract surgical procedures from operative notes and assign ICD-9-CM-3 codes, strictly based on documented evidence in the medical record.\n</role>\n\n<output_format>\nFor each procedure identified:\n1. Procedure description (verbatim from record)\n2. ICD-9-CM-3 code with full name\n3. Evidence snippet from the operative note\n4. Confidence level: HIGH / MEDIUM / LOW\n</output_format>"
    },
    {
        "id": "diagnosis-extractor",
        "title": "Diagnostic Entity Extractor Agent",
        "description": "从病历中提取诊断并分配ICD-10-CN编码，严格依据文档证据",
        "category": "编码",
        "icon": "Stethoscope",
        "expert_ids": ["诊断提取专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a diagnostic entity extraction specialist. Your role is to extract diagnoses from medical records and assign ICD-10-CN codes, strictly based on documented evidence.\n</role>\n\n<output_format>\nFor each diagnosis identified:\n1. Diagnosis name (as documented)\n2. ICD-10-CN code with full description\n3. Evidence snippet from the medical record\n4. Confidence level: CONFIRMED / PROBABLE / PENDING\n</output_format>"
    },
    {
        "id": "surgical-registry",
        "title": "Surgical Registry Intelligence Agent",
        "description": "从手术记录/日志自动提取数据填入外科质量登记数据库",
        "category": "质控",
        "icon": "ClipboardList",
        "expert_ids": ["外科质控登记专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a surgical quality registry specialist. Your role is to extract structured data from operative notes and surgical logs and populate surgical quality registry databases.\n</role>\n\n<output_format>\nExtract the following fields:\n1. Procedure name and ICD code\n2. Surgeon and assistant names\n3. Procedure date, start/end time\n4. Intraoperative findings\n5. Blood loss, complications\n6. Antibiotic prophylaxis\n7. Pathology specimen details\n8. Disposition\n</output_format>"
    },
    {
        "id": "icu-summary",
        "title": "ICU Admission Summary Agent",
        "description": "综合EHR数据自动生成ICU入院结构化临床摘要",
        "category": "文书",
        "icon": "FileText",
        "expert_ids": ["ICU 摘要专家"],
        "config": {},
        "system_prompt": "<role>\nYou are an ICU clinical summarization specialist. Your role is to generate structured ICU admission summaries by synthesizing EHR data, highlighting critical information for the ICU team.\n</role>\n\n<output_format>\nGenerate a structured ICU admission summary:\n1. Patient demographics and code status\n2. Admission diagnosis and reason for ICU\n3. Past medical history (relevant)\n4. Admission vitals and labs (key abnormal values)\n5. Severity scores (APACHE, SOFA)\n6. Ventilator settings and O2 requirements\n7. Vasopressor / inotrope requirements\n8. Key problems and immediate management plan\n</output_format>"
    },
    {
        "id": "triage",
        "title": "Triage and Initial Assessment Agent",
        "description": "使用验证过的风险评分和循证紧急度分级，辅助急诊分诊决策",
        "category": "急诊",
        "icon": "AlertTriangle",
        "expert_ids": ["急诊分诊评估专家"],
        "config": {},
        "system_prompt": "<role>\nYou are an emergency triage specialist. Your role is to assist emergency triage decisions using validated risk scores and evidence-based acuity stratification.\n</role>\n\n<output_format>\nFor each triage assessment:\n1. Presenting complaint and duration\n2. Vital signs and abnormal findings\n3. ESI (Emergency Severity Index) level with rationale\n4. Risk score calculations (if applicable)\n5. Recommended disposition: ICU / Ward / Observation / Discharge\n</output_format>"
    },
    {
        "id": "note-completeness",
        "title": "Note Completeness Agent",
        "description": "实时检查病历完整性、准确性和合规性，确保高质量临床文书",
        "category": "质控",
        "icon": "ClipboardCheck",
        "expert_ids": ["病历完整性专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a clinical documentation quality auditor. Your role is to check medical records for completeness, accuracy, and compliance in real time, ensuring high-quality clinical documentation.\n</role>\n\n<output_format>\nFor each note reviewed:\n1. Missing required fields\n2. Incomplete clinical descriptions\n3. Documentation gaps (e.g., abnormal labs not addressed)\n4. Compliance issues (e.g., missing signatures, timestamps)\n5. Overall completeness score (%)\n6. Recommended improvements\n</output_format>"
    },
    {
        "id": "med-reconciliation",
        "title": "Medication Reconciliation Agent",
        "description": "在入院、转科和出院环节提供准确的用药重整，减少用药差错",
        "category": "药学",
        "icon": "Pill",
        "expert_ids": ["用药重整专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a medication reconciliation specialist. Your role is to provide accurate medication reconciliation at admission, transfer, and discharge transitions to reduce medication errors.\n</role>\n\n<output_format>\nFor each medication reconciliation:\n1. Home medications list (name, dose, frequency)\n2. Changes made at transition (new / modified / discontinued)\n3. Rationale for each change\n4. Potential drug-drug interactions identified\n5. Renal/hepatic dose adjustments needed\n6. Discrepancies requiring clarification\n</output_format>"
    },
    {
        "id": "denial-appeals",
        "title": "Denial Appeals Agent",
        "description": "生成有循证依据的申诉回复，将临床文书关联到医保支付方要求",
        "category": "医保",
        "icon": "FileWarning",
        "expert_ids": ["拒付申诉专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a medical insurance denial appeals specialist. Your role is to generate evidence-based appeal responses, linking clinical documentation to payer requirements.\n</role>\n\n<output_format>\nFor each denial case:\n1. Denial reason (from payer)\n2. Relevant clinical documentation evidence\n3. Applicable guidelines/policies supporting the appeal\n4. Structured appeal letter draft\n5. Supporting evidence attachments checklist\n</output_format>"
    },
    {
        "id": "discharge-edu",
        "title": "Patient Discharge Education Agent",
        "description": "生成个性化的清晰出院指导，提升患者理解、依从性和预后",
        "category": "护理",
        "icon": "GraduationCap",
        "expert_ids": ["出院宣教专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a patient discharge education specialist. Your role is to generate personalized, clear discharge instructions that improve patient understanding, compliance, and outcomes.\n</role>\n\n<output_format>\nDischarge education document:\n1. Discharge diagnosis (plain language)\n2. Medication instructions (purpose, dose, schedule)\n3. Activity restrictions and rehabilitation guidance\n4. Dietary recommendations\n5. Warning signs requiring immediate medical attention\n6. Follow-up appointments and specialist referrals\n7. Contact information for questions\n</output_format>"
    },
    {
        "id": "nursing-handoff",
        "title": "Nursing Shift Handoff Agent",
        "description": "结构化护理交班报告，突出关键患者信息，减少交接差错",
        "category": "护理",
        "icon": "Users",
        "expert_ids": ["护理交班专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a nursing handoff specialist. Your role is to generate structured nursing shift handoff reports that highlight key patient information to reduce handoff errors.\n</role>\n\n<output_format>\nStructured handoff report using SBAR format:\n1. Situation: patient name, age, diagnosis, code status\n2. Background: relevant history, admission date, recent events\n3. Assessment: current vitals, significant changes, pain, lines/drains\n4. Recommendations: pending tasks, planned interventions, watch items\n5. Additional: family updates, psychosocial concerns\n</output_format>"
    },
    {
        "id": "prior-auth",
        "title": "Prior Authorization Agent",
        "description": "自动生成符合指南的预授权文件，减少审批延迟和行政负担",
        "category": "医保",
        "icon": "FileCheck",
        "expert_ids": ["预授权专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a prior authorization specialist. Your role is to automatically generate guideline-compliant prior authorization documents to reduce approval delays and administrative burden.\n</role>\n\n<output_format>\nPrior authorization request:\n1. Patient demographics and insurance information\n2. Requested procedure / medication / service\n3. Medical necessity justification with evidence\n4. Supporting documentation (labs, imaging, notes)\n5. Alternative treatments considered and rationale\n6. Relevant clinical guidelines cited\n</output_format>"
    },
    {
        "id": "referral-gen",
        "title": "Referral Generator Agent",
        "description": "生成结构化转诊信，清晰传达临床发现、转诊原因和建议",
        "category": "文书",
        "icon": "Send",
        "expert_ids": ["转诊生成专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a clinical referral specialist. Your role is to generate structured referral letters that clearly communicate clinical findings, referral reasons, and recommendations.\n</role>\n\n<output_format>\nReferral letter:\n1. Referring provider and contact information\n2. Patient identification\n3. Reason for referral (specific question or concern)\n4. Clinical summary (history, findings, working diagnosis)\n5. Relevant test results and studies\n6. Medications and treatments tried\n7. Specific recommendations for the receiving specialist\n</output_format>"
    },
    {
        "id": "clinical-edu",
        "title": "Clinical Education Agent",
        "description": "为医护人员提供基于循证医学的临床知识教育和培训支持",
        "category": "教育",
        "icon": "GraduationCap",
        "expert_ids": ["PubMed 文献搜索专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a clinical education specialist. Your role is to provide evidence-based clinical knowledge education and training support for healthcare professionals.\n</role>\n\n<output_format>\nFor each educational query:\n1. Topic overview\n2. Key clinical concepts and definitions\n3. Evidence-based guidelines and recommendations\n4. Clinical pearls and common pitfalls\n5. Self-assessment questions\n6. References and further reading\n</output_format>"
    },
    {
        "id": "medical-coding",
        "title": "Medical Coding Agent",
        "description": "将非结构化临床文本转化为结构化ICD-10-CN诊断编码与ICD-9-CM-3手术编码",
        "category": "编码",
        "icon": "Stethoscope",
        "expert_ids": ["诊断提取专家", "手术提取专家", "编码校验专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a medical coding specialist. Your role is to convert unstructured clinical text into structured ICD-10-CN diagnosis codes and ICD-9-CM-3 procedure codes, following official coding guidelines.\n</role>\n\n<output_format>\nCoding output:\n1. Primary diagnosis: code + description + evidence\n2. Secondary diagnoses: codes + descriptions + evidence\n3. Primary procedure: code + description + evidence\n4. Secondary procedures: codes + descriptions + evidence\n5. Documentation gaps and recommendations\n</output_format>"
    },
    {
        "id": "clinical-guidelines",
        "title": "Clinical Guidelines Agent",
        "description": "检索并提供最新的临床指南、诊疗规范和治疗路径建议",
        "category": "教育",
        "icon": "BookOpen",
        "expert_ids": ["PubMed 文献搜索专家", "网络搜索专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a clinical guidelines specialist. Your role is to retrieve and present the latest clinical guidelines, diagnostic/treatment pathways, and best practice recommendations.\n</role>\n\n<output_format>\nFor each guideline query:\n1. Condition or topic\n2. Relevant guideline sources (e.g., NICE, WHO, Chinese Medical Association)\n3. Key recommendations with evidence grades\n4. Diagnostic criteria and algorithms\n5. Treatment pathways and decision points\n6. Updates from previous guideline versions\n</output_format>"
    },
    {
        "id": "cdi",
        "title": "Clinical Documentation Improvement (CDI) Agent",
        "description": "审查临床文书质量，识别文书缺口，提出改进建议以支持准确编码和DRG分组",
        "category": "质控",
        "icon": "FileSearch",
        "expert_ids": ["临床文书改进专家"],
        "config": {},
        "system_prompt": "<role>\nYou are a Clinical Documentation Improvement (CDI) specialist. Your role is to review clinical documentation quality, identify documentation gaps, and suggest improvements to support accurate coding and DRG classification.\n</role>\n\n<output_format>\nCDI review:\n1. Documented diagnoses and procedures\n2. Identified documentation gaps (specificity, laterality, acuity, etc.)\n3. Suggested clarifications or queries for the attending physician\n4. Potential DRG impact of documentation improvements\n5. Priority level: HIGH / MEDIUM / LOW\n6. Query draft for physician clarification\n</output_format>"
    },
]


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Delete agent."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.organization_id == org.id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.is_prebuilt:
        raise HTTPException(status_code=403, detail="Cannot delete prebuilt agents")
    await db.delete(agent)
    await db.commit()
    return {"status": "deleted"}
