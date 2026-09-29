import uuid
import pytest
from app.services.database_tenancy import bind_tenant_to_transaction
from app.middleware.auth import decode_token


@pytest.mark.asyncio
async def test_draft_publish_pinned_versions_rollback_and_tenant_isolation(client, needs_auth, monkeypatch):
    from icoder_runtime.backends.pure_llm_provider import PureLLMProvider, LLMResponse
    class Model:
        async def complete(self, **kwargs):
            marker = next((x for x in ('RELEASE_ONE','RELEASE_TWO','RELEASE_THREE') if x in kwargs['system_prompt']), 'UNKNOWN')
            return LLMResponse(text=f'## Synthetic\n{marker}',finish_reason='stop')
    monkeypatch.setattr(PureLLMProvider,'_resolve_client',lambda self:Model())
    async def register():
        suffix=uuid.uuid4().hex[:12]
        r=await client.post('/api/auth/register',json={'username':suffix,'email':suffix+'@example.com',
            'password':'ReleaseTest!2026','full_name':'Synthetic release user','organization_name':suffix})
        assert r.status_code==201,r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}
    h=await register()
    org_id=decode_token(h['Authorization'].split(' ',1)[1])['org_id']
    r=await client.post('/api/rest/v1/agent_definitions',headers=h,json={'name':'Release proof','system_prompt':'RELEASE_ONE','expert_ids':[]})
    assert r.status_code==200,r.text
    agent=r.json(); aid=agent['id']; path='/api/rest/v1/agent_definitions/'+aid
    assert agent['status']=='draft'
    async def run(binding=None, preview=False, headers=None):
        body={'input':{'text':'Synthetic data only'},'purpose_of_use':'quality_improvement','preview_draft':preview}
        if binding: body.update(expected_agent_version=binding['version'],expected_configuration_digest=binding['configuration_digest'])
        return await client.post('/api/v1/agents/'+aid+'/run',headers=headers or h,json=body)
    assert (await run()).json()['error_reason']=='agent_not_published'
    draft=await run(preview=True)
    assert draft.status_code==200,draft.text
    assert draft.json()['draft_preview'] is True
    from app.database import AsyncSessionLocal
    from app.models.run_history import RunHistoryModel
    from app.api.run_trace import _build_run_summary
    from sqlalchemy import select
    async with AsyncSessionLocal() as check_db:
        await bind_tenant_to_transaction(check_db,org_id)
        saved = (await check_db.execute(select(RunHistoryModel).where(RunHistoryModel.run_id == draft.json()['run_id']))).scalar_one()
        assert saved.executed_agent_version == 'draft'
        assert saved.draft_preview is True
        assert saved.manual_review_required == draft.json()['manual_review_required']
        assert _build_run_summary(saved, [])['executed_agent_version'] == 'draft'
    assert 'RELEASE_ONE' in draft.text
    p=await client.post(path+'/publish',headers=h)
    assert p.status_code==200,p.text
    v1=(await client.get(path+'/integration',headers=h)).json()
    assert v1['version']=='1.0.0'
    assert v1['binding_mode']=='published_snapshot'
    await client.put(path,headers=h,json={'system_prompt':'RELEASE_TWO'})
    assert 'RELEASE_ONE' in (await run(v1)).text
    assert 'RELEASE_ONE' in (await run()).text
    assert 'RELEASE_TWO' in (await run(preview=True)).text
    published=await client.post(path+'/publish',headers=h)
    assert published.json()['version']=='1.0.1',published.text
    v2=(await client.get(path+'/integration',headers=h)).json()
    keyed = {**h, 'Idempotency-Key':uuid.uuid4().hex}
    first = await run(v1, headers=keyed)
    replay = await run(v1, headers=keyed)
    assert first.json()['run_id'] == replay.json()['run_id']
    assert (await run(v2, headers=keyed)).status_code == 409
    assert 'RELEASE_TWO' in (await run(v2)).text
    assert 'RELEASE_ONE' in (await run(v1)).text
    assert (await run(v1)).json()['executed_agent_version']=='1.0.0'
    pinned = await run(v1)
    async with AsyncSessionLocal() as check_db:
        await bind_tenant_to_transaction(check_db,org_id)
        saved = (await check_db.execute(select(RunHistoryModel).where(RunHistoryModel.run_id == pinned.json()['run_id']))).scalar_one()
        assert saved.executed_agent_version == '1.0.0'
        assert saved.draft_preview is False
    old=(await client.get(path+'/integration?version=1.0.0',headers=h)).json()
    assert old==v1
    mismatch=await run({**v1,'configuration_digest':v2['configuration_digest']})
    assert mismatch.status_code==409,mismatch.text
    assert (await client.get(path+'/integration?version=9.0.0',headers=h)).status_code==404
    other=await register()
    assert (await client.get(path+'/releases',headers=other)).status_code==404
    assert (await client.post(path+'/releases/1.0.0/activate',headers=other)).status_code==404
    switched=await client.post(path+'/releases/1.0.0/activate',headers=h)
    assert switched.status_code==200,switched.text
    assert 'RELEASE_ONE' in (await run()).text
    assert 'RELEASE_TWO' in (await run(v2)).text
    assert (await client.get(path,headers=h)).json()['system_prompt']=='RELEASE_TWO'
    from app.main import app
    app.state.rate_limiter_counts.clear()  # This test exercises >30 operations, not quota behavior.
    await client.put(path,headers=h,json={'system_prompt':'RELEASE_THREE'})
    import asyncio
    publications=await asyncio.gather(client.post(path+'/publish',headers=h),client.post(path+'/publish',headers=h))
    assert all(r.status_code==200 for r in publications),[r.text for r in publications]
    versions=(await client.get(path+'/releases',headers=h)).json()
    assert versions['active_version']=='1.0.2'
    assert len(versions['releases'])==3
    assert 'RELEASE_ONE' in (await run(v1)).text
    assert 'RELEASE_THREE' in (await run()).text
    credentials=(await client.post('/api/oauth/clients',headers=h,data={'name':'Release test',
        'scopes':'api:write','allowed_agent_ids':aid,'allowed_purposes':'quality_improvement'})).json()
    token=await client.post('/api/oauth/token',data={'grant_type':'client_credentials','scope':'api:write',
        'client_id':credentials['client_id'],'client_secret':credentials['client_secret']})
    machine={'Authorization':'Bearer '+token.json()['access_token']}
    assert (await run(v1,headers=machine)).status_code==200
    assert (await run(preview=True,headers=machine)).status_code==403
    await client.post(path+'/archive',headers=h)
    assert (await run(v1)).json()['error_reason']=='agent_not_published'
    assert (await client.get(path+'/integration?version=1.0.0',headers=h)).status_code==409


@pytest.mark.asyncio
async def test_first_edit_preserves_legacy_online_definition(client, needs_auth):
    uid=uuid.uuid4().hex[:12]
    registered=await client.post("/api/auth/register",json={"username":uid,"email":uid+"@example.com","password":"LegacyTest!2026","full_name":"Synthetic","organization_name":uid})
    assert registered.status_code==201,registered.text
    client.headers["Authorization"]="Bearer "+registered.json()["access_token"]
    org_id=decode_token(registered.json()['access_token'])['org_id']
    from sqlalchemy import select
    from app.database import async_session_factory
    from app.models.agent import Agent
    from app.models.agent_release import AgentRelease
    created=await client.post('/api/rest/v1/agent_definitions',json={'name':'Legacy proof','system_prompt':'OLD_ONLINE'})
    aid=created.json()['id']
    async with async_session_factory() as db:
        await bind_tenant_to_transaction(db,org_id)
        agent=(await db.execute(select(Agent).where(Agent.id==aid))).scalar_one()
        agent.is_published=True;agent.status='published'
        await db.commit()
    changed=await client.put('/api/rest/v1/agent_definitions/'+aid,json={'system_prompt':'NEW_DRAFT'})
    assert changed.status_code==200,changed.text
    async with async_session_factory() as db:
        await bind_tenant_to_transaction(db,org_id)
        release=(await db.execute(select(AgentRelease).where(AgentRelease.agent_id==aid))).scalar_one()
        assert release.definition['system_prompt']=='OLD_ONLINE'
        assert release.runtime_pack['system_prompt']=='OLD_ONLINE'
        assert release.version=='1.0.0'
