import asyncio
from datetime import datetime,timedelta,timezone
import uuid
import pytest
from app.services.phi_encryption import encrypt_phi, decrypt_phi
from sqlalchemy import select,update
from tests.test_api.test_agent_jobs import setup

@pytest.mark.asyncio
async def test_operations_aggregates_pages_filters_isolation_and_atomic_actions(client,needs_auth,monkeypatch):
    from app.database import AsyncSessionLocal
    from app.middleware.auth import decode_token
    from app.models.run_history import RunHistoryModel as Run
    from app.models.agent_job import AgentJob as Job
    from app.models.organization import OrganizationMember,OrgRole
    from app.models.audit_log import AuditLog
    from app.services.database_tenancy import bind_tenant_to_transaction
    monkeypatch.setattr('app.middleware.rate_limit.GENERAL_LIMIT',200)
    h,aid,org,_=await setup(client,monkeypatch)
    other,other_aid,other_org,_=await setup(client,monkeypatch)
    uid=decode_token(h['Authorization'].split()[1])['sub']
    now=datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        for i in range(25):
            db.add(Run(organization_id=org,user_id=uid if i<24 else 'someone-else',agent_id=aid,run_id='op-'+uuid.uuid4().hex,executed_agent_version='1.0.0',api_client_id='partner-one' if i<10 else None,status='COMPLETED' if i<20 else 'FAILED',error=i>=20,error_reason='model_unavailable' if i>=20 else None,latency_ms=100 if i<20 else 500,tenancy_classification='MODERN',input_text='DO_NOT_RETURN',output_summary='DO_NOT_RETURN',created_at=now.replace(tzinfo=None)))
        db.add(Run(organization_id=org,user_id=uid,agent_id=aid,run_id='hidden-'+uuid.uuid4().hex,tenancy_classification='QUARANTINED',input_text='DO_NOT_RETURN'))
        db.add(Run(organization_id=org,user_id=uid,agent_id=aid,run_id='old-'+uuid.uuid4().hex,tenancy_classification='MODERN',created_at=(now-timedelta(days=100)).replace(tzinfo=None)))
        job=Job(organization_id=org,agent_id=aid,actor_kind='oauth',actor_id='partner-one',idempotency_key=uuid.uuid4().hex,request_digest='a'*64,version='1.0.0',payload=encrypt_phi('DO_NOT_RETURN'),state='queued',notification_state='none')
        db.add(job);await db.commit();jid=job.id
    response=await client.get('/api/operations/overview',headers=h)
    assert response.status_code==200,response.text
    data=response.json();assert data['summary']=={'runs':25,'succeeded':20,'failed':5,'other':0,'success_rate':80.0,'average_latency_ms':180.0}
    assert data['scope']=='organization' and len(data['runs'])==20 and data['runs_more']
    assert data['queue']['queued']==1 and data['failures']==[{'category':'model','count':5}]
    assert 'DO_NOT_RETURN' not in response.text
    second=(await client.get('/api/operations/overview',headers=h,params={'run_offset':20})).json()
    assert len(second['runs'])==5 and not second['runs_more']
    assert not set(r['run_id'] for r in data['runs']) & set(r['run_id'] for r in second['runs'])
    filtered=(await client.get('/api/operations/overview',headers=h,params={'agent_id':aid,'version':'1.0.0','client_id':'partner-one'})).json()
    assert filtered['summary']['runs']==10 and filtered['summary']['success_rate']==100
    failures=(await client.get('/api/operations/overview',headers=h,params={'failures_only':True})).json()
    assert len(failures['runs'])==5 and failures['summary']['runs']==25
    assert (await client.get('/api/operations/overview',headers=other)).json()['summary']['runs']==0
    assert (await client.post(f'/api/operations/jobs/{jid}/cancel',headers=other)).status_code==404
    assert (await client.get('/api/operations/overview',headers=h,params={'days':366})).status_code==422
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        await db.execute(update(OrganizationMember).where(OrganizationMember.organization_id==org,OrganizationMember.user_id==uid).values(role=OrgRole.MEMBER));await db.commit()
    own=(await client.get('/api/operations/overview',headers=h)).json()
    assert own['scope']=='personal' and own['summary']['runs']==24 and own['jobs']==[]
    assert (await client.post(f'/api/operations/jobs/{jid}/cancel',headers=h)).status_code==404
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        await db.execute(update(OrganizationMember).where(OrganizationMember.organization_id==org,OrganizationMember.user_id==uid).values(role=OrgRole.OWNER));await db.commit()
    results=await asyncio.gather(*[client.post(f'/api/operations/jobs/{jid}/cancel',headers=h) for _ in range(2)])
    assert sorted(r.status_code for r in results)==[200,409]
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        saved=await db.get(Job,jid);assert saved.state=='cancelled'
        audit=(await db.execute(select(AuditLog).where(AuditLog.resource_id==jid,AuditLog.action=='agent.operations.cancel'))).scalars().all()
        assert len(audit)==1
    after=(await client.get('/api/operations/overview',headers=h)).json()
    assert after['queue'].get('queued',0)==0 and after['queue']['cancelled']==1 and after['summary']['runs']==25


@pytest.mark.asyncio
async def test_operations_notification_retry_never_reexecutes(client,needs_auth,monkeypatch):
    import json
    from app.database import AsyncSessionLocal
    from app.models.agent_job import AgentJob as Job
    from app.services.database_tenancy import bind_tenant_to_transaction
    h,aid,org,calls=await setup(client,monkeypatch)
    url='https://receiver.example/events'
    monkeypatch.setenv('ICODER_TASK_CALLBACK_URLS',json.dumps({org:[url]}))
    monkeypatch.setenv('ICODER_TASK_CALLBACK_SECRETS',json.dumps({org:'s'*32}))
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        job=Job(organization_id=org,agent_id=aid,actor_kind='oauth',actor_id='partner',idempotency_key=uuid.uuid4().hex,request_digest='a'*64,version='1.0.0',payload=encrypt_phi('PRIVATE'),result=encrypt_phi('UNCHANGED'),state='completed',notification_state='failed',notification_attempts=5,callback_url=url)
        db.add(job);await db.commit();jid=job.id
    assert (await client.post(f'/api/operations/jobs/{jid}/retry-notification',headers=h)).status_code==200
    assert (await client.post(f'/api/operations/jobs/{jid}/retry-notification',headers=h)).status_code==409
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        job=await db.get(Job,jid)
        assert job.state=='completed' and decrypt_phi(job.result)=='UNCHANGED' and job.notification_state=='pending' and job.notification_attempts==0
    assert calls==[]
