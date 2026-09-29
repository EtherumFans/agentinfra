import uuid
import pytest
from app.services.release_evaluation import EvaluationRequest, EvaluationCase, check_result
from types import SimpleNamespace

@pytest.mark.parametrize('cases', [[],[{'id':'x','text':'synthetic'}],
    [{'id':'x','text':'synthetic','contains':['']}],
    [{'id':'x','text':'a','contains':['a']}]*2])
def test_invalid_suite_rejected(cases):
    with pytest.raises(ValueError):EvaluationRequest(baseline_version='1.0.0',cases=cases)

def test_exact_fields_and_failure_do_not_pass():
    c=EvaluationCase(id='x',text='synthetic',expected_fields={'nested.code':'A'},contains=['A'],excludes=['invented'])
    r=SimpleNamespace(result={'nested':{'code':'A'}},run_id='r',executed_agent_version='1',runtime_mode='test',latency_ms=1,manual_review_required=True,error=False)
    assert check_result(c,r)['passed']
    r.error=True
    assert not check_result(c,r)['passed']

@pytest.mark.asyncio
async def test_real_versions_regression_report_persistence_and_tenant_isolation(client,needs_auth,monkeypatch):
    from icoder_runtime.backends.pure_llm_provider import PureLLMProvider, LLMResponse
    drift={'agent_id':None}
    class Model:
        async def complete(self,**kwargs):
            if drift['agent_id']:
                from app.database import AsyncSessionLocal
                from app.models.agent import Agent
                from sqlalchemy import update, select
                from app.services.database_tenancy import bind_tenant_to_transaction
                aid=drift['agent_id'];drift['agent_id']=None
                async with AsyncSessionLocal() as db:
                    tenant=(await db.execute(select(Agent.organization_id).where(Agent.id==aid))).scalar_one()
                    await bind_tenant_to_transaction(db,tenant)
                    await db.execute(update(Agent).where(Agent.id==aid).values(system_prompt='CONCURRENT_CHANGE'))
                    await db.commit()
            return LLMResponse(text='## Result\n'+('EXPECTED' if 'BASELINE' in kwargs['system_prompt'] else 'REGRESSION'),finish_reason='stop')
    monkeypatch.setattr(PureLLMProvider,'_resolve_client',lambda self:Model())
    async def register():
        u=uuid.uuid4().hex[:12]
        r=await client.post('/api/auth/register',json={'username':u,'email':u+'@example.com','password':'Evaluate!2026','full_name':'Synthetic evaluator','organization_name':u})
        assert r.status_code==201,r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}
    h=await register()
    r=await client.post('/api/rest/v1/agent_definitions',headers=h,json={'name':'Evaluation proof','system_prompt':'BASELINE','expert_ids':[]})
    assert r.status_code==200,r.text
    path='/api/rest/v1/agent_definitions/'+r.json()['id']
    assert (await client.post(path+'/publish',headers=h)).status_code==200
    await client.put(path,headers=h,json={'system_prompt':'CANDIDATE'})
    body={'baseline_version':'1.0.0','cases':[{'id':'facts','text':'Synthetic only','contains':['EXPECTED'],'excludes':['REGRESSION']}]}
    report=await client.post(path+'/evaluations',headers=h,json=body)
    assert report.status_code==200,report.text
    data=report.json()
    assert data['regressions']==1
    assert data['candidate_passed']==0
    assert data['consistent'] is True
    assert data['clinical_approval'] is False
    assert data['cases'][0]['baseline']['executed_version']=='1.0.0'
    assert data['cases'][0]['candidate']['executed_version']=='draft'
    assert 'Synthetic only' not in report.text
    history=await client.get(path+'/evaluations',headers=h)
    assert history.json()[0]['id']==data['id']
    drift['agent_id']=r.json()['id']
    changed=await client.post(path+'/evaluations',headers=h,json=body)
    assert changed.status_code==200,changed.text
    assert changed.json()['consistent'] is False
    assert changed.json()['checks_passed'] is False
    other=await register()
    assert (await client.get(path+'/evaluations',headers=other)).status_code==404
    assert (await client.post(path+'/evaluations',headers=other,json=body)).status_code==404
    assert (await client.post(path+'/evaluations',headers=h,json={**body,'baseline_version':'9.0.0'})).status_code==404
    await client.post(path+'/archive',headers=h)
    assert (await client.post(path+'/evaluations',headers=h,json=body)).status_code==409


def test_missing_field_does_not_match_null():
    case=EvaluationCase(id='missing',text='synthetic',expected_fields={'absent':None})
    response=SimpleNamespace(result={},run_id='r',executed_agent_version='1',runtime_mode='test',latency_ms=1,manual_review_required=True,error=False)
    assert not check_result(case,response)['passed']


@pytest.mark.asyncio
async def test_required_publication_uses_latest_matching_evidence(client, needs_auth, monkeypatch):
    from icoder_runtime.backends.pure_llm_provider import PureLLMProvider, LLMResponse
    class Model:
        async def complete(self, **kwargs):
            return LLMResponse(text='EXPECTED', finish_reason='stop')
    monkeypatch.setattr(PureLLMProvider, '_resolve_client', lambda self: Model())
    uid=uuid.uuid4().hex[:12]
    auth=await client.post('/api/auth/register',json={'username':uid,'email':uid+'@example.com','password':'Evaluate!2026','full_name':'Synthetic','organization_name':uid})
    h={'Authorization':'Bearer '+auth.json()['access_token']}
    created=await client.post('/api/rest/v1/agent_definitions',headers=h,json={'name':'Gate','system_prompt':'Test','expert_ids':[], 'config':{'release_evaluation_required_for':['quality_improvement']}})
    path='/api/rest/v1/agent_definitions/'+created.json()['id']
    assert (await client.post(path+'/publish',headers=h)).status_code==409
    suite={'cases':[{'id':'one','text':'Synthetic','contains':['EXPECTED']}]}
    report=await client.post(path+'/evaluations',headers=h,json=suite)
    assert report.status_code==200,report.text
    assert report.json()['checks_passed']
    assert (await client.get(path+'/releases',headers=h)).json()['evaluation_gate']['passed']
    assert (await client.post(path+'/publish',headers=h)).status_code==200
    release=(await client.get(path+'/releases',headers=h)).json()['releases'][0]
    assert release['evaluation_evidence']['evaluation_id']==report.json()['id']
    await client.put(path,headers=h,json={'system_prompt':'Changed'})
    assert (await client.post(path+'/publish',headers=h)).status_code==409
    good=await client.post(path+'/evaluations',headers=h,json=suite)
    assert good.json()['checks_passed']
    failed=await client.post(path+'/evaluations',headers=h,json={'cases':[{'id':'bad','text':'Synthetic','contains':['ABSENT']}]})
    assert not failed.json()['checks_passed']
    assert (await client.post(path+'/publish',headers=h)).status_code==409
    # Another purpose cannot supply the missing quality-improvement evidence.
    other=await client.post(path+'/evaluations',headers=h,json={**suite,'purpose_of_use':'research'})
    assert other.status_code==200,other.text
    assert (await client.post(path+'/publish',headers=h)).status_code==409
    assert (await client.post(path+'/version',headers=h)).status_code==409

    # Registry changes invalidate an otherwise passing draft report.
    dep={'kind':'tool','name':'gate-tool','version':'one'}
    assert (await client.post(path+'/dependencies/register',headers=h,json=dep)).status_code==200
    await client.put(path+'/dependencies/bindings',headers=h,json={'bindings':[{'kind':'tool','name':'gate-tool'}]})
    fresh=await client.post(path+'/evaluations',headers=h,json=suite)
    assert fresh.json()['checks_passed']
    await client.post(path+'/dependencies/register',headers=h,json={**dep,'version':'two'})
    assert (await client.post(path+'/publish',headers=h)).status_code==409
    # Resolved runtime configuration changes also invalidate evidence without a prompt edit.
    import app.services.agent_runtime_pack as packs
    original=packs.pack_from_tenant_agent
    await client.post(path+'/evaluations',headers=h,json=suite)
    async def changed_pack(*args,**kwargs):
        return {**await original(*args,**kwargs),'synthetic_resolved_revision':'new'}
    monkeypatch.setattr(packs,'pack_from_tenant_agent',changed_pack)
    assert (await client.post(path+'/publish',headers=h)).status_code==409


@pytest.mark.parametrize('policy',[True,'research',['unknown'],[{}]])
def test_invalid_release_policy_rejected(policy):
    from app.api.agents import AgentUpdate
    with pytest.raises(ValueError):AgentUpdate(config={'release_evaluation_required_for':policy})
