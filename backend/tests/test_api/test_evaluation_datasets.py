import asyncio
import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select,update,text
from app.models.evaluation_dataset import EvaluationBatchItem as Item,EvaluationDataset as Dataset,now
from app.services.database_tenancy import bind_tenant_to_transaction

async def setup(client,monkeypatch,count=12):
    from icoder_runtime.backends.pure_llm_provider import PureLLMProvider,LLMResponse
    from app.middleware.auth import decode_token
    calls=[]
    class Model:
        async def complete(self,**kwargs):
            from app.services.tenant_model_routing import current_request_tenant
            assert current_request_tenant()==org
            calls.append(True);return LLMResponse(text='{"ok":true}',finish_reason='stop')
    monkeypatch.setattr(PureLLMProvider,'_resolve_client',lambda self:Model())
    monkeypatch.setattr('app.middleware.rate_limit.GENERAL_LIMIT',500)
    async def register():
        name=uuid.uuid4().hex[:12]
        r=await client.post('/api/auth/register',json={'username':name,'email':name+'@example.com','password':'DatasetTest!2026','full_name':'Synthetic','organization_name':name})
        assert r.status_code==201,r.text
        token=r.json()['access_token'];return {'Authorization':'Bearer '+token},decode_token(token)['org_id']
    h,org=await register();other,_=await register()
    agent=await client.post('/api/rest/v1/agent_definitions',headers=h,json={'name':'Batch fixture','system_prompt':'Return JSON only','config':{'release_evaluation_required_for':['*']}})
    aid=agent.json()['id']
    cases=[{'id':f'case-{i}','text':'Synthetic only','expected_json':{'ok':i!=count-1}} for i in range(count)]
    d=await client.post('/api/evaluation-datasets',headers=h,json={'name':'Synthetic version','split':'validation','cases':cases})
    assert d.status_code==200,d.text
    return h,other,org,aid,d.json(),calls

async def approve(client,h,d):
    r=await client.post('/api/evaluation-datasets/'+d['id']+'/review',headers=h,json={'decision':'approved','note':'Automated synthetic fixture, not clinical approval','expected_reviews':0})
    assert r.status_code==200,r.text

async def start(client,h,aid,d):
    body={'agent_id':aid,'request_id':uuid.uuid4().hex}
    url='/api/evaluation-datasets/'+d['id']+'/batches'
    r=await client.post(url,headers=h,json=body);assert r.status_code==200,r.text
    assert (await client.post(url,headers=h,json=body)).json()['id']==r.json()['id']
    return url+'/'+r.json()['id'],r.json()['id']

async def items(org,bid):
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        return list((await db.execute(select(Item).where(Item.batch_id==bid,Item.organization_id==org).order_by(Item.case_index))).scalars())

@pytest.mark.asyncio
async def test_dataset_versions_review_encryption_and_tenant_scope(client,needs_auth,monkeypatch):
    h,other,org,aid,d,calls=await setup(client,monkeypatch)
    base='/api/evaluation-datasets/'+d['id']
    assert (await client.get(base,headers=other)).status_code==404
    assert (await client.post(base+'/review',headers=other,json={'decision':'approved','note':'x','expected_reviews':0})).status_code==404
    assert (await client.post(base+'/batches',headers=h,json={'agent_id':aid,'request_id':'pending'})).status_code==409
    await approve(client,h,d)
    assert (await client.post(base+'/review',headers=h,json={'decision':'rejected','note':'stale','expected_reviews':0})).status_code==409
    added=await client.post('/api/evaluation-datasets',headers=h,json={'name':d['name'],'split':'acceptance','dataset_id':d['dataset_id'],'expected_version':1,'append':True,'cases':[{'id':'new','text':'Synthetic','contains':['ok']}]})
    assert added.status_code==200,added.text
    assert added.json()['case_count']==13 and added.json()['version']==2 and added.json()['review_status']=='pending'
    old=(await client.get(base,headers=h)).json();assert old['case_count']==12 and old['review_status']=='approved'
    assert (await client.get(base,headers=h,params={'offset':10,'limit':1})).json()['cases'][0]['id']=='case-10'
    from app.database import AsyncSessionLocal,engine
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        raw=(await db.execute(text('SELECT cases FROM evaluation_datasets WHERE id=:id'),{'id':d['id']})).scalar_one()
        if engine.dialect.name=='postgresql':assert raw.startswith('v') and 'Synthetic' not in raw
    assert not calls
    from tests.test_api.test_evaluation_import import workbook
    content=workbook([[f'private-{i}','Synthetic','I10.x00','N18.810+D63.8*;B44.100x004+J99.8*',None,None] for i in range(12)])
    imported=await client.post('/api/evaluation-datasets/import-xlsx',headers=h,data={'name':'Full import','split':'training'},files={'file':('synthetic.xlsx',content)})
    assert imported.status_code==200 and imported.json()['case_count']==12 and imported.json()['review_status']=='pending'
    saved=(await client.get('/api/evaluation-datasets/'+imported.json()['id'],headers=h)).json()
    assert saved['cases'][0]['expected_json']['other_diagnosis_codes']==['N18.810+D63.8*','B44.100x004+J99.8*']

@pytest.mark.asyncio
async def test_batch_more_than_ten_atomic_claim_summary_and_checks_not_retried(client,needs_auth,monkeypatch):
    h,other,org,aid,d,calls=await setup(client,monkeypatch)
    await approve(client,h,d);url,bid=await start(client,h,aid,d)
    from app.services.evaluation_batch_worker import EvaluationBatchWorker
    from app.main import app
    w=EvaluationBatchWorker();w.app=app
    rows=await items(org,bid)
    await asyncio.gather(w.execute(rows[0].id,org),w.execute(rows[0].id,org))
    assert len(calls)==1
    gate=(await client.get('/api/rest/v1/agent_definitions/'+aid+'/releases',headers=h)).json()['evaluation_gate']
    assert not gate['can_publish'] and gate['evaluation_id'] is None
    for row in rows[1:]:await w.execute(row.id,org)
    report=(await client.get(url,headers=h)).json()
    assert report['total']==12 and report['states']['completed']==12 and report['passed']==11
    assert report['field_matches']['ok']=={'matched':11,'checked':12}
    assert len((await client.get(url,headers=h,params={'failed_only':True})).json()['items'])==1
    assert (await client.get(url,headers=other)).status_code==404
    assert (await client.post(url+'/retry',headers=h)).status_code==200
    assert all(r.state=='completed' for r in await items(org,bid))

@pytest.mark.asyncio
async def test_cancel_drift_and_expired_lease_recovery(client,needs_auth,monkeypatch):
    h,other,org,aid,d,calls=await setup(client,monkeypatch,3)
    await approve(client,h,d);url,bid=await start(client,h,aid,d)
    assert (await client.post(url+'/cancel',headers=h)).status_code==200
    from app.services.evaluation_batch_worker import EvaluationBatchWorker
    from app.main import app
    w=EvaluationBatchWorker();w.app=app
    for row in await items(org,bid):await w.execute(row.id,org)
    assert not calls and all(r.state=='cancelled' for r in await items(org,bid))
    assert (await client.post(url+'/retry',headers=h)).status_code==409

@pytest.mark.asyncio
async def test_retry_preserves_attempts_and_cancel_allows_running_item_to_finish(client,needs_auth,monkeypatch):
    h,other,org,aid,d,calls=await setup(client,monkeypatch,2)
    await approve(client,h,d);url,bid=await start(client,h,aid,d)
    from app.services.evaluation_batch_worker import EvaluationBatchWorker
    from app.main import app
    from app.api import agent_evaluations
    w=EvaluationBatchWorker();w.app=app;rows=await items(org,bid)
    original=agent_evaluations.evaluate_agent_releases
    async def timeout(*args,**kwargs):raise asyncio.TimeoutError()
    monkeypatch.setattr(agent_evaluations,'evaluate_agent_releases',timeout)
    await w.execute(rows[0].id,org)
    assert (await items(org,bid))[0].state=='interrupted'
    monkeypatch.setattr(agent_evaluations,'evaluate_agent_releases',original)
    assert (await client.post(url+'/retry',headers=h)).status_code==200
    await w.execute(rows[0].id,org)
    first=(await items(org,bid))[0]
    assert first.state=='completed' and len(first.attempts)==4
    from app.services.tenant_model_routing import current_request_tenant
    assert current_request_tenant()!=org
    url,bid=await start(client,h,aid,d);rows=await items(org,bid)
    entered=asyncio.Event();release=asyncio.Event()
    async def wait_then_evaluate(*args,**kwargs):entered.set();await release.wait();return await original(*args,**kwargs)
    monkeypatch.setattr(agent_evaluations,'evaluate_agent_releases',wait_then_evaluate)
    task=asyncio.create_task(w.execute(rows[0].id,org));await asyncio.wait_for(entered.wait(),10)
    assert (await client.post(url+'/cancel',headers=h)).status_code==200
    release.set();await task
    states=[r.state for r in await items(org,bid)]
    assert states==['completed','cancelled']
    calls.clear()
    url,bid=await start(client,h,aid,d);rows=await items(org,bid)
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        await db.execute(update(Item).where(Item.id==rows[0].id).values(state='running',claim_token='old',lease_until=now()-timedelta(seconds=5)));await db.commit()
    # A new worker discovers the expired attempt; it does not replay it automatically.
    async def orgs():return [org]
    w.organizations=orgs;w.concurrency=0
    await w.tick()
    assert (await items(org,bid))[0].state=='interrupted'
    assert (await client.post(url+'/retry',headers=h)).status_code==200
    await w.finish_item(rows[0].id,org,'old','completed',{'checks_passed':True},None)
    assert (await items(org,bid))[0].state=='queued'
    await client.put('/api/rest/v1/agent_definitions/'+aid,headers=h,json={'system_prompt':'Changed'})
    await w.execute(rows[0].id,org)
    assert all(r.state=='failed' for r in await items(org,bid)) and not calls
    assert (await client.post(url+'/retry',headers=h)).status_code==409
