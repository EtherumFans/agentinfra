import uuid
import pytest
from tests.test_api.test_agent_jobs import setup

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['model','tool','knowledge'])
async def test_dependency_drift_blocks_pinned_run_and_dependency_only_publish(client,needs_auth,monkeypatch,kind):
    monkeypatch.setattr('app.middleware.rate_limit.GENERAL_LIMIT',200)
    h,aid,org,calls=await setup(client,monkeypatch)
    path='/api/rest/v1/agent_definitions/'+aid
    dep={'kind':kind,'name':'clinical-model','version':'2026.1','artifact_digest':'a'*64}
    r=await client.post(path+'/dependencies/register',headers=h,json=dep)
    assert r.status_code==200,r.text
    assert (await client.put(path+'/dependencies/bindings',headers=h,json={'bindings':[{'kind':kind,'name':'clinical-model'}]})).status_code==200
    assert (await client.post(path+'/publish',headers=h)).status_code==200
    impact=await client.get(path+'/dependencies/impact',headers=h,params={'kind':kind,'name':'clinical-model'})
    assert impact.status_code==200,impact.text
    assert impact.json()['agents'][0]['agent_id']==aid
    assert impact.json()['agents'][0]['releases'][0]['dependency_version']=='2026.1'
    assert 'client_secret' not in impact.text
    manifest=(await client.get(path+'/integration',headers=h)).json()
    assert manifest['version']=='1.0.1'
    payload={'input':{'text':'Synthetic only'},'purpose_of_use':'quality_improvement','expected_agent_version':manifest['version'],'expected_configuration_digest':manifest['configuration_digest']}
    url=f'/api/v1/agents/{aid}/run'
    assert (await client.post(url,headers=h,json=payload)).status_code==200
    assert (await client.post(path+'/dependencies/register',headers=h,json={**dep,'artifact_digest':'b'*64})).status_code==409
    assert (await client.post(path+'/dependencies/register',headers=h,json={**dep,'version':'2026.2','artifact_digest':'b'*64})).status_code==200
    blocked=await client.post(url,headers=h,json=payload)
    assert blocked.status_code==409,blocked.text
    assert blocked.json()['detail']['error']=='dependency_drift'
    state=(await client.get(path+'/dependencies',headers=h)).json()
    assert len(state['drift'])==1 and state['remote_content_verified'] is False
    assert (await client.get(path+'/releases',headers=h)).json()['draft_changed'] is True
    published=await client.post(path+'/publish',headers=h)
    assert published.json()['version']=='1.0.2',published.text
    latest=(await client.get(path+'/integration',headers=h)).json()
    assert (await client.post(url,headers=h,json={**payload,'expected_agent_version':latest['version'],'expected_configuration_digest':latest['configuration_digest']})).status_code==200
    assert (await client.post(url,headers=h,json=payload)).status_code==409
    # Re-registering a previously verified external revision reactivates that identity only.
    assert (await client.post(path+'/dependencies/register',headers=h,json=dep)).status_code==200
    assert (await client.post(url,headers=h,json=payload)).status_code==200
    other,_,_,_=await setup(client,monkeypatch)
    assert (await client.get(path+'/dependencies',headers=other)).status_code==404
    assert (await client.post(path+'/dependencies/register',headers=other,json=dep)).status_code==404
    assert (await client.put(path+'/dependencies/bindings',headers=h,json={'bindings':[{'kind':'knowledge','name':'missing'}]})).status_code==409

@pytest.mark.asyncio
async def test_non_admin_cannot_change_shared_registry(client,needs_auth,monkeypatch):
    monkeypatch.setattr('app.middleware.rate_limit.GENERAL_LIMIT',200)
    h,aid,org,calls=await setup(client,monkeypatch)
    from app.database import AsyncSessionLocal
    from app.models.organization import OrganizationMember,OrgRole
    from app.services.database_tenancy import bind_tenant_to_transaction
    from sqlalchemy import update
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,org)
        await db.execute(update(OrganizationMember).where(OrganizationMember.organization_id==org).values(role=OrgRole.MEMBER));await db.commit()
    path='/api/rest/v1/agent_definitions/'+aid+'/dependencies'
    assert (await client.get(path,headers=h)).json()['can_register'] is False
    assert (await client.get(path+'/impact',headers=h,params={'kind':'tool','name':'extract'})).status_code==403
    assert (await client.post(path+'/register',headers=h,json={'kind':'tool','name':'extract','version':'1'})).status_code==403
