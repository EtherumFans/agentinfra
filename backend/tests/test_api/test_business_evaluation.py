import json
import uuid
from types import SimpleNamespace
import pytest
from app.services.business_evaluation import suite_cases
from app.services.release_evaluation import EvaluationCase, EvaluationRequest, check_result


@pytest.mark.parametrize('suite',['documentation-v1','coding-v1','quality-v1'])
def test_business_rules_detect_missing_invented_and_mismatched_fields(suite):
    for raw in suite_cases(suite):
        case=EvaluationCase(**raw)
        response=SimpleNamespace(result={'markdown':json.dumps(case.expected_json,ensure_ascii=False)},run_id='synthetic',executed_agent_version='draft',runtime_mode='test',latency_ms=0,manual_review_required=True,error=False)
        assert check_result(case,response)['passed']
        response.result['markdown']=json.dumps({**case.expected_json,'invented':'unsupported'})
        assert not check_result(case,response)['passed']
        response.result['markdown']='{}'
        assert not check_result(case,response)['passed']
        response.result['markdown']='not JSON'
        assert not check_result(case,response)['passed']
    with pytest.raises(ValueError):
        EvaluationRequest(business_suite=suite,cases=[EvaluationCase(**suite_cases(suite)[0])])


@pytest.mark.asyncio
async def test_fixed_suite_review_gate_failure_isolation_and_model_drift(client,needs_auth,monkeypatch):
    from app.main import app
    from app.database import AsyncSessionLocal
    from app.models.model_connection import ModelConnection
    from app.services.model_connection import encrypt_key
    from app.services.database_tenancy import bind_tenant_to_transaction
    from icoder_runtime.core.llm_gateway import DeepSeekProvider, LLMGateway
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    from icoder_runtime.backends import registry
    calls=[]; mode={'fail':False}
    cases=suite_cases('documentation-v1')
    async def generate(self,**kwargs):
        case=cases[len(calls)%2];calls.append(True)
        return {'content':json.dumps({} if mode['fail'] else case['expected_json'],ensure_ascii=False),
                'model':'deepseek-v4-flash','usage':{'input_tokens':20,'output_tokens':10},'cost_usd':0.00001,'finish_reason':'stop'}
    monkeypatch.setattr(DeepSeekProvider,'generate',generate)
    policy=RuntimeDataPolicy(allow_external_llm=True)
    gateway=LLMGateway(data_policy=policy);gateway.register(DeepSeekProvider(api_key='synthetic',model='deepseek-v4-flash'),default=True)
    monkeypatch.setattr(app.state,'platform_gateway',gateway,raising=False)
    monkeypatch.setattr(app.state,'data_policy',policy,raising=False)
    monkeypatch.setattr(registry,'_GATEWAY_LOOKUP',lambda:gateway)
    monkeypatch.setattr('app.middleware.rate_limit.GENERAL_LIMIT',300)
    async def register():
        name=uuid.uuid4().hex[:12]
        r=await client.post('/api/auth/register',json={'username':name,'email':name+'@example.com','password':'Evaluation!2026','full_name':'Synthetic','organization_name':name})
        assert r.status_code==201,r.text
        from app.middleware.auth import decode_token
        token=r.json()['access_token']
        return {'Authorization':'Bearer '+token},decode_token(token)['org_id']
    headers,org=await register();other,_=await register()
    a=await client.post('/api/rest/v1/agent_definitions',headers=headers,json={'name':'Synthetic business gate','system_prompt':'Return JSON only.','expert_ids':[],'config':{'release_business_suite':'documentation-v1'}})
    aid=a.json()['id'];base='/api/rest/v1/agent_definitions/'+aid
    assert (await client.post(base+'/publish',headers=headers)).status_code==409
    weak = await client.post(base+'/evaluations',headers=headers,json={'cases':[
        {'id':'weak1','text':'synthetic','excludes':['never-present']},
        {'id':'weak2','text':'synthetic','excludes':['never-present']}]})
    assert weak.json()['checks_passed']
    assert (await client.post(base+'/publish',headers=headers)).status_code==409
    r=await client.post(base+'/evaluations',headers=headers,json={'business_suite':'documentation-v1'})
    assert r.status_code==200,r.text
    report=r.json();assert report['checks_passed'],report
    assert all(c['candidate']['real_model_verified'] for c in report['cases'])
    assert (await client.post(base+'/publish',headers=headers)).status_code==409
    url=base+'/evaluations/'+report['id']+'/review'
    assert (await client.post(url,headers=other,json={'decision':'approved','note':'Synthetic review'})).status_code==404
    approved=await client.post(url,headers=headers,json={'decision':'approved','note':'Automated fixture decision; not clinical approval.'})
    assert approved.status_code==200,approved.text
    assert (await client.post(url,headers=headers,json={'decision':'rejected','note':'stale decision'})).status_code==409
    gate=(await client.get(base+'/releases',headers=headers)).json()['evaluation_gate']
    assert gate['can_publish'] and gate['review_required']
    rejected = await client.post(url,headers=headers,json={'decision':'rejected','note':'Synthetic rejection',
        'expected_previous_review_id':approved.json()['id']})
    assert rejected.status_code==200
    assert not (await client.get(base+'/releases',headers=headers)).json()['evaluation_gate']['can_publish']
    accepted = await client.post(url,headers=headers,json={'decision':'approved','note':'Automated fixture decision; not clinical approval.',
        'expected_previous_review_id':rejected.json()['id']})
    assert accepted.status_code==200
    assert (await client.post(base+'/publish',headers=headers)).status_code==200
    # A failed fresh report supersedes earlier passing evidence.
    mode['fail']=True
    failed=await client.post(base+'/evaluations',headers=headers,json={'business_suite':'documentation-v1'})
    assert not failed.json()['checks_passed']
    assert not (await client.get(base+'/releases',headers=headers)).json()['evaluation_gate']['can_publish']
    assert (await client.post(base+'/evaluations/'+failed.json()['id']+'/review',headers=headers,json={'decision':'approved','note':'must fail'})).status_code==409
    # Model configuration changes invalidate existing evidence and approval.
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        db.add(ModelConnection(organization_id=org,model='deepseek-v4-flash',encrypted_key=encrypt_key(org,'synthetic'),enabled=True,version=1));await db.commit()
    gate=(await client.get(base+'/releases',headers=headers)).json()['evaluation_gate']
    assert gate['reason']=='missing_or_stale' and not gate['can_publish']
    history=await client.get(base+'/evaluations',headers=headers)
    accepted=next(r for r in history.json() if r['id']==report['id'])
    assert accepted['review']['note']=='Automated fixture decision; not clinical approval.'
    assert accepted['clinical_approval'] is False
    # Correct text without gateway usage evidence cannot certify a real model.
    from icoder_runtime.backends.pure_llm_provider import PureLLMProvider, LLMResponse
    outputs=iter(cases)
    class NoEvidence:
        async def complete(self,**kwargs):
            return LLMResponse(text=json.dumps(next(outputs)['expected_json'],ensure_ascii=False),finish_reason='stop')
    monkeypatch.setattr(PureLLMProvider,'_resolve_client',lambda self:NoEvidence())
    missing=await client.post(base+'/evaluations',headers=headers,json={'business_suite':'documentation-v1'})
    assert not missing.json()['checks_passed']
    assert all(not c['candidate']['real_model_verified'] for c in missing.json()['cases'])
    from app.models.organization import OrganizationMember, OrgRole
    from sqlalchemy import update
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        await db.execute(update(OrganizationMember).where(OrganizationMember.organization_id==org).values(role=OrgRole.MEMBER));await db.commit()
    assert (await client.post(url,headers=headers,json={'decision':'rejected','note':'no permission'})).status_code==403
