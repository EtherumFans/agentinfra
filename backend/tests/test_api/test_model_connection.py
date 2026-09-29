import json
import uuid
import pytest
from sqlalchemy import select, update


@pytest.mark.asyncio
async def test_encrypted_setup_routing_failure_preservation_and_permissions(client, needs_auth, monkeypatch):
    from app.main import app
    from app.database import AsyncSessionLocal
    from app.models.model_connection import ModelConnection
    from app.models.organization import OrganizationMember, OrgRole
    from app.models.audit_log import AuditLog
    from app.middleware.auth import decode_token
    from app.services.database_tenancy import bind_tenant_to_transaction
    from app.services.tenant_model_routing import resolve_tenant_model_route
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    from icoder_runtime.core.llm_gateway import DeepSeekProvider, LLMGateway, MockLLMProvider
    policy = RuntimeDataPolicy(allow_external_llm=True)
    monkeypatch.setattr(app.state, 'data_policy', policy, raising=False)
    monkeypatch.setattr(app.state, 'model_connection_probes', {}, raising=False)
    monkeypatch.setattr('app.middleware.rate_limit.GENERAL_LIMIT', 200)
    async def register():
        name = uuid.uuid4().hex[:12]
        r = await client.post('/api/auth/register', json={'username':name,'email':name+'@example.com','password':'ModelTest!2026','full_name':'Synthetic','organization_name':name})
        assert r.status_code == 201
        token = r.json()['access_token']; claims = decode_token(token)
        return {'Authorization':'Bearer '+token}, claims['org_id'], claims['sub']
    headers, org, uid = await register()
    other, other_org, _ = await register()
    calls = []
    async def generate(self, **kwargs):
        calls.append((self.api_key, self.model))
        return {'content':'ICODER_OK','model':self.model,'finish_reason':'stop','latency_ms':12,'usage':{'input_tokens':10,'output_tokens':4}}
    monkeypatch.setattr(DeepSeekProvider, 'generate', generate)
    url = '/api/v1/model-connection'
    key = 'synthetic-secret-'+uuid.uuid4().hex
    body = {'api_key':key,'model':'deepseek-v4-flash','expected_version':0}
    assert (await client.get(url, headers=headers)).json()['version'] == 0
    saved = await client.post(url+'/test-and-enable', headers=headers, json=body)
    assert saved.status_code == 200, saved.text
    assert key not in saved.text
    public = await client.get(url, headers=headers)
    assert public.json()['enabled'] and key not in public.text
    assert not (await client.get(url, headers=other)).json()['configured']
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, org)
        row = await db.get(ModelConnection, org)
        assert key not in row.encrypted_key
        audits = (await db.execute(select(AuditLog.details).where(AuditLog.organization_id==org, AuditLog.action=='model_connection.enabled'))).scalars().all()
        assert len(audits) == 1 and key not in json.dumps(audits)
    gateway = LLMGateway(data_policy=policy, tenant_provider_resolver=resolve_tenant_model_route)
    gateway.register(MockLLMProvider(), default=True)
    result = await gateway.generate(messages=[{'role':'user','content':'synthetic'}], context={'organization_id':org})
    assert result['model'] == 'deepseek-v4-flash' and calls[-1][0] == key
    from app.services.tenant_model_routing import bind_request_tenant, reset_request_tenant
    from icoder_runtime.backends.llm_gateway_adapter import LLMGatewayAdapter
    token = bind_request_tenant(org)
    try:
        adapted = await LLMGatewayAdapter(gateway).complete(system_prompt='synthetic', user_input='check')
        assert adapted.finish_reason == 'stop' and adapted.text == 'ICODER_OK'
    finally:
        reset_request_tenant(token)
    route = await resolve_tenant_model_route({'organization_id':other_org})
    assert route['mode'] == 'inherit' and '_provider' not in route
    catalog = await client.get('/api/v1/model-catalog', headers=headers)
    assert catalog.status_code == 200, catalog.text
    assert catalog.json()['active_provider'] == 'deepseek' and catalog.json()['active_model']=='deepseek-v4-flash'
    assert key not in catalog.text
    policy.allow_external_llm = False
    count = len(calls)
    denied = await client.post(url+'/test-and-enable', headers=headers, json={**body, 'expected_version':1})
    assert denied.status_code == 403 and len(calls) == count
    policy.allow_external_llm = True
    assert (await client.post(url+'/test-and-enable', headers=headers, json=body)).status_code == 409
    app.state.model_connection_probes.clear()
    async def unavailable(self, **kwargs): return {'degraded':True}
    monkeypatch.setattr(DeepSeekProvider, 'generate', unavailable)
    failed = await client.post(url+'/test-and-enable', headers=headers, json={**body,'api_key':'replacement','expected_version':1})
    assert failed.status_code == 502
    assert (await client.get(url, headers=headers)).json()['version'] == 1
    assert (await client.post(url+'/disable', headers=headers, json={'expected_version':1})).status_code==200
    assert (await resolve_tenant_model_route({'organization_id':org}))['mode']=='inherit'
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db, org)
        await db.execute(update(OrganizationMember).where(OrganizationMember.organization_id==org,OrganizationMember.user_id==uid).values(role=OrgRole.MEMBER))
        await db.commit()
    assert not (await client.get(url,headers=headers)).json()['editable']
    assert (await client.post(url+'/disable',headers=headers,json={'expected_version':2})).status_code==403
    assert (await client.post(url+'/test-and-enable',headers=headers,json={**body,'expected_version':2})).status_code==403


@pytest.mark.asyncio
async def test_policy_blocks_calls_and_cipher_binds_tenant(monkeypatch):
    from app.models.model_connection import ModelConnection
    from app.services.model_connection import encrypt_key, provider_for
    encrypted = encrypt_key('one', 'synthetic-key')
    with pytest.raises(ValueError, match='tenant_mismatch'):
        provider_for(ModelConnection(organization_id='two',encrypted_key=encrypted,model='deepseek-v4-flash'))
    monkeypatch.delenv('ICODER_SECRET_KEY')
    with pytest.raises(ValueError, match='stable_encryption'):
        encrypt_key('one','synthetic')
