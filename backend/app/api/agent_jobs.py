"""Authenticated batch job submission and owner-scoped status/result retrieval."""
import json
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,func,update,text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user_or_oauth_client,get_current_organization
from app.models.organization import Organization
from app.models.agent_job import AgentJob
from app.api.agent_run import AgentRunRequestInput,_require_agent_run_scope,_require_machine_delegation
from app.services.agent_runtime_pack import load_tenant_agent
from app.services.agent_integration import integration_manifest,validate_integration_binding
from app.services.agent_jobs import actor,projection,validate_callback,now
from app.services.phi_encryption import encrypt_phi
from app.services.release_evaluation import digest

router=APIRouter(prefix='/api/v1',tags=['agent-jobs'])
class JobSubmission(BaseModel):
    model_config=ConfigDict(extra='forbid')
    inputs:list[AgentRunRequestInput]=Field(min_length=1,max_length=20)
    purpose_of_use:str=Field(min_length=1,max_length=32)
    expected_agent_version:str | None=Field(default=None,max_length=64)
    expected_configuration_digest:str | None=Field(default=None,max_length=64)
    callback_url:str | None=Field(default=None,max_length=2048)

@router.post('/agents/{agent_id}/jobs',status_code=202)
async def submit_jobs(agent_id:str,body:JobSubmission,request:Request,principal:tuple=Depends(get_current_user_or_oauth_client),
    org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    kind,identity=actor(principal)
    if principal[1] is not None:
        _require_agent_run_scope(agent_id,principal[1]);_require_machine_delegation(agent_id,body.purpose_of_use,principal[1])
    key=(request.headers.get('Idempotency-Key') or '').strip()
    if not key or len(key)>120 or any(ord(c)<33 or ord(c)>126 for c in key):raise HTTPException(422,'idempotency_key_required_max_120_ascii')
    validate_callback(body.callback_url,org.id)
    resolved=await load_tenant_agent(agent_id,org.id,db,version=body.expected_agent_version)
    if resolved is None:raise HTTPException(404,'agent_not_found')
    manifest=integration_manifest(resolved)
    validate_integration_binding(resolved,body.expected_agent_version,body.expected_configuration_digest)
    request_hash=digest({'agent_id':agent_id,'body':body.model_dump(mode='json')})
    keys=[f'{key}:{i}' for i in range(len(body.inputs))]
    async def existing():
        return list((await db.execute(select(AgentJob).where(AgentJob.organization_id==org.id,AgentJob.actor_kind==kind,
            AgentJob.actor_id==identity,AgentJob.idempotency_key.in_(keys)).order_by(AgentJob.created_at,AgentJob.id))).scalars())
    await db.execute(text("UPDATE organizations SET id=id WHERE id=:org"),{'org':org.id})
    prior=await existing()
    if prior:
        if len(prior)!=len(keys) or any(j.request_digest!=request_hash for j in prior):raise HTTPException(409,'idempotency_conflict')
        return {'jobs':[projection(j) for j in prior],'replayed':True}
    pending=(await db.execute(select(func.count()).select_from(AgentJob).where(AgentJob.organization_id==org.id,AgentJob.state.in_(['queued','running'])))).scalar_one()
    if pending+len(keys)>100:raise HTTPException(429,'organization_queue_full')
    jobs=[]
    for i,value in enumerate(body.inputs):
        payload={'request':{'input':value.model_dump(mode='json'),'purpose_of_use':body.purpose_of_use,
            'expected_agent_version':manifest['version'],'expected_configuration_digest':manifest['configuration_digest']},
            'scopes':principal[1].get('scopes',[]) if principal[1] else []}
        job=AgentJob(organization_id=org.id,agent_id=agent_id,actor_kind=kind,actor_id=identity,idempotency_key=keys[i],
            request_digest=request_hash,version=manifest['version'],payload=encrypt_phi(json.dumps(payload,ensure_ascii=False)),
            callback_url=body.callback_url,notification_state='pending' if body.callback_url else 'none')
        db.add(job);jobs.append(job)
    try:await db.commit()
    except IntegrityError:
        await db.rollback();prior=await existing()
        if len(prior)!=len(keys) or any(j.request_digest!=request_hash for j in prior):raise HTTPException(409,'idempotency_conflict')
        jobs=prior
    return {'jobs':[projection(j) for j in jobs],'replayed':False}

async def owned_job(jid,principal,org,db):
    kind,identity=actor(principal)
    job=(await db.execute(select(AgentJob).where(AgentJob.id==jid,AgentJob.organization_id==org.id,AgentJob.actor_kind==kind,AgentJob.actor_id==identity))).scalar_one_or_none()
    if not job:raise HTTPException(404,'job_not_found')
    return job

@router.get('/agent-jobs')
async def list_jobs(agent_id:str | None=None, limit:int=Query(20,ge=1,le=100), offset:int=Query(0,ge=0), q:str=Query('',max_length=128), state:str | None=Query(None,pattern='^(queued|running|completed|failed|interrupted|cancelled)$'), principal:tuple=Depends(get_current_user_or_oauth_client),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    kind,identity=actor(principal)
    query=select(AgentJob).where(AgentJob.organization_id==org.id,AgentJob.actor_kind==kind,AgentJob.actor_id==identity)
    if agent_id:query=query.where(AgentJob.agent_id==agent_id)
    if state:query=query.where(AgentJob.state==state)
    if q:query=query.where(AgentJob.id.contains(q,autoescape=True) | AgentJob.version.contains(q,autoescape=True))
    rows=(await db.execute(query.order_by(AgentJob.created_at.desc(),AgentJob.id.desc()).offset(offset).limit(limit+1))).scalars().all()
    return {'jobs':[projection(j) for j in rows[:limit]],'has_more':len(rows)>limit,'offset':offset,'limit':limit}

@router.get('/agent-jobs/{job_id}')
async def get_job(job_id:str,principal:tuple=Depends(get_current_user_or_oauth_client),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    return projection(await owned_job(job_id,principal,org,db),True)

@router.post('/agent-jobs/{job_id}/cancel')
async def cancel_job(job_id:str,principal:tuple=Depends(get_current_user_or_oauth_client),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    job=await owned_job(job_id,principal,org,db)
    result=await db.execute(update(AgentJob).where(AgentJob.id==job.id,AgentJob.organization_id==org.id,AgentJob.state=='queued').values(state='cancelled',finished_at=now(),notification_due=now()))
    if result.rowcount!=1:raise HTTPException(409,'only_queued_jobs_can_cancel')
    await db.commit();return {'state':'cancelled'}

@router.post('/agent-jobs/{job_id}/retry-notification')
async def retry_notification(job_id:str,principal:tuple=Depends(get_current_user_or_oauth_client),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    job=await owned_job(job_id,principal,org,db)
    validate_callback(job.callback_url,org.id)
    result=await db.execute(update(AgentJob).where(AgentJob.id==job.id,AgentJob.organization_id==org.id,AgentJob.notification_state=='failed').values(notification_state='pending',notification_attempts=0,notification_due=now(),notification_lease=None))
    if result.rowcount!=1:raise HTTPException(409,'notification_not_failed')
    await db.commit();return {'notification_state':'pending'}
