"""Expert CRUD API + Expert Library Browser + Run endpoint"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.models.user import User
from app.models.expert import Expert, McpServer
from app.models.organization import Organization
from app.services.expert_runner import expert_runner
from app.services.expert_registry import expert_registry

router = APIRouter(prefix="/api/experts", tags=["experts"])


# ---- Pydantic Schemas ----

class McpServerIn(BaseModel):
    name: str = ""
    url: str = ""
    transport_type: str = "streamable_http"
    description: str = ""

class ExpertCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    system_prompt: str = ""
    icon: str = "Bot"
    category: str = "general"
    mcp_servers: list[McpServerIn] = []

class ExpertUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    icon: str | None = None
    category: str | None = None

class RunRequest(BaseModel):
    input: str = Field(..., min_length=1)
    conversation_history: list[dict] = []


# ---- MCP Server helpers ----

async def _mcp_to_dict(srv: McpServer) -> dict:
    return {
        "id": srv.id,
        "name": srv.name,
        "url": srv.url,
        "transport_type": srv.transport_type,
        "description": srv.description,
        "is_active": srv.is_active,
    }

async def _expert_to_dict(exp: Expert, db: AsyncSession) -> dict:
    result = await db.execute(
        select(McpServer).where(McpServer.expert_id == exp.id, McpServer.is_active == True)
    )
    servers = result.scalars().all()
    return {
        "id": exp.id,
        "name": exp.name,
        "description": exp.description,
        "system_prompt": exp.system_prompt,
        "icon": exp.icon,
        "category": exp.category,
        "is_prebuilt": exp.is_prebuilt,
        "is_published": exp.is_published,
        "created_by": exp.created_by,
        "usage_count": exp.usage_count,
        "mcp_servers": [await _mcp_to_dict(s) for s in servers],
        "created_at": exp.created_at.isoformat(),
        "updated_at": exp.updated_at.isoformat(),
    }


# ---- CRUD Endpoints ----

@router.get("")
async def list_experts(
    category: str = "",
    search: str = "",
    type: str = Query("all", enum=["all", "prebuilt", "custom"]),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List experts with optional filter/search"""
    q = select(Expert).where(Expert.organization_id == org.id)
    if type == "prebuilt":
        q = q.where(Expert.is_prebuilt == True)
    elif type == "custom":
        q = q.where(Expert.is_prebuilt == False)
    if category:
        q = q.where(Expert.category == category)
    if search:
        q = q.where(or_(
            Expert.name.ilike(f"%{search}%"),
            Expert.description.ilike(f"%{search}%"),
        ))
    q = q.order_by(Expert.is_prebuilt.desc(), Expert.usage_count.desc())
    result = await db.execute(q)
    experts = result.scalars().all()
    items = []
    for exp in experts:
        items.append(await _expert_to_dict(exp, db))
    return {"experts": items, "total": len(items)}


@router.post("")
async def create_expert(
    body: ExpertCreate,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom expert"""
    exp = Expert(
        organization_id=org.id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        icon=body.icon,
        category=body.category,
        is_prebuilt=False,
        is_published=False,
        created_by=user.id,
    )
    db.add(exp)
    await db.flush()

    for srv in body.mcp_servers:
        if srv.name and srv.url:
            ms = McpServer(
                organization_id=org.id,
                expert_id=exp.id,
                name=srv.name,
                url=srv.url,
                transport_type=srv.transport_type or "streamable_http",
                description=srv.description,
            )
            db.add(ms)

    await db.commit()
    await db.refresh(exp)
    return await _expert_to_dict(exp, db)


# ---- Registry endpoints ----

@router.get("/registry")
async def get_registry(db: AsyncSession = Depends(get_db)):
    """Get the full expert registry with capabilities (iCoDer-style)."""
    experts = await expert_registry.list_all(db)
    capabilities = await expert_registry.get_capabilities(db)
    return {
        "experts": experts,
        "total": len(experts),
        "capabilities": capabilities,
        "description": "Expert Registry — discover experts by capability. Use /registry/search?capability=X to filter.",
    }


@router.get("/registry/search")
async def search_registry(
    capability: str = Query(..., description="Capability to search for"),
    db: AsyncSession = Depends(get_db),
):
    """Find experts by capability."""
    experts = await expert_registry.find_by_capability(capability, db)
    return {"capability": capability, "experts": experts, "total": len(experts)}


@router.post("/registry/match")
async def match_experts(
    request: str = Query(..., description="User request to match experts for"),
    db: AsyncSession = Depends(get_db),
):
    """LLM-powered expert matching for a user request."""
    result = await expert_registry.match_experts(request, db)
    return result


@router.post("/planner/compare")
async def compare_plans(
    text: str = Query(..., description="Clinical text to compare plans for"),
):
    """Compare fixed pipeline vs dynamic LLM plan."""
    from app.services.llm_planner import llm_planner as planner
    result = await planner.compare_plans(text)
    return result


# ---- SSE Streaming ----

@router.post("/{expert_id}/stream")
async def stream_expert(
    expert_id: str,
    input: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream expert response via Server-Sent Events."""
    from app.services.sse_manager import sse_manager
    import uuid

    result = await db.execute(select(Expert).where(Expert.id == expert_id))
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Expert not found")

    async def generate():
        yield "Processing...\n"
        output = await expert_runner.run(exp, input, [], [])
        yield output

    return await sse_manager.stream_agent_response(uuid.uuid4().hex[:12], generate())


# ---- Guardrails ----

@router.post("/guardrails/check")
async def check_guardrails(
    input_text: str = Query(...),
    output_text: str = Query(""),
):
    """Run safety guardrails on input/output text."""
    from app.services.guardrails import guardrails
    return await guardrails.enforce_all(input_text, output_text)


# ---- BYO Expert (MCP Wrapping) ----

@router.post("/byo/discover")
async def discover_mcp_tools(
    mcp_url: str = Query(...),
    auth_header: str | None = None,
):
    """Discover tools from an external MCP server."""
    from app.services.mcp_wrapper import mcp_wrapper
    tools = await mcp_wrapper.discover_tools(mcp_url, auth_header)
    return {"url": mcp_url, "tools": tools, "count": len(tools)}


@router.post("/byo/create-expert")
async def create_byo_expert(
    mcp_url: str = Query(...),
    system_prompt: str = Query(...),
    name: str = Query("Custom MCP Expert"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom expert from an MCP server (BYO Expert)."""
    from app.services.mcp_wrapper import mcp_wrapper

    config = await mcp_wrapper.create_expert_config(mcp_url, system_prompt, name)
    exp = Expert(
        name=config["name"],
        description=config["description"],
        system_prompt=config["system_prompt"],
        category=config["category"],
        is_prebuilt=False,
        is_published=True,
        created_by=user.id,
        capabilities=["custom", "mcp"],
        tags=config["tool_names"],
    )
    db.add(exp)
    await db.flush()

    # Add MCP server config
    from app.models.expert import McpServer
    srv = McpServer(
        expert_id=exp.id,
        name=name,
        url=mcp_url,
        transport_type="streamable_http",
        description=f"MCP server with {config['tool_count']} tools",
    )
    db.add(srv)
    await db.commit()
    await db.refresh(exp)

    return {"expert_id": exp.id, "config": config, "status": "created"}


# ---- Expert Direct Call ----


@router.post("/call/{expert_name}")
async def call_expert_directly(
    expert_name: str,
    input: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Direct Expert Call — bypass the Orchestrator, call an expert by name.

    iCoDer equivalent: "Direct Expert Calls — direct API access to individual experts."
    """
    result = await db.execute(
        select(Expert).where(
            Expert.name.ilike(f"%{expert_name}%"),
            Expert.is_published == True,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail=f"Expert not found: {expert_name}")

    output = await expert_runner.run(exp, input, [], [])
    return {"expert": exp.name, "output": output}


# ---- Memory endpoints ----

@router.post("/memory/save")
async def save_memory(
    session_id: str = Query(...),
    role: str = Query(...),
    content: str = Query(...),
    expert_id: str | None = None,
    agent_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a conversation message to persistent memory."""
    from app.services.memory_expert import memory_expert
    mem = await memory_expert.save(user.id, session_id, role, content, expert_id, agent_id, db)
    return {"status": "saved", "id": mem.id if mem else None}


@router.get("/memory/recall")
async def recall_memory(
    query: str = Query(...),
    limit: int = 10,
    expert_id: str | None = None,
    agent_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recall relevant memories for a query (optionally scoped by expert/agent)."""
    from app.services.memory_expert import memory_expert
    results = await memory_expert.recall(
        user.id, query, limit, db,
        expert_id=expert_id, agent_id=agent_id,
    )
    return {"query": query, "memories": results, "total": len(results)}


@router.get("/memory/context")
async def get_context(
    session_id: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get session context for ongoing conversation."""
    from app.services.memory_expert import memory_expert
    ctx = await memory_expert.get_session_context(user.id, session_id, db=db)
    return {"session_id": session_id, "context": ctx}


@router.get("/memory/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user profile built from accumulated memories."""
    from app.services.memory_expert import memory_expert
    return await memory_expert.get_user_profile(user.id, db)


@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    """List distinct expert categories"""
    result = await db.execute(select(Expert.category, func.count(Expert.id)).group_by(Expert.category))
    rows = result.all()
    return {"categories": [{"name": r[0], "count": r[1]} for r in rows]}


@router.get("/{expert_id}")
async def get_expert(
    expert_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get expert detail"""
    result = await db.execute(select(Expert).where(Expert.id == expert_id))
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Expert not found")
    return await _expert_to_dict(exp, db)


@router.put("/{expert_id}")
async def update_expert(
    expert_id: str,
    body: ExpertUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update custom expert"""
    result = await db.execute(select(Expert).where(Expert.id == expert_id))
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Expert not found")
    if body.name is not None:
        exp.name = body.name
    if body.description is not None:
        exp.description = body.description
    if body.system_prompt is not None:
        exp.system_prompt = body.system_prompt
    if body.icon is not None:
        exp.icon = body.icon
    if body.category is not None:
        exp.category = body.category
    await db.commit()
    await db.refresh(exp)
    return await _expert_to_dict(exp, db)


@router.delete("/{expert_id}")
async def delete_expert(
    expert_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete custom expert"""
    result = await db.execute(select(Expert).where(Expert.id == expert_id))
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Expert not found")
    if exp.is_prebuilt:
        raise HTTPException(status_code=403, detail="Cannot delete prebuilt experts")
    # Cascade delete MCP servers
    mcp_result = await db.execute(select(McpServer).where(McpServer.expert_id == expert_id))
    for srv in mcp_result.scalars().all():
        await db.delete(srv)
    await db.delete(exp)
    await db.commit()
    return {"status": "deleted"}


# ---- MCP Server management ----

@router.post("/{expert_id}/mcp-servers")
async def add_mcp_server(
    expert_id: str,
    body: McpServerIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add MCP server to expert"""
    result = await db.execute(select(Expert).where(Expert.id == expert_id))
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Expert not found")
    if exp.is_prebuilt:
        raise HTTPException(status_code=403, detail="Cannot modify prebuilt experts")
    srv = McpServer(
        expert_id=expert_id,
        name=body.name,
        url=body.url,
        transport_type=body.transport_type or "streamable_http",
        description=body.description,
    )
    db.add(srv)
    await db.commit()
    await db.refresh(srv)
    return await _mcp_to_dict(srv)


@router.delete("/{expert_id}/mcp-servers/{server_id}")
async def remove_mcp_server(
    expert_id: str,
    server_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove MCP server"""
    result = await db.execute(
        select(McpServer).where(McpServer.id == server_id, McpServer.expert_id == expert_id)
    )
    srv = result.scalar_one_or_none()
    if not srv:
        raise HTTPException(status_code=404, detail="MCP server not found")
    await db.delete(srv)
    await db.commit()
    return {"status": "deleted"}


# ---- Run Expert ----

@router.post("/{expert_id}/run")
async def run_expert(
    expert_id: str,
    body: RunRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute an expert with given input"""
    result = await db.execute(select(Expert).where(Expert.id == expert_id))
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Expert not found")

    # Fetch MCP servers
    mcp_result = await db.execute(
        select(McpServer).where(McpServer.expert_id == expert_id, McpServer.is_active == True)
    )
    mcp_servers = mcp_result.scalars().all()

    output = await expert_runner.run(
        expert=exp,
        user_input=body.input,
        conversation_history=body.conversation_history,
        mcp_servers=mcp_servers,
    )

    # Increment usage
    exp.usage_count = (exp.usage_count or 0) + 1
    await db.commit()

    return {"expert_id": expert_id, "output": output, "model": "deepseek-chat"}


class PunctuateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Raw unpunctuated Chinese text")
    use_llm: bool = Field(default=True, description="Whether to run medical LLM correction pass")

@router.post("/stt/punctuate")
async def punctuate_text(
    body: PunctuateRequest,
    user: User = Depends(get_current_user),
):
    """Two-stage Chinese punctuation restoration.

    Stage 1: CT-Transformer (MacBERT-architecture, offline, no API cost)
    Stage 2: Medical LLM correction (DeepSeek, domain-specific refinement)

    Works with output from any ASR engine: browser SpeechRecognition,
    Paraformer, Whisper, SenseVoice, etc.
    """
    from app.services.punctuation_service import punctuation_service

    try:
        result = await punctuation_service.punctuate(body.text, use_llm=body.use_llm)
        return {"text": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Punctuation restoration failed: {str(e)}")
