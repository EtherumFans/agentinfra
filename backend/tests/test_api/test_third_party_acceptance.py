"""Real TCP third-party app -> OAuth -> pinned run/jobs -> signed receiver.
Only model output and the HTTPS callback destination mapping are test doubles.
"""
import asyncio
import importlib.util
import json
import os
import socket
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
import pytest
import uvicorn

@asynccontextmanager
async def serve(app):
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off',access_log=False))
    task=asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(100):
            if server.started:break
            if task.done():await task
            await asyncio.sleep(.01)
        assert server.started
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit=True
        await asyncio.wait_for(task,10)
        sock.close()

@pytest.mark.asyncio
async def test_third_party_http_acceptance(client,needs_auth,monkeypatch,tmp_path):
    from app.main import app
    from app.services.agent_jobs import AgentJobWorker
    from tests.test_api.test_agent_jobs import setup
    monkeypatch.setattr('app.middleware.rate_limit.GENERAL_LIMIT',200)
    from icoder_runtime.backends.pure_llm_provider import PureLLMProvider
    original_resolver = PureLLMProvider._resolve_client
    h,aid,org,calls=await setup(client,monkeypatch)
    live = os.environ.get('ICODER_LIVE_DEEPSEEK_ACCEPTANCE') == '1'
    live_evidence = {}
    if live:
        from tests.test_api.deepseek_live_support import configure_live_gateway
        live_evidence = await configure_live_gateway(monkeypatch)
        monkeypatch.setattr(PureLLMProvider, '_resolve_client', original_resolver)
    path='/api/rest/v1/agent_definitions/'+aid
    manifest=(await client.get(path+'/integration',headers=h)).json()
    credentials=(await client.post('/api/oauth/clients',headers=h,data={'name':'Third-party acceptance','scopes':'api:write','allowed_agent_ids':aid,'allowed_purposes':'quality_improvement'})).json()
    source=Path(__file__).resolve().parents[3]/'frontend/public/integration'
    monkeypatch.syspath_prepend(str(source))
    spec=importlib.util.spec_from_file_location('third_party_acceptance',source/'server.py')
    demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
    monkeypatch.setattr(demo,'RECEIPT_PATH',tmp_path/'receipts.db')
    secret='test-callback-'+uuid.uuid4().hex
    callback='https://third-party.example/icoder/notifications'
    monkeypatch.setenv('ICODER_TASK_CALLBACK_URLS',json.dumps({org:[callback]}))
    monkeypatch.setenv('ICODER_TASK_CALLBACK_SECRETS',json.dumps({org:secret}))
    evidence={}
    async with serve(app) as upstream,serve(demo.app) as downstream:
        config={'ICODER_BASE_URL':upstream,'ICODER_AGENT_ID':aid,'ICODER_AGENT_VERSION':manifest['version'],'ICODER_CONFIGURATION_DIGEST':manifest['configuration_digest'],'ICODER_PURPOSE':'quality_improvement','ICODER_CLIENT_ID':credentials['client_id'],'ICODER_CLIENT_SECRET':credentials['client_secret'],'DEMO_PASSWORD':'synthetic-demo-password','ICODER_CALLBACK_URL':callback,'ICODER_CALLBACK_SECRET':secret}
        monkeypatch.setattr(demo,'configuration',lambda:config)
        async with httpx.AsyncClient(base_url=downstream,headers={'Host':'testserver'},timeout=180 if live else 30,trust_env=False) as third:
            assert (await third.post('/icoder/check')).status_code==401
            third.auth=('demo',config['DEMO_PASSWORD'])
            assert (await third.post('/icoder/run',json={'text':'   '})).status_code==422
            assert (await third.post('/icoder/check',headers={'Origin':'https://untrusted.example'})).status_code==403
            first=await third.post('/icoder/check');assert first.status_code==200,first.text
            report=first.json();assert report['ok'] and report['version']==manifest['version'] and report['run_id'] and report['elapsed_ms']>=0
            assert report['checks']['callback']=='not_checked'
            evidence['first_call']=report
            # Publishing a new default must not change a third-party pinned call.
            await client.put(path,headers=h,json={'system_prompt':'VERSION_TWO'})
            assert (await client.post(path+'/publish',headers=h)).status_code==200
            pinned=await third.post('/icoder/check');assert pinned.json()['version']==manifest['version'] and pinned.json()['ok']
            evidence['pinned_after_new_release']=True
            original=config['ICODER_CONFIGURATION_DIGEST'];config['ICODER_CONFIGURATION_DIGEST']='0'*64
            mismatch=await third.post('/icoder/check');assert mismatch.status_code==409 and mismatch.json()['diagnostic']['code']=='binding_conflict'
            config['ICODER_CONFIGURATION_DIGEST']=original
            config['ICODER_PURPOSE']='research'
            denied=await third.post('/icoder/check');assert denied.status_code==403
            config['ICODER_PURPOSE']='quality_improvement'
            evidence['binding_and_purpose_rejected']=True
            key=uuid.uuid4().hex
            queued=await third.post('/icoder/jobs',headers={'Idempotency-Key':key},json={'text':'Synthetic asynchronous acceptance'})
            assert queued.status_code==202,queued.text
            jid=queued.json()['jobs'][0]['id']
            replay=await third.post('/icoder/jobs',headers={'Idempotency-Key':key},json={'text':'Synthetic asynchronous acceptance'})
            assert replay.json()['replayed'] and replay.json()['jobs'][0]['id']==jid
            notifications=[]
            async def network_delivery(url,raw,signature):
                assert url==callback
                notifications.append((raw,signature))
                if len(notifications)==1:return 503
                response=await third.post('/icoder/notifications',content=raw,headers={'X-iCoDer-Signature':signature})
                return response.status_code
            monkeypatch.setattr('app.services.agent_jobs.send_notification',network_delivery)
            worker=AgentJobWorker();worker.app=app
            async def organizations():return [org]
            monkeypatch.setattr(worker,'organizations',organizations)
            await worker.start(app)
            try:
                for _ in range(450 if live else 100):
                    polled = await third.get('/icoder/jobs/'+jid)
                    assert polled.status_code == 200, polled.text
                    status=polled.json()
                    if status['notification_state']=='delivered':break
                    await asyncio.sleep(2 if live else .4)
                assert status['state']=='completed' and status['notification_state']=='delivered',status
                assert status['notification_attempts']==2
            finally:await worker.stop()
            overview=await client.get('/api/operations/overview',headers=h,params={'agent_id':aid})
            operational=overview.json()
            assert overview.status_code==200,overview.text
            assert operational['queue']['completed']==1 and operational['notifications']['delivered']==1
            assert any(r['run_id']==status['run_id'] for r in operational['runs'])
            assert operational['summary']['runs']>=3
            assert sum(g['runs'] for g in operational['groups'])==operational['summary']['runs']
            evidence['operations_statistics']=operational['summary']
            receipt=await third.get('/icoder/receipts/'+jid);assert receipt.json()['received']
            raw,signature=notifications[-1]
            duplicate=await third.post('/icoder/notifications',content=raw,headers={'X-iCoDer-Signature':signature})
            assert duplicate.json()=={'accepted':True,'duplicate':True}
            assert (await third.post('/icoder/notifications',content=raw+b' ',headers={'X-iCoDer-Signature':signature})).status_code==401
            old_signature='1.'+signature.split('.',1)[1]
            assert (await third.post('/icoder/notifications',content=raw,headers={'X-iCoDer-Signature':old_signature})).status_code==401
            evidence['async']={'job_id':jid,'run_id':status['run_id'],'state':status['state'],'notification_attempts':2,'signature_tamper_rejected':True,'duplicate_ignored':True,'submission_replayed':True}
            assert (await client.delete('/api/oauth/clients/'+credentials['client_id'],headers=h)).status_code==200
            revoked=await third.post('/icoder/check');assert revoked.status_code==502 and revoked.json()['diagnostic']['stage']=='authorization'
            evidence['revoked_client_rejected']=True
            for credential in (credentials['client_secret'],secret):assert credential not in json.dumps(evidence)
    if live:
        assert len(live_evidence['calls']) == 5, 'Expected two gateway probes and three real agent invocations'
    filename = 'deepseek-third-party-acceptance.json' if live else 'third-party-acceptance.json'
    destination=Path(__file__).resolve().parents[3]/'artifacts/product-review-2026-09-07'/filename
    destination.write_text(json.dumps({'passed':True,'transport':'real loopback TCP','model':os.environ.get('LLM_MODEL') if live else 'deterministic synthetic provider','live_model':live_evidence,'callback_mapping':'test-only HTTPS registered URL mapped to loopback receiver',**evidence},ensure_ascii=False,indent=2),encoding='utf-8')
