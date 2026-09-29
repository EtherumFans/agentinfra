import uuid
from datetime import datetime, timezone
import pytest

@pytest.mark.asyncio
async def test_history_can_retrieve_beyond_old_limits_and_is_tenant_scoped(client, needs_auth, monkeypatch):
    monkeypatch.setattr("app.middleware.rate_limit.GENERAL_LIMIT", 200)
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.agent import Agent
    from app.models.user import User
    from app.models.agent_evaluation import AgentEvaluation
    from app.models.agent_dependency import AgentDependency
    from app.models.agent_job import AgentJob
    from app.services.phi_encryption import encrypt_phi
    from app.services.database_tenancy import bind_tenant_to_transaction
    async def register():
        uid=uuid.uuid4().hex[:12]
        r=await client.post('/api/auth/register',json={'username':uid,'email':uid+'@example.com','password':'History!2026','full_name':'Synthetic','organization_name':uid})
        return uid,{'Authorization':'Bearer '+r.json()['access_token']}
    uid,h=await register()
    _,other=await register()
    created=await client.post('/api/rest/v1/agent_definitions',headers=h,json={'name':'History','system_prompt':'Test','expert_ids':[]})
    aid=created.json()['id'];path='/api/rest/v1/agent_definitions/'+aid
    async with AsyncSessionLocal() as db:
        agent=(await db.execute(select(Agent).where(Agent.id==aid))).scalar_one()
        await bind_tenant_to_transaction(db,agent.organization_id)
        user=(await db.execute(select(User).where(User.username==uid))).scalar_one()
        timestamp=datetime.now(timezone.utc)
        for i in range(105):
            db.add(AgentJob(organization_id=agent.organization_id,agent_id=aid,actor_kind='user',actor_id=str(user.id),idempotency_key=f'history-{i}:0',request_digest='0'*64,version='1.0.0',payload=encrypt_phi('{}'),state='completed',created_at=timestamp))
        for i in range(35):
            db.add(AgentEvaluation(organization_id=agent.organization_id,agent_id=aid,created_by=str(user.id),created_at=timestamp,report={'candidate_version':'draft','suite_digest':f'suite-{i}'}))
        for i in range(305):
            db.add(AgentDependency(organization_id=agent.organization_id,created_by=str(user.id),kind='tool',name=f'tool-{i:03}',version='1',created_at=timestamp))
        await db.commit()
    async def collect(url,field,expected,extra=None):
        ids=[]
        for offset in range(0,expected,20):
            r=await client.get(url,headers=h,params={'limit':20,'offset':offset,**(extra or {})})
            assert r.status_code==200,r.text
            data=r.json();rows=data[field]
            ids.extend(row.get('id',row.get('name')) for row in rows)
            assert data['has_more']==(offset+20<expected)
        assert len(ids)==expected and len(set(ids))==expected
    await collect('/api/v1/agent-jobs','jobs',105,{'agent_id':aid})
    await collect(path+'/evaluations','items',35,{'paginated':True})
    await collect(path+'/dependencies','registry',305,{'current_only':True})
    found=await client.get(path+'/dependencies',headers=h,params={'q':'tool-304','current_only':True})
    assert [r['name'] for r in found.json()['registry']]==['tool-304']
    assert not (await client.get(path+'/dependencies',headers=h,params={'q':'%'})).json()['registry']
    assert not (await client.get('/api/v1/agent-jobs',headers=h,params={'agent_id':aid,'state':'failed'})).json()['jobs']
    assert (await client.get(path+'/evaluations',headers=h,params={'limit':101})).status_code==422
    assert (await client.get(path+'/evaluations',headers=other)).status_code==404
    assert (await client.get(path+'/dependencies',headers=other)).status_code==404
    assert not (await client.get('/api/v1/agent-jobs',headers=other,params={'agent_id':aid})).json()['jobs']
