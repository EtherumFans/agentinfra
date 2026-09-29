import asyncio,json,uuid,hmac,hashlib
from datetime import timedelta
import pytest
from sqlalchemy import select,update
from app.services.agent_jobs import AgentJobWorker,now,validate_callback
from app.models.agent_job import AgentJob
from app.services.database_tenancy import bind_tenant_to_transaction

async def setup(client,monkeypatch):
    from icoder_runtime.backends.pure_llm_provider import PureLLMProvider,LLMResponse
    calls=[]
    class Model:
        async def complete(self,**kwargs):
            calls.append(kwargs['system_prompt']);return LLMResponse(text='## Synthetic\n'+kwargs['system_prompt'],finish_reason='stop')
    monkeypatch.setattr(PureLLMProvider,'_resolve_client',lambda self:Model())
    u=uuid.uuid4().hex[:12]
    r=await client.post('/api/auth/register',json={'username':u,'email':u+'@example.com','password':'JobTest!2026','full_name':'Synthetic jobs','organization_name':u})
    assert r.status_code==201,r.text
    h={'Authorization':'Bearer '+r.json()['access_token']}
    a=await client.post('/api/rest/v1/agent_definitions',headers=h,json={'name':'Jobs','system_prompt':'VERSION_ONE','expert_ids':[]})
    aid=a.json()['id'];path='/api/rest/v1/agent_definitions/'+aid
    await client.post(path+'/publish',headers=h)
    from app.database import AsyncSessionLocal
    from app.models.agent import Agent
    async with AsyncSessionLocal() as db:org=(await db.execute(select(Agent.organization_id).where(Agent.id==aid))).scalar_one()
    return h,aid,org,calls

@pytest.mark.asyncio
async def test_durable_batch_pins_version_claims_once_cancels_and_isolates(client,needs_auth,monkeypatch):
    h,aid,org,calls=await setup(client,monkeypatch)
    body={'inputs':[{'text':'Synthetic A'},{'text':'Synthetic B'}],'purpose_of_use':'quality_improvement'}
    headers={**h,'Idempotency-Key':uuid.uuid4().hex}
    url=f'/api/v1/agents/{aid}/jobs'
    submitted=await client.post(url,headers=headers,json=body)
    assert submitted.status_code==202,submitted.text
    jobs=submitted.json()['jobs'];assert len(jobs)==2
    assert 'Synthetic A' not in submitted.text
    replay=await client.post(url,headers=headers,json=body)
    assert {j['id'] for j in replay.json()['jobs']}=={j['id'] for j in jobs}
    assert (await client.post(url,headers=headers,json={**body,'inputs':[{'text':'Changed'}]})).status_code==409
    path='/api/rest/v1/agent_definitions/'+aid
    await client.put(path,headers=h,json={'system_prompt':'VERSION_TWO'});await client.post(path+'/publish',headers=h)
    # New worker instances use only persisted queue state, even after an upgrade.
    worker=AgentJobWorker();other_worker=AgentJobWorker()
    from app.main import app
    worker.app=app;other_worker.app=app
    await asyncio.gather(worker.execute(jobs[0]['id'],org),other_worker.execute(jobs[0]['id'],org))
    completed=await client.get('/api/v1/agent-jobs/'+jobs[0]['id'],headers=h)
    assert completed.json()['state']=='completed',completed.text
    assert completed.json()['result']['executed_agent_version']=='1.0.0'
    assert 'VERSION_ONE' in completed.text
    assert len(calls)==1
    assert (await client.post('/api/v1/agent-jobs/'+jobs[1]['id']+'/cancel',headers=h)).status_code==200
    await worker.execute(jobs[1]['id'],org)
    assert len(calls)==1
    assert (await client.post('/api/v1/agent-jobs/'+jobs[0]['id']+'/cancel',headers=h)).status_code==409
    other,_,_,_=await setup(client,monkeypatch)
    assert (await client.get('/api/v1/agent-jobs/'+jobs[0]['id'],headers=other)).status_code==404
    assert (await client.get('/api/v1/agent-jobs',headers=other)).json()['jobs']==[]

@pytest.mark.asyncio
async def test_notification_retry_signature_and_no_reexecution(client,needs_auth,monkeypatch):
    h,aid,org,calls=await setup(client,monkeypatch)
    callback='https://receiver.example/events';secret='test-only-'+uuid.uuid4().hex
    monkeypatch.setenv('ICODER_TASK_CALLBACK_URLS',json.dumps({org:[callback]}))
    monkeypatch.setenv('ICODER_TASK_CALLBACK_SECRETS',json.dumps({org:secret}))
    body={'inputs':[{'text':'Synthetic private input'}],'purpose_of_use':'quality_improvement','callback_url':callback}
    r=await client.post(f'/api/v1/agents/{aid}/jobs',headers={**h,'Idempotency-Key':uuid.uuid4().hex},json=body)
    assert r.status_code==202,r.text
    jid=r.json()['jobs'][0]['id'];worker=AgentJobWorker()
    from app.main import app
    worker.app=app;await worker.execute(jid,org)
    sent=[]
    async def send(url,payload,signature):
        sent.append(payload);timestamp,mac=signature.split('.')
        assert hmac.compare_digest(mac,hmac.new(secret.encode(),timestamp.encode()+b'.'+payload,hashlib.sha256).hexdigest())
        assert b'Synthetic private input' not in payload and b'VERSION_ONE' not in payload
        return 503 if len(sent)==1 else 204
    monkeypatch.setattr('app.services.agent_jobs.send_notification',send)
    await worker.deliver(jid,org)
    first=(await client.get('/api/v1/agent-jobs/'+jid,headers=h)).json()
    assert first['notification_state']=='pending' and first['notification_attempts']==1
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        await db.execute(update(AgentJob).where(AgentJob.id==jid).values(notification_due=now()-timedelta(seconds=1)));await db.commit()
    await asyncio.gather(worker.deliver(jid,org),AgentJobWorker().deliver(jid,org))
    result=(await client.get('/api/v1/agent-jobs/'+jid,headers=h)).json()
    assert result['notification_state']=='delivered' and result['notification_attempts']==2
    assert len(calls)==1 and len(sent)==2 and sent[0]==sent[1]
    async def reject(*args):return 401
    monkeypatch.setattr('app.services.agent_jobs.send_notification',reject)
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        await db.execute(update(AgentJob).where(AgentJob.id==jid).values(notification_state='pending',notification_due=now()-timedelta(seconds=1)));await db.commit()
    await worker.deliver(jid,org)
    assert (await client.get('/api/v1/agent-jobs/'+jid,headers=h)).json()['notification_state']=='failed'
    assert (await client.post('/api/v1/agent-jobs/'+jid+'/retry-notification',headers=h)).status_code==200
    assert len(calls)==1

    assert (await client.post(f'/api/v1/agents/{aid}/jobs',headers={**h,'Idempotency-Key':uuid.uuid4().hex},json={**body,'callback_url':'https://unregistered.example'})).status_code==422

@pytest.mark.asyncio
async def test_expired_execution_is_not_silently_retried(client,needs_auth,monkeypatch):
    h,aid,org,calls=await setup(client,monkeypatch)
    r=await client.post(f'/api/v1/agents/{aid}/jobs',headers={**h,'Idempotency-Key':uuid.uuid4().hex},json={'inputs':[{'text':'Synthetic'}],'purpose_of_use':'quality_improvement'})
    jid=r.json()['jobs'][0]['id']
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        await db.execute(update(AgentJob).where(AgentJob.id==jid).values(state='running',lease_until=now()-timedelta(seconds=1)));await db.commit()
    worker=AgentJobWorker()
    async def organizations():return [org]
    monkeypatch.setattr(worker,"organizations",organizations)
    await worker.tick();await worker.stop()
    result=(await client.get('/api/v1/agent-jobs/'+jid,headers=h)).json()
    assert result['state']=='interrupted' and result['error_code']=='execution_outcome_unknown'
    assert calls==[]


@pytest.mark.asyncio
async def test_revoked_client_cannot_execute_queued_job(client,needs_auth,monkeypatch):
    h,aid,org,calls=await setup(client,monkeypatch)
    c=await client.post('/api/oauth/clients',headers=h,data={'name':'Queued machine','scopes':'api:write','allowed_agent_ids':aid,'allowed_purposes':'quality_improvement'})
    credentials=c.json()
    t=await client.post('/api/oauth/token',data={'grant_type':'client_credentials','scope':'api:write','client_id':credentials['client_id'],'client_secret':credentials['client_secret']})
    machine={'Authorization':'Bearer '+t.json()['access_token'],'Idempotency-Key':uuid.uuid4().hex}
    r=await client.post(f'/api/v1/agents/{aid}/jobs',headers=machine,json={'inputs':[{'text':'Synthetic'}],'purpose_of_use':'quality_improvement'})
    assert r.status_code==202,r.text
    jid=r.json()['jobs'][0]['id']
    assert (await client.delete('/api/oauth/clients/'+credentials['client_id'],headers=h)).status_code==200
    await AgentJobWorker().execute(jid,org)
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        job=await db.get(AgentJob,jid)
        assert job.state=='failed' and job.error_code=='access_or_configuration_403'
    assert calls==[]

def test_notification_signature_tamper_expiry_and_cross_org_registration(monkeypatch):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('receiver',Path(__file__).resolve().parents[3]/'frontend/public/integration/verify_notification.py')
    receiver=importlib.util.module_from_spec(spec);spec.loader.exec_module(receiver)
    raw=b'{"event_id":"j:terminal","job_id":"j"}';secret='s'*32
    signature='1000.'+hmac.new(secret.encode(),b'1000.'+raw,hashlib.sha256).hexdigest()
    assert receiver.verify_notification(raw,signature,secret,timestamp=1001)['job_id']=='j'
    with pytest.raises(ValueError):receiver.verify_notification(raw+b' ',signature,secret,timestamp=1001)
    with pytest.raises(ValueError):receiver.verify_notification(raw,signature,secret,timestamp=1400)
    monkeypatch.setenv('ICODER_TASK_CALLBACK_URLS',json.dumps({'one':['https://receiver.example/events']}))
    monkeypatch.setenv('ICODER_TASK_CALLBACK_SECRETS',json.dumps({'one':secret}))
    from fastapi import HTTPException
    with pytest.raises(HTTPException):validate_callback('https://receiver.example/events','two')


@pytest.mark.asyncio
async def test_scheduler_rotates_tenants_and_slow_callback_does_not_block(client,needs_auth,monkeypatch):
    monkeypatch.setenv('ICODER_JOB_CONCURRENCY','1')
    first,a,org_a,_=await setup(client,monkeypatch)
    second,b,org_b,_=await setup(client,monkeypatch)
    for headers,aid in [(first,a),(second,b)]:
        response=await client.post(f'/api/v1/agents/{aid}/jobs',headers={**headers,'Idempotency-Key':uuid.uuid4().hex},json={'inputs':[{'text':'Synthetic'}]*3,'purpose_of_use':'quality_improvement'})
        assert response.status_code==202,response.text
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org_a)
        job=(await db.execute(select(AgentJob).where(AgentJob.organization_id==org_a).limit(1))).scalar_one()
        job.state='completed';job.notification_state='pending';job.notification_due=now()
        await db.commit()
    worker=AgentJobWorker();started=[];block=asyncio.Event()
    async def organizations():
        rows=[org_a,org_b] if worker.org_cursor!=org_a else [org_b,org_a]
        worker.org_cursor=rows[0]
        return rows
    monkeypatch.setattr(worker,'organizations',organizations)
    async def execute(jid,org):
        started.append(org)
        async with AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db,org)
            await db.execute(update(AgentJob).where(AgentJob.id==jid).values(state='completed'))
            await db.commit()
    async def notify(jid,org):await block.wait()
    monkeypatch.setattr(worker,'execute',execute);monkeypatch.setattr(worker,'deliver',notify)
    # Waiting callbacks cannot prevent tick from returning or execution in the other tenant.
    for _ in range(8):
        await asyncio.wait_for(worker.tick(),2)
        if worker.tasks:await asyncio.gather(*worker.tasks)
        if set(started)=={org_a,org_b}:break
    assert set(started)=={org_a,org_b}
    assert len(worker.notifications)<=worker.notification_concurrency
    await worker.stop()

@pytest.mark.parametrize('value',['0','33','invalid'])
def test_invalid_worker_capacity_fails_fast(monkeypatch,value):
    monkeypatch.setenv('ICODER_JOB_CONCURRENCY',value)
    with pytest.raises(ValueError):AgentJobWorker()
