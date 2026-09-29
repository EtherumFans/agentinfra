import importlib.util
from pathlib import Path

import httpx
import pytest


@pytest.mark.asyncio
async def test_proxy_keeps_credentials_and_binding_server_side(monkeypatch):
    path = Path(__file__).resolve().parents[3] / 'frontend/public/integration/server.py'
    spec = importlib.util.spec_from_file_location('integration_demo', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = {'ICODER_BASE_URL':'http://upstream','ICODER_AGENT_ID':'bound-agent',
              'ICODER_AGENT_VERSION':'1.0.2','ICODER_CONFIGURATION_DIGEST':'a'*64,
              'ICODER_CLIENT_ID':'private-client','ICODER_CLIENT_SECRET':'private-secret',
              'ICODER_PURPOSE':'quality_improvement','DEMO_PASSWORD':'local-password'}
    monkeypatch.setattr(module, 'configuration', lambda: config)
    requests = []
    def upstream(request):
        requests.append(request)
        if request.url.path.endswith('/token'):
            return httpx.Response(200,json={'access_token':'private-token'})
        import json
        body = json.loads(request.content)
        assert body['expected_agent_version'] == '1.0.2'
        assert body['expected_configuration_digest'] == 'a'*64
        assert body['purpose_of_use'] == 'quality_improvement'
        assert request.url.path == '/api/v1/agents/bound-agent/run'
        assert request.headers['authorization'] == 'Bearer private-token'
        return httpx.Response(200,json={'error':False,'run_id':'proxy-run','result':{'text':'synthetic'}})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(upstream), **kw))
    async with real_client(transport=httpx.ASGITransport(app=module.app),base_url='http://testserver') as client:
        denied = await client.post('/icoder/run',json={'text':'synthetic'})
        assert denied.status_code == 401
        assert not requests
        auth = ('demo','local-password')
        cross_origin = await client.post('/icoder/run', auth=auth,
            headers={'Origin':'https://untrusted.example'}, json={'text':'synthetic'})
        assert cross_origin.status_code == 403
        assert not requests
        result = await client.post('/icoder/run',auth=auth,json={'text':'synthetic','agent_id':'other'})
        assert result.status_code == 200, result.text
        assert result.json()['run_id'] == 'proxy-run'
        for secret in ('private-client','private-secret','private-token'):
            assert secret not in result.text
        assert result.headers['cache-control'] == 'no-store'


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [(401,'access_denied'),(403,'access_denied'),
    (404,'release_not_found'),(409,'binding_conflict'),(429,'rate_limited'),(503,'execution_failed')])
async def test_diagnostics_classifies_failures_without_leaking_upstream(monkeypatch,status,code):
    spec=importlib.util.spec_from_file_location('diagnostic_demo',Path(__file__).resolve().parents[3]/'frontend/public/integration/server.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    config={'ICODER_BASE_URL':'http://upstream','ICODER_AGENT_ID':'bound',
        'ICODER_AGENT_VERSION':'1.0.0','ICODER_CONFIGURATION_DIGEST':'a'*64,
        'ICODER_CLIENT_ID':'private-client','ICODER_CLIENT_SECRET':'private-secret',
        'ICODER_PURPOSE':'quality_improvement','DEMO_PASSWORD':'local-password'}
    monkeypatch.setattr(module,'configuration',lambda:config)
    def upstream(request):
        if request.url.path.endswith('/token'):
            return httpx.Response(200,json={'access_token':'private-token'})
        return httpx.Response(status,json={'detail':'private-secret sensitive upstream internals'})
    real=httpx.AsyncClient
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(upstream),**kw))
    async with real(transport=httpx.ASGITransport(app=module.app),base_url='http://testserver') as client:
        assert (await client.post('/icoder/check')).status_code==401
        r=await client.post('/icoder/check',auth=('demo','local-password'))
        assert r.status_code==status
        assert r.json()['ok'] is False
        assert r.json()['diagnostic']['code']==code
        assert 'private-secret' not in r.text
        assert (await client.post('/icoder/check',auth=('demo','local-password'),headers={'Origin':'https://evil.example'})).status_code==403


@pytest.mark.asyncio
async def test_connection_timeout_is_uncertain_and_does_not_retry(monkeypatch):
    spec=importlib.util.spec_from_file_location('timeout_demo',Path(__file__).resolve().parents[3]/'frontend/public/integration/server.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    config={'ICODER_BASE_URL':'http://upstream','ICODER_AGENT_ID':'bound','ICODER_AGENT_VERSION':'1.0.0','ICODER_CONFIGURATION_DIGEST':'a'*64,'ICODER_CLIENT_ID':'private-client','ICODER_CLIENT_SECRET':'private-secret','ICODER_PURPOSE':'quality_improvement','DEMO_PASSWORD':'local-password'}
    monkeypatch.setattr(module,'configuration',lambda:config)
    requests=[]
    def upstream(request):
        requests.append(request.url.path)
        if request.url.path.endswith('/token'):return httpx.Response(200,json={'access_token':'private-token'})
        raise httpx.ReadTimeout('synthetic timeout',request=request)
    real=httpx.AsyncClient
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(upstream),**kw))
    async with real(transport=httpx.ASGITransport(app=module.app),base_url='http://testserver') as client:
        r=await client.post('/icoder/check',auth=('demo','local-password'))
        assert r.status_code==504 and r.json()['diagnostic']['code']=='upstream_timeout'
        assert len(requests)==2
        assert 'private-secret' not in r.text
