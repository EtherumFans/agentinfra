import asyncio
import json
import uuid
import pytest
from icoder_runtime.observability.model_usage import collect_model_usage, record_model_usage, model_usage_snapshot


@pytest.mark.asyncio
async def test_accumulates_rounds_preserves_unknown_and_isolates_concurrent_runs():
    @collect_model_usage
    async def run(label):
        record_model_usage('deepseek', {'model':label,'usage':{'input_tokens':10,'output_tokens':0},'cost_usd':0})
        await asyncio.sleep(0)
        record_model_usage('deepseek', {'model':label,'usage':{'input_tokens':5,'output_tokens':7},'cost_usd':0.0001,'content':'PRIVATE'})
        return model_usage_snapshot()
    a,b = await asyncio.gather(run('model-a'),run('model-b'))
    assert a['calls']==2 and a['input_tokens']==15 and a['output_tokens']==7
    assert a['cost_complete'] and a['usage_complete']
    assert a['models'][0]['model']=='model-a' and b['models'][0]['model']=='model-b'
    assert 'PRIVATE' not in json.dumps(a)
    assert model_usage_snapshot() is None
    @collect_model_usage
    async def incomplete():
        record_model_usage('deepseek', {'degraded':True,'is_mock':True,'usage':{'input_tokens':0,'output_tokens':0},'cost_usd':0})
        record_model_usage('other', {'model':'real','usage':{'input_tokens':0,'output_tokens':0},'cost_usd':0})
        record_model_usage('mock', {'usage':{'input_tokens':999},'cost_usd':1})
        return model_usage_snapshot()
    partial = await incomplete()
    assert partial['calls']==2 and partial['estimated_cost_usd']==0
    assert partial['input_tokens']==0 and not partial['cost_complete'] and not partial['usage_complete']
    assert partial['models'][0]['input_tokens'] is None


@pytest.mark.asyncio
async def test_gateway_stream_records_terminal_once():
    from icoder_runtime.core.llm_gateway import LLMGateway, BaseLLMProvider
    class Provider(BaseLLMProvider):
        name = 'synthetic-provider'
        async def generate(self, **kwargs):
            return {'model':'synthetic','content':'OK','usage':{'input_tokens':2,'output_tokens':1},'cost_usd':0.01}
        async def generate_stream(self, **kwargs):
            yield {'type':'text_delta','delta':'O'}
            yield {'type':'text_delta','delta':'K'}
            yield {'type':'completed','result':await self.generate()}
    @collect_model_usage
    async def run():
        gateway = LLMGateway();gateway.register(Provider(),default=True)
        _ = [event async for event in gateway.generate_stream(messages=[])]
        return model_usage_snapshot()
    usage = await run()
    assert usage['calls']==1 and usage['input_tokens']==2 and usage['output_tokens']==1


@pytest.mark.asyncio
async def test_operational_usage_coverage_and_persistence(client,needs_auth,monkeypatch):
    from tests.test_api.test_agent_jobs import setup
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel as Run
    from app.services.database_tenancy import bind_tenant_to_transaction
    from app.api.agent_run import AgentRunResponse, _persist_run_history
    from datetime import datetime, timezone
    from sqlalchemy import select
    h,aid,org,_ = await setup(client,monkeypatch)
    other,_,_,_ = await setup(client,monkeypatch)
    recorded_id = 'usage-recorded-' + uuid.uuid4().hex
    legacy_id = 'usage-legacy-' + uuid.uuid4().hex
    @collect_model_usage
    async def persist():
        record_model_usage('deepseek',{'model':'deepseek-v4-flash','usage':{'input_tokens':10,'output_tokens':4},'cost_usd':0.001})
        async with AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db,org)
            await _persist_run_history(db,response=AgentRunResponse(agent_id=aid,run_id=recorded_id,trace_id='usage-trace',runtime_mode='pure_llm'),input_text='SYNTHETIC_PRIVATE',user_id='',tenant_id=org,organization_id=org)
            row=(await db.execute(select(Run).where(Run.run_id==recorded_id))).scalar_one()
            row.tenancy_classification='MODERN'
            db.add(Run(organization_id=org,agent_id=aid,run_id=legacy_id,created_at=datetime.now(timezone.utc).replace(tzinfo=None),tenancy_classification='MODERN'))
            await db.commit()
    await persist()
    r=await client.get('/api/operations/overview',headers=h)
    assert r.status_code==200,r.text
    usage=r.json()['model_usage']
    assert usage['recorded_runs']==1 and usage['unrecorded_runs']==1
    assert usage['input_tokens']==10 and usage['output_tokens']==4 and usage['estimated_cost_usd']==0.001
    assert usage['complete_usage_runs']==1 and usage['complete_cost_runs']==1
    assert 'SYNTHETIC_PRIVATE' not in r.text
    assert (await client.get('/api/operations/overview',headers=other)).json()['model_usage']['estimated_cost_usd'] is None
    assert (await client.get('/api/operations/overview',headers=h,params={'agent_id':'missing'})).json()['model_usage']['calls'] is None
