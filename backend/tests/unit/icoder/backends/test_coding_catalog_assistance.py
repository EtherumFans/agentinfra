import json
import pytest
from app.services import coding_catalog_assistance as c
from icoder_runtime.backends import AgentRunContext, BackendRequest
from icoder_runtime.backends.pure_llm_provider import PureLLMProvider, LLMResponse

@pytest.fixture
def catalog(monkeypatch):
    data={'diagnosis':{'A01.001':'合成诊断甲','B02':'合成诊断乙'},'procedure':{'01.01':'合成手术甲'}}
    monkeypatch.setattr(c,'catalogs',lambda:data)
    return data

def test_retrieval_is_bounded_and_does_not_invent_codes(catalog):
    found=c.candidates('记录：合成诊断甲。',catalog['diagnosis'],limit=1)
    assert found==[{'code':'A01.001','name':'合成诊断甲'}]
    assert c.candidates('',catalog['diagnosis'])==[]

def test_binding_and_membership_preserve_compound_and_unknown(catalog):
    with pytest.raises(ValueError):c.profile({'coding_catalog_assistance':'unknown'})
    with pytest.raises(ValueError):c.augment('合成资料',{'profile':c.PROFILE,'catalog_release':'old'})
    value={'primary_diagnosis_code':'A01.001+B02*','other_diagnosis_codes':['A01'], 'primary_procedure_code':None,'other_procedure_codes':[]}
    result=c.validate_output(json.dumps(value))
    assert result['fields']['primary_diagnosis_code']['unknown']==0
    assert result['fields']['other_diagnosis_codes']['unknown']==1
    assert not result['clinical_validity_verified']
    assert c.validate_output('broken')['status']=='invalid_json'

@pytest.mark.asyncio
async def test_invoke_and_stream_share_assistance_without_altering_output(catalog):
    output=json.dumps({'primary_diagnosis_code':'A01.001','other_diagnosis_codes':[], 'primary_procedure_code':None,'other_procedure_codes':[]})
    class Client:
        calls=[]
        async def complete(self,**kwargs):
            self.calls.append(kwargs)
            return LLMResponse(text=output,finish_reason='stop')
        async def stream(self,**kwargs):
            raise AssertionError('assisted coding must validate final output first')
            yield
    client=Client();provider=PureLLMProvider(llm_client=client)
    ctx=AgentRunContext(run_id='r',context_id='c',agent_id='a',agent_pack={'coding_catalog_assistance':c.profile({'coding_catalog_assistance':c.PROFILE})})
    req=BackendRequest(user_input='合成诊断甲')
    result=await provider.invoke(req,ctx)
    assert result.markdown==output
    assert 'A01.001' in client.calls[0]['user_input']
    assert 'coding_validation' in result.raw_provider_response
    events=[e async for e in provider.stream(req,ctx)]
    assert events[0]['payload'].markdown==output
    assert len(client.calls)==2

@pytest.mark.asyncio
async def test_unconfigured_agent_is_unchanged(catalog):
    class Client:
        async def complete(self,**kwargs):
            assert kwargs['user_input']=='合成诊断甲'
            return LLMResponse(text='unchanged',finish_reason='stop')
    ctx=AgentRunContext(run_id='r',context_id='c',agent_id='a')
    result=await PureLLMProvider(llm_client=Client()).invoke(BackendRequest(user_input='合成诊断甲'),ctx)
    assert 'coding_validation' not in result.raw_provider_response

@pytest.mark.asyncio
async def test_stale_catalog_binding_fails_before_model_call(catalog):
    class Client:
        async def complete(self,**kwargs):
            raise AssertionError('stale binding must not call the model')
    ctx=AgentRunContext(run_id='r',context_id='c',agent_id='a',agent_pack={'coding_catalog_assistance':{'profile':c.PROFILE,'catalog_release':'old'}})
    result=await PureLLMProvider(llm_client=Client()).invoke(BackendRequest(user_input='合成资料'),ctx)
    assert result.finish_state=='failed'

def test_agent_pack_binds_opt_in_and_config_validation():
    from app.models.agent import Agent
    from app.services.agent_runtime_pack import pack_from_db_agent
    from app.services.release_evaluation import validate_release_policy
    agent=Agent(id='synthetic',name='synthetic',config={})
    assert 'coding_catalog_assistance' not in pack_from_db_agent(agent)
    agent.config={'coding_catalog_assistance':c.PROFILE,'release_evaluation_required_for':['*']}
    assert pack_from_db_agent(agent)['coding_catalog_assistance']['catalog_release']==c.CATALOG_RELEASE
    assert validate_release_policy(agent.config)['release_evaluation_required_for']==['*']
    with pytest.raises(ValueError):validate_release_policy({'coding_catalog_assistance':'untrusted'})
