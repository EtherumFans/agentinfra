"""Tenant-scoped operational metadata; no clinical bodies or credentials."""
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, case, and_, or_, update
from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.models.organization import OrganizationMember, OrgRole
from app.models.run_history import RunHistoryModel as Run
from app.models.agent_job import AgentJob as Job
from app.models.audit_log import AuditLog
from app.models.agent import Agent
from app.services.tenant_read_policy import TENANT_VISIBLE_CLASSIFICATIONS
from app.services.agent_jobs import validate_callback, now

router=APIRouter(prefix='/api/operations',tags=['agent-operations'])

async def admin_role(db, user, org):
    role=(await db.execute(select(OrganizationMember.role).where(OrganizationMember.organization_id==org.id,OrganizationMember.user_id==user.id))).scalar_one_or_none()
    return role in (OrgRole.OWNER,OrgRole.ADMIN)

def category(reason):
    value=func.lower(func.coalesce(reason,''))
    return case((or_(value.like('%403%'),value.like('%permission%'),value.like('%denied%')),'access'),(or_(value.like('%401%'),value.like('%auth%')),'authentication'),(or_(value.like('%version%'),value.like('%configuration%'),value.like('%dependency%')),'configuration'),(or_(value.like('%timeout%'),value.like('%outcome_unknown%')),'uncertain'),(value.like('%tool%'),'tool'),(or_(value.like('%model%'),value.like('%llm%'),value.like('%provider%')),'model'),else_='other')

@router.get('/overview')
async def overview(days:int=Query(7,ge=1,le=365),agent_id:str=Query('',max_length=128),version:str=Query('',max_length=64),client_id:str=Query('',max_length=128),failures_only:bool=False,run_offset:int=Query(0,ge=0,le=100000),job_offset:int=Query(0,ge=0,le=100000),user=Depends(get_current_user),org=Depends(get_current_organization),db=Depends(get_db)):
    admin=await admin_role(db,user,org)
    timestamp=datetime.now(timezone.utc);cutoff=timestamp-timedelta(days=days)
    rf=[Run.organization_id==org.id,Run.tenancy_classification.in_(TENANT_VISIBLE_CLASSIFICATIONS),Run.created_at>=cutoff.replace(tzinfo=None),Run.created_at<=timestamp.replace(tzinfo=None)]
    jf=[Job.organization_id==org.id,Job.created_at>=cutoff,Job.created_at<=timestamp]
    if not admin:
        rf.append(Run.user_id==str(user.id));jf.extend([Job.actor_kind=='user',Job.actor_id==str(user.id)])
    if agent_id:rf.append(Run.agent_id==agent_id);jf.append(Job.agent_id==agent_id)
    if version:rf.append(Run.executed_agent_version==version);jf.append(Job.version==version)
    if client_id:
        rf.append(Run.api_client_id==client_id);jf.extend([Job.actor_kind=='oauth',Job.actor_id==client_id])
    failed=or_(Run.error.is_(True),Run.status=='FAILED')
    success=and_(Run.error.is_(False),Run.status.in_(['COMPLETED','COMPLETED_AFTER_CLIENT_ABORT']))
    terminal=or_(failed,success)
    stats=(await db.execute(select(func.count(),func.sum(case((success,1),else_=0)),func.sum(case((failed,1),else_=0)),func.avg(case((terminal,Run.latency_ms),else_=None))).where(*rf))).one()
    total,passed,errors,latency=stats;passed=passed or 0;errors=errors or 0
    observed = (await db.execute(select(
        func.count(Run.model_calls), func.sum(Run.model_calls),
        func.sum(Run.model_input_tokens), func.sum(Run.model_output_tokens),
        func.sum(Run.model_estimated_cost_usd),
        func.sum(case((Run.model_usage_complete.is_(True), 1), else_=0)),
        func.sum(case((Run.model_cost_complete.is_(True), 1), else_=0)),
    ).where(*rf))).one()
    usage = {'recorded_runs':observed[0], 'unrecorded_runs':total-observed[0],
             'calls':observed[1], 'input_tokens':observed[2], 'output_tokens':observed[3],
             'estimated_cost_usd':round(observed[4], 8) if observed[4] is not None else None,
             'complete_usage_runs':observed[5] or 0, 'complete_cost_runs':observed[6] or 0,
             'currency':'USD', 'billing_authoritative':False}
    jobs_by_state=dict((await db.execute(select(Job.state,func.count()).where(*jf).group_by(Job.state))).all())
    notices=dict((await db.execute(select(Job.notification_state,func.count()).where(*jf).group_by(Job.notification_state))).all())
    failure_category=category(Run.error_reason)
    failures=[{'category':k,'count':n} for k,n in (await db.execute(select(failure_category,func.count()).where(*rf,failed).group_by(failure_category))).all()]
    groups=(await db.execute(select(Run.agent_id,Run.executed_agent_version,Run.api_client_id,func.count(),func.sum(case((success,1),else_=0)),func.sum(case((failed,1),else_=0)),func.avg(case((terminal,Run.latency_ms),else_=None))).where(*rf).group_by(Run.agent_id,Run.executed_agent_version,Run.api_client_id).order_by(func.count().desc(),Run.agent_id,Run.executed_agent_version,Run.api_client_id).limit(101))).all()
    run_filter=rf+([failed] if failures_only else [])
    job_filter=jf+([or_(Job.state.in_(['failed','interrupted']),Job.notification_state=='failed')] if failures_only else [])
    runs=(await db.execute(select(Run.run_id,Run.agent_id,Run.executed_agent_version,Run.api_client_id,Run.status,Run.error,Run.latency_ms,Run.created_at,Run.model_usage,category(Run.error_reason).label('category')).where(*run_filter).order_by(Run.created_at.desc(),Run.run_id.desc()).offset(run_offset).limit(21))).mappings().all()
    jobs=(await db.execute(select(Job.id,Job.agent_id,Job.version,Job.actor_kind,Job.actor_id,Job.run_id,Job.state,Job.notification_state,Job.notification_attempts,Job.created_at,category(Job.error_code).label('category')).where(*job_filter).order_by(Job.created_at.desc(),Job.id.desc()).offset(job_offset).limit(21))).mappings().all()
    ids={r[0] for r in groups[:100]}|{r['agent_id'] for r in runs[:20]}|{j['agent_id'] for j in jobs[:20]}
    names=dict((await db.execute(select(Agent.id,Agent.name).where(Agent.organization_id==org.id,Agent.id.in_(ids)))).all()) if ids else {}
    return {'model_usage':usage,'agent_names':names,'scope':'organization' if admin else 'personal','as_of':timestamp.isoformat(),'days':days,'summary':{'runs':total,'succeeded':passed,'failed':errors,'other':total-passed-errors,'success_rate':round(passed/(passed+errors)*100,2) if passed+errors else None,'average_latency_ms':round(latency,1) if latency is not None else None},'queue':jobs_by_state,'notifications':notices,'failures':failures,'groups':[{'agent_id':r[0],'version':r[1],'client_id':r[2],'runs':r[3],'succeeded':r[4] or 0,'failed':r[5] or 0,'average_latency_ms':round(r[6],1) if r[6] is not None else None} for r in groups[:100]],'groups_truncated':len(groups)>100,'runs':[{**dict(r),'created_at':r['created_at'].replace(tzinfo=timezone.utc).isoformat()} for r in runs[:20]],'runs_more':len(runs)>20,'jobs':[dict(r) for r in jobs[:20]],'jobs_more':len(jobs)>20}

@router.post('/jobs/{job_id}/{action}')
async def operate(job_id:str,action:str,user=Depends(get_current_user),org=Depends(get_current_organization),db=Depends(get_db)):
    if action not in ('cancel','retry-notification'):raise HTTPException(404,'operation_not_found')
    admin=await admin_role(db,user,org)
    conditions=[Job.id==job_id,Job.organization_id==org.id]
    if not admin:conditions.extend([Job.actor_kind=='user',Job.actor_id==str(user.id)])
    job=(await db.execute(select(Job).where(*conditions))).scalar_one_or_none()
    if not job:raise HTTPException(404,'job_not_found')
    if action=='cancel':
        conditions.append(Job.state=='queued');values={'state':'cancelled','finished_at':now(),'notification_due':now()}
    else:
        validate_callback(job.callback_url,org.id)
        conditions.extend([Job.notification_state=='failed',Job.state.in_(['completed','failed','interrupted','cancelled'])]);values={'notification_state':'pending','notification_attempts':0,'notification_due':now(),'notification_lease':None}
    result=await db.execute(update(Job).where(*conditions).values(**values))
    if result.rowcount!=1:raise HTTPException(409,'job_state_changed_refresh_required')
    db.add(AuditLog(organization_id=org.id,user_id=str(user.id),action='agent.operations.'+action,resource_type='agent_job',resource_id=job.id,tenancy_classification='MODERN',details={'agent_id':job.agent_id}))
    await db.commit()
    return {'updated':True}
