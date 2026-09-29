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
from app.services.release_evaluation import EvaluationRequest
from app.middleware.auth import require_org_role, require_org_membership
from pydantic import BaseModel, Field
from typing import Literal
from fastapi import UploadFile, File, Form
from starlette.concurrency import run_in_threadpool

@router.post('/{agent_id}/evaluation-import')
async def preview_evaluation_import(agent_id:str,file:UploadFile=File(...),start:int=Form(1,ge=1,le=20000),limit:int=Form(10,ge=1,le=10),user=Depends(get_current_user),org=Depends(get_current_organization),db=Depends(get_db)):
    await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    try:
        if not (file.filename or '').lower().endswith('.xlsx'):raise HTTPException(422,'仅支持 .xlsx 训练集。')
        content=await file.read(10*1024*1024+1)
        if len(content)>10*1024*1024:raise HTTPException(413,'Excel 文件不能超过 10 MB。')
        from app.services.evaluation_import import preview_training_xlsx
        return await run_in_threadpool(preview_training_xlsx,content,start,limit)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
    finally:await file.close()


class ReviewRequest(BaseModel):
    decision: Literal['approved','rejected']
    note: str = Field(min_length=1,max_length=2000)
    expected_previous_review_id: str | None = Field(default=None,max_length=36)


@router.post('/{agent_id}/evaluations/{evaluation_id}/review')
async def review_evaluation(agent_id: str, evaluation_id: str, body: ReviewRequest,
    user=Depends(get_current_user), org=Depends(get_current_organization),
    _member=Depends(require_org_role('owner','admin')), db=Depends(get_db)):
    from app.models.agent_evaluation import AgentEvaluation
    from app.models.agent_evaluation_review import AgentEvaluationReview
    from app.services.release_evaluation import draft_fingerprint, review_summaries
    from app.services.business_evaluation import model_binding
    await db.execute(text('UPDATE organizations SET id=id WHERE id=:org'),{'org':org.id})
    agent = await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    report = (await db.execute(select(AgentEvaluation).where(AgentEvaluation.id==evaluation_id,
        AgentEvaluation.agent_id==agent_id, AgentEvaluation.organization_id==org.id))).scalar_one_or_none()
    if report is None:
        raise HTTPException(404,'evaluation_not_found')
    previous = (await review_summaries(db,org.id,[report.id])).get(report.id)
    if (previous['id'] if previous else None) != body.expected_previous_review_id:
        raise HTTPException(409,'review_changed_refresh_required')
    if not body.note.strip():
        raise HTTPException(422,'review_note_required')
    if body.decision=='approved':
        valid = report.report.get('consistent') and report.report.get('checks_passed')
        valid = valid and report.report.get('model_binding') == await model_binding(db,org.id)
        if report.report.get('candidate_version')=='draft':
            valid = valid and report.report.get('draft_digest') == await draft_fingerprint(db,agent)
        if not valid:
            raise HTTPException(409,'evaluation_failed_or_stale')
    review = AgentEvaluationReview(organization_id=org.id,evaluation_id=report.id,
        decision=body.decision,note=body.note.strip(),created_by=str(user.id))
    db.add(review);await db.flush()
    await _audit_agent_lifecycle(db,agent=agent,org=org,user=user,action='agent.evaluation.reviewed',
        details={'evaluation_id':report.id,'review_id':review.id,'decision':body.decision})
    await db.commit()
    return {'id':review.id,'decision':review.decision}

@router.post('/{agent_id}/evaluations')
async def evaluate_agent_releases(agent_id: str, body: EvaluationRequest, request: Request,
    user: User=Depends(get_current_user), org: Organization=Depends(get_current_organization),
    db: AsyncSession=Depends(get_db)):
    from app.services.agent_releases import preserve_current, runtime_definition, definition
    from app.services.agent_integration import integration_manifest
    from app.services.release_evaluation import digest, check_result, draft_fingerprint
    from app.services.business_evaluation import model_binding
    from app.models.agent_evaluation import AgentEvaluation
    from app.api.agent_run import run_agent, AgentRunRequest
    agent=await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    await preserve_current(db,agent,str(user.id))
    baseline=integration_manifest(await runtime_definition(db,agent,body.baseline_version)) if body.baseline_version else None
    candidate=None if body.candidate_version=='draft' else integration_manifest(await runtime_definition(db,agent,body.candidate_version))
    from app.services.agent_dependencies import draft_locks
    initial=await draft_fingerprint(db,agent)
    initial_model = await model_binding(db, org.id)
    await db.commit()
    # Each subrun has its own identity; an outer idempotency header cannot alias them.
    scope={**request.scope,'headers':[(k,v) for k,v in request.scope['headers'] if k.lower()!=b'idempotency-key']}
    run_request=Request(scope)
    rows=[]
    for case in body.cases:
        row={'case_id':case.id}
        for label,binding in (('baseline',baseline),('candidate',candidate)):
            if label=='baseline' and baseline is None:
                row[label]={'passed':False,'skipped':True,'checks':[]}
                continue
            args={'input':{'text':case.text},'purpose_of_use':body.purpose_of_use}
            if binding:
                args.update(expected_agent_version=binding['version'],expected_configuration_digest=binding['configuration_digest'])
            else:
                args['preview_draft']=True
            try:
                result=await run_agent(agent_id,AgentRunRequest(**args),run_request,(user,None),org,db)
                row[label]=check_result(case,result)
                if body.business_suite:
                    from app.models.run_history import RunHistoryModel
                    run = (await db.execute(select(RunHistoryModel).where(
                        RunHistoryModel.run_id==result.run_id, RunHistoryModel.organization_id==org.id))).scalar_one_or_none()
                    usage = run.model_usage if run else None
                    live = bool(usage and usage.get('calls') and usage.get('usage_complete') and usage.get('models')
                                and all(m.get('provider') not in ('mock','unknown') and m.get('model') not in ('unknown','mock/1.0') for m in usage['models']))
                    if initial_model.get('source')=='organization' and live:
                        live = all(m.get('provider')==initial_model['provider'] and m.get('model')==initial_model['model'] for m in usage['models'])
                    row[label]['model_usage'] = usage
                    row[label]['real_model_verified'] = live
                    row[label]['checks'].append({'kind':'real_model','passed':live,'reason':'ok' if live else 'real_model_evidence_missing'})
                    row[label]['passed'] = row[label]['passed'] and live
            except HTTPException as exc:
                row[label]={'passed':False,'execution_ok':False,'http_status':exc.status_code,'checks':[]}
        row['regression']=row['baseline']['passed'] and not row['candidate']['passed']
        rows.append(row)
    latest=(await db.execute(select(Agent).where(Agent.id==agent_id,Agent.organization_id==org.id).execution_options(populate_existing=True))).scalar_one_or_none()
    consistent=latest is not None and (candidate is not None or initial==await draft_fingerprint(db,latest)) and initial_model==await model_binding(db,org.id)
    report={'schema':'icoder.release-evaluation/v1','baseline_version':body.baseline_version,
        'batch_context':request.scope.get('_evaluation_batch_context'),
        'business_suite':body.business_suite,'model_binding':initial_model,
        'purpose_of_use':body.purpose_of_use,
        'candidate_version':body.candidate_version,'draft_digest':initial if candidate is None else None,
        'suite_digest':digest([c.model_dump() for c in body.cases]),'case_count':len(rows),
        'consistent':consistent,'regressions':sum(r['regression'] for r in rows),
        'candidate_passed':sum(r['candidate']['passed'] for r in rows),
        'checks_passed':consistent and all(r['candidate']['passed'] for r in rows),
        'clinical_approval':False,'cases':rows}
    record=AgentEvaluation(organization_id=org.id,agent_id=agent_id,report=report,created_by=str(user.id))
    db.add(record)
    await db.flush()
    await _audit_agent_lifecycle(db,agent=latest or agent,org=org,user=user,
        action='agent.evaluation.completed',details={'evaluation_id':record.id,'suite_digest':report['suite_digest'],'checks_passed':report['checks_passed']})
    await db.commit()
    return {'id':record.id,**report}


@router.get('/{agent_id}/evaluation-suites')
async def evaluation_suites(agent_id: str, user=Depends(get_current_user), org=Depends(get_current_organization), db=Depends(get_db)):
    from app.services.business_evaluation import SUITES
    await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    return {'suites':[{'id':key,**value} for key,value in SUITES.items()]}


@router.get('/{agent_id}/evaluations')
async def list_agent_evaluations(agent_id: str, limit:int=Query(20,ge=1,le=100), offset:int=Query(0,ge=0), q:str=Query('',max_length=128), paginated:bool=False, user: User=Depends(get_current_user),
    org: Organization=Depends(get_current_organization),db: AsyncSession=Depends(get_db), member=Depends(require_org_membership)):
    from app.models.agent_evaluation import AgentEvaluation
    await _owned_agent_for_lifecycle(agent_id,org=org,db=db)
    query=select(AgentEvaluation).where(AgentEvaluation.agent_id==agent_id,AgentEvaluation.organization_id==org.id)
    if q:query=query.where(AgentEvaluation.id.contains(q,autoescape=True) | AgentEvaluation.report['candidate_version'].as_string().contains(q,autoescape=True) | AgentEvaluation.report['suite_digest'].as_string().contains(q,autoescape=True))
    rows=(await db.execute(query.order_by(AgentEvaluation.created_at.desc(),AgentEvaluation.id.desc()).offset(offset).limit(limit+1))).scalars().all()
    from app.services.release_evaluation import review_summaries
    reviews = await review_summaries(db,org.id,[r.id for r in rows[:limit]])
    items=[{'id':r.id,'created_at':r.created_at.isoformat(),**r.report,
            'review':reviews.get(r.id),'review_editable':member.role.value in ('owner','admin')} for r in rows[:limit]]
    return {'items':items,'has_more':len(rows)>limit,'offset':offset,'limit':limit} if paginated else items
