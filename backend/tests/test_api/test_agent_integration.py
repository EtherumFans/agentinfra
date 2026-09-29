from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from app.services.agent_integration import integration_manifest, validate_integration_binding


def test_configuration_binding_rejects_changes_even_without_version_bump():
    agent = SimpleNamespace(id='custom', name='Doc', organization_id='one', version='1.0.0',
                            status='published', is_published=True, is_prebuilt=False,
                            system_prompt='original', config={'model':'one'})
    manifest = integration_manifest(agent)
    validate_integration_binding(agent, manifest['version'], manifest['configuration_digest'])
    agent.system_prompt = 'changed'
    with pytest.raises(HTTPException) as error:
        validate_integration_binding(agent, manifest['version'], manifest['configuration_digest'])
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_tenant_manifest_version_gate_and_machine_execution(client, needs_auth, monkeypatch):
    from icoder_runtime.backends.pure_llm_provider import PureLLMProvider, LLMResponse
    class SyntheticModel:
        async def complete(self, **kwargs):
            return LLMResponse(text='## Synthetic documentation\nSupplied facts only. Human review required.', finish_reason='stop')
    monkeypatch.setattr(PureLLMProvider, '_resolve_client', lambda self: SyntheticModel())
    async def register():
        suffix = uuid.uuid4().hex[:12]
        r = await client.post('/api/auth/register', json={
            'username':'integration-'+suffix, 'email':suffix+'@example.com',
            'password':'Integration!2026', 'full_name':'Synthetic Integration User',
            'organization_name':'Integration '+suffix})
        assert r.status_code == 201, r.text
        return {'Authorization':'Bearer '+r.json()['access_token']}
    headers = await register()
    created = await client.post('/api/rest/v1/agent_definitions', headers=headers,
        json={'name':'Synthetic documentation integration',
              'system_prompt':'Organize supplied facts only.', 'expert_ids':[]})
    assert created.status_code in (200,201), created.text
    agent_id = created.json()['id']
    path = '/api/rest/v1/agent_definitions/'+agent_id
    published = await client.post(path+'/publish', headers=headers)
    assert published.status_code == 200, published.text
    manifest_response = await client.get(path+'/integration', headers=headers)
    assert manifest_response.status_code == 200, manifest_response.text
    manifest = manifest_response.json()
    other_headers = await register()
    assert (await client.get(path+'/integration', headers=other_headers)).status_code == 404
    payload = {'input':{'text':'Synthetic document. Missing information must stay missing.'},
               'expected_agent_version':manifest['version'],
               'expected_configuration_digest':manifest['configuration_digest'],
               'purpose_of_use':'quality_improvement'}
    credentials = await client.post('/api/oauth/clients', headers=headers, data={
        'name':'Integration test client', 'scopes':'api:write',
        'allowed_agent_ids':agent_id, 'allowed_purposes':'quality_improvement'})
    assert credentials.status_code in (200,201), credentials.text
    credential = credentials.json()
    token = await client.post('/api/oauth/token', data={
        'grant_type':'client_credentials','scope':'api:write',
        'client_id':credential['client_id'],'client_secret':credential['client_secret']})
    assert token.status_code == 200, token.text
    machine = {'Authorization':'Bearer '+token.json()['access_token']}
    result = await client.post(manifest['run_path'], headers=machine, json=payload)
    assert result.status_code == 200, result.text
    # Mock/degraded models are permitted in this isolated test, not quality evidence.
    assert result.json().get('run_id'), result.text
    assert result.json().get('error') is False, result.text
    trace = await client.get(result.json()['trace_url'], headers=headers)
    assert trace.status_code == 200, trace.text
    # The downloadable host-server example calls the real OAuth and Run APIs;
    # only the model response above is synthetic.
    import importlib.util
    from pathlib import Path
    import httpx
    spec = importlib.util.spec_from_file_location('real_integration_proxy',
        Path(__file__).resolve().parents[3] / 'frontend/public/integration/server.py')
    proxy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proxy)
    config = {'ICODER_BASE_URL':'http://test', 'ICODER_AGENT_ID':agent_id,
              'ICODER_AGENT_VERSION':manifest['version'],
              'ICODER_CONFIGURATION_DIGEST':manifest['configuration_digest'],
              'ICODER_CLIENT_ID':credential['client_id'], 'ICODER_CLIENT_SECRET':credential['client_secret'],
              'ICODER_PURPOSE':'quality_improvement', 'DEMO_PASSWORD':'local-test-password'}
    monkeypatch.setattr(proxy, 'configuration', lambda: config)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(proxy.httpx, 'AsyncClient', lambda **kw: real_client(transport=client._transport, **kw))
    async with real_client(transport=httpx.ASGITransport(app=proxy.app),base_url='http://testserver') as external:
        proxy_result = await external.post('/icoder/run', auth=('demo','local-test-password'),
                                          json={'text':'Synthetic document for human review.'})
        assert proxy_result.status_code == 200, proxy_result.text
        assert proxy_result.json()['error'] is False, proxy_result.text
        assert proxy_result.json()['run_id'] != result.json()['run_id']
        diagnostic = await external.post('/icoder/check', auth=('demo','local-test-password'))
        assert diagnostic.status_code == 200, diagnostic.text
        assert diagnostic.json()['ok'] is True
        assert diagnostic.json()['version'] == manifest['version']
        assert diagnostic.json()['run_id']
        assert credential['client_secret'] not in diagnostic.text
        queued=await external.post('/icoder/jobs',auth=('demo','local-test-password'),headers={'Idempotency-Key':uuid.uuid4().hex},json={'text':'Synthetic asynchronous document'})
        assert queued.status_code==202,queued.text
        jid=queued.json()['jobs'][0]['id']
        status=await external.get('/icoder/jobs/'+jid,auth=('demo','local-test-password'))
        assert status.status_code==200,status.text
        assert status.json()['version']==manifest['version']
    monkeypatch.setattr(proxy.httpx, 'AsyncClient', real_client)
    wrong_purpose = await client.post(manifest['run_path'], headers=machine,
                                    json={**payload, 'purpose_of_use':'payment'})
    assert wrong_purpose.status_code == 403
    updated = await client.put(path, headers=headers, json={'system_prompt':'New draft instructions'})
    assert updated.status_code == 200, updated.text
    changed = await client.post(manifest['run_path'], headers=machine, json=payload)
    assert changed.status_code == 200, changed.text
    assert changed.json()['executed_agent_version'] == manifest['version']
    assert changed.json()['error'] is False
    await client.post(path+'/archive', headers=headers)
    assert (await client.get(path+'/integration', headers=headers)).status_code == 409
    revoked = await client.delete('/api/oauth/clients/'+credential['client_id'], headers=headers)
    assert revoked.status_code == 200, revoked.text
    denied = await client.post(manifest['run_path'], headers=machine, json=payload)
    assert denied.status_code in (401,403), denied.text
