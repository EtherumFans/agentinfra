"""Agent delivery routes separated from CRUD; public URLs remain stable."""
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user,get_current_organization
from app.models.agent import Agent
from app.models.user import User
from app.models.organization import Organization
from app.api.agents import _owned_agent_for_lifecycle,_audit_agent_lifecycle
router=APIRouter(prefix='/api/rest/v1/agent_definitions',tags=['agent-delivery'])
from app.services.agent_dependencies import DependencyRegistration,DependencyBindings

@router.get('/{agent_id}/dependencies')
async def list_agent_dependencies(agent_id:str,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),q:str=Query('',max_length=100),current_only:bool=False,user:User=Depends(get_current_user),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    from app.models.agent_dependency import AgentDependency
    from app.services.agent_dependencies import project,release_drift
    from app.services.agent_releases import preserve_current
    agent=await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    release=await preserve_current(db,agent,str(user.id))
    query=select(AgentDependency).where(AgentDependency.organization_id==org.id)
    if current_only:query=query.where(AgentDependency.is_current.is_(True))
    if q:query=query.where(AgentDependency.name.contains(q,autoescape=True) | AgentDependency.version.contains(q,autoescape=True))
    rows=(await db.execute(query.order_by(AgentDependency.created_at.desc(),AgentDependency.id.desc()).offset(offset).limit(limit+1))).scalars().all()
    locks=release.runtime_pack.get('_dependency_lock',[]) if release else []
    drift=await release_drift(db,release) if release else []
    from app.models.organization import OrganizationMember,OrgRole
    role=(await db.execute(select(OrganizationMember.role).where(OrganizationMember.organization_id==org.id,OrganizationMember.user_id==user.id))).scalar_one_or_none()
    await db.commit()
    return {'bindings':(agent.config or {}).get('dependency_bindings',[]),'locked':locks,'drift':drift,
        'can_register':role in (OrgRole.OWNER,OrgRole.ADMIN),
        'registry':[dict(project(r),is_current=r.is_current) for r in rows[:limit]],
        'has_more':len(rows)>limit,'offset':offset,'limit':limit,
        'verification':'operator_declared','remote_content_verified':False}


@router.post('/{agent_id}/dependencies/register')
async def register_dependency(agent_id:str,body:DependencyRegistration,user:User=Depends(get_current_user),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    from app.models.agent_dependency import AgentDependency
    from app.models.organization import OrganizationMember,OrgRole
    from app.services.agent_dependencies import project
    from sqlalchemy import update
    agent=await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    role=(await db.execute(select(OrganizationMember.role).where(OrganizationMember.organization_id==org.id,OrganizationMember.user_id==user.id))).scalar_one_or_none()
    if role not in (OrgRole.OWNER,OrgRole.ADMIN):raise HTTPException(403,'dependency_registration_requires_org_admin')
    await db.execute(text('UPDATE organizations SET id=id WHERE id=:org'),{'org':org.id})
    match=(AgentDependency.organization_id==org.id,AgentDependency.kind==body.kind,AgentDependency.name==body.name)
    existing=(await db.execute(select(AgentDependency).where(*match,AgentDependency.version==body.version))).scalar_one_or_none()
    if existing and existing.artifact_digest!=body.artifact_digest:raise HTTPException(409,'dependency_version_immutable')
    await db.execute(update(AgentDependency).where(*match).values(is_current=False))
    if existing:existing.is_current=True;row=existing
    else:
        row=AgentDependency(organization_id=org.id,created_by=str(user.id),**body.model_dump());db.add(row)
    await _audit_agent_lifecycle(db,agent=agent,org=org,user=user,action='agent.dependency.registered',details=body.model_dump())
    await db.commit()
    return project(row)


@router.put('/{agent_id}/dependencies/bindings')
async def bind_agent_dependencies(agent_id:str,body:DependencyBindings,user:User=Depends(get_current_user),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    from app.services.agent_dependencies import resolve_bindings
    from app.services.agent_releases import preserve_current
    agent=await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    bindings=[b.model_dump() for b in body.bindings]
    await resolve_bindings(db,org.id,bindings)
    await preserve_current(db,agent,str(user.id))
    agent.config={**(agent.config or {}),'dependency_bindings':bindings}
    await _audit_agent_lifecycle(db,agent=agent,org=org,user=user,action='agent.dependencies.bound',details={'bindings':bindings})
    await db.commit()
    return {'bindings':bindings,'published':False}


@router.get('/{agent_id}/dependencies/impact')
async def get_dependency_impact(agent_id:str,kind:str=Query(pattern='^(model|tool|knowledge)$'),name:str=Query(min_length=1,max_length=100),user:User=Depends(get_current_user),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    from app.models.organization import OrganizationMember,OrgRole
    from app.services.dependency_impact import dependency_impact
    await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    role=(await db.execute(select(OrganizationMember.role).where(OrganizationMember.organization_id==org.id,OrganizationMember.user_id==user.id))).scalar_one_or_none()
    if role not in (OrgRole.OWNER,OrgRole.ADMIN):raise HTTPException(403,'dependency_impact_requires_org_admin')
    return {'agents':await dependency_impact(db,org.id,kind,name),'scope':'organization','client_versions_known':False}

@router.get('/{agent_id}/dependencies/candidates')
async def get_dependency_candidates(agent_id:str,user:User=Depends(get_current_user),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    from app.services.dependency_impact import configured_dependency_candidates
    agent=await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    return {'candidates':await configured_dependency_candidates(db,agent),'verified':False}
