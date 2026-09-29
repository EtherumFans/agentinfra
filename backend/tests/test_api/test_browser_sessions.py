import uuid
import pytest

@pytest.mark.asyncio
async def test_browser_cookie_csrf_refresh_and_session_scoped_logout(client,needs_auth):
    from app.middleware.auth import decode_token
    uid=uuid.uuid4().hex[:12]
    headers={'Origin':'http://test','X-iCoDer-Browser':'1'}
    body={'username':uid,'email':uid+'@example.com','password':'Session!2026','full_name':'Synthetic','organization_name':uid}
    assert (await client.post('/api/auth/browser/register',json=body)).status_code==403
    registered=await client.post('/api/auth/browser/register',headers=headers,json=body)
    assert registered.status_code==201,registered.text
    cookie=registered.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Path=/api/auth/browser' in cookie
    assert registered.json()['refresh_token']==''
    old_access=registered.json()['access_token']
    assert decode_token(old_access)['browser_session_id']
    assert (await client.post('/api/auth/browser/refresh',headers={**headers,'Origin':'https://evil.example'})).status_code==403
    refreshed=await client.post('/api/auth/browser/refresh',headers=headers)
    assert refreshed.status_code==200,refreshed.text
    stolen=client.cookies.get('icoder_browser_refresh')
    # A separate session for the same user must remain valid after logout here.
    login=await client.post('/api/auth/login',json={'username':uid,'password':'Session!2026'})
    other_access=login.json()['access_token']
    assert (await client.post('/api/auth/browser/logout',headers=headers)).status_code==200
    assert (await client.get('/api/auth/me',headers={'Authorization':'Bearer '+old_access})).status_code==401
    assert (await client.get('/api/auth/me',headers={'Authorization':'Bearer '+other_access})).status_code==200
    assert (await client.post('/api/auth/refresh',json={'refresh_token':stolen})).status_code==401
    assert (await client.post('/api/auth/browser/refresh',headers={**headers,'Cookie':'icoder_browser_refresh='+stolen})).status_code==401

@pytest.mark.asyncio
async def test_memory_search_requires_consent_and_returns_older_window(client,needs_auth):
    from app.database import AsyncSessionLocal
    from app.services.database_tenancy import bind_tenant_to_transaction
    from app.services.connector_memory_store import GovernedMemoryStore
    from app.services.connector_executor import ConnectorInvocation
    uid=uuid.uuid4().hex[:12]
    r=await client.post('/api/auth/register',json={'username':uid,'email':uid+'@example.com','password':'Memory!2026','full_name':'Synthetic','organization_name':uid})
    assert r.status_code==201,r.text
    data=r.json();h={'Authorization':'Bearer '+data['access_token']}
    a=await client.post('/api/rest/v1/agent_definitions',headers=h,json={'name':'Memory search'})
    aid=a.json()['id'];url=f'/api/v2/agentic/agents/{aid}/memory-search'
    assert (await client.post(url,headers=h,json={'query':'synthetic preference'})).status_code==403
    store=GovernedMemoryStore()
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,data['current_org_id'])
        await store.grant(db,organization_id=data['current_org_id'],user_id=data['user']['id'],agent_id=aid,purpose_of_use='treatment',retention_days=30,expires_in_days=30)
        await store.invoke(db,ConnectorInvocation(organization_id=data['current_org_id'],actor_type='user',actor_id=data['user']['id'],agent_id=aid,connector_id='test-memory',operation='remember',arguments={'content':'synthetic preference concise summaries','role':'user'},data_classification='deidentified',purpose_of_use='treatment'))
        await db.commit()
    found=await client.post(url,headers=h,json={'query':'synthetic preference'})
    assert found.status_code==200,found.text
    assert found.json()['returned']==1
    assert (await client.post(url,headers=h,json={'query':'synthetic preference','purpose_of_use':'quality_improvement'})).status_code==403
    assert (await client.post(url,headers=h,json={'query':'synthetic preference','candidate_offset':1})).json()['returned']==0
