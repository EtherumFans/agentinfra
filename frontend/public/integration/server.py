"""Local integration example: python server.py (Python 3.10+).

Install fastapi, uvicorn and httpx; keep integration-config.json beside this file.
The browser never receives OAuth credentials/tokens. For deployment, replace
HTTP Basic demo authentication with the host application's user authorization.
"""
import json
import secrets
import time
import sqlite3
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, field_validator

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
basic = HTTPBasic()
CONFIG_PATH = Path(__file__).with_name('integration-config.json')


def configuration():
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    for key in ('ICODER_BASE_URL', 'ICODER_AGENT_ID', 'ICODER_AGENT_VERSION',
                'ICODER_CONFIGURATION_DIGEST', 'ICODER_CLIENT_ID',
                'ICODER_CLIENT_SECRET', 'ICODER_PURPOSE', 'DEMO_PASSWORD'):
        if not config.get(key) or any(x in config[key] for x in ('填写', '设置本地')):
            raise RuntimeError(f'Configure {key} in integration-config.json')
    return config


def require_user(credentials: HTTPBasicCredentials = Depends(basic)):
    config = configuration()
    if not (secrets.compare_digest(credentials.username, 'demo') and
            secrets.compare_digest(credentials.password.encode(), config['DEMO_PASSWORD'].encode())):
        raise HTTPException(401, 'Unauthorized', headers={'WWW-Authenticate':'Basic'})
    return config


@app.middleware('http')
async def local_security(request: Request, call_next):
    # Do not permit another web origin to spend this demo client's allowance.
    if request.headers.get('host') not in ('127.0.0.1:13010', 'localhost:13010', 'testserver'):
        return JSONResponse({'error': 'invalid_host'}, 403)
    if request.method == 'POST' and request.headers.get('origin') not in (
        None, 'http://127.0.0.1:13010', 'http://localhost:13010',
    ):
        return JSONResponse({'error': 'origin_rejected'}, 403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


PAGE = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>iCoDer 外部接入验证</title>
<style>body{font:14px system-ui;background:#F5F5F7;color:#1D1D1F;max-width:800px;margin:40px auto;padding:20px}main{background:white;padding:24px;border-radius:16px}textarea{width:100%;min-height:160px;box-sizing:border-box;padding:12px}button{background:#0071E3;color:white;border:0;border-radius:20px;padding:10px 20px;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}button:disabled{opacity:.5}</style>
<main><h1>iCoDer 外部接入验证</h1><p>此页面由用户系统的本地示例服务提供。结果供人工复核。</p>
<button id="check" type="button">检查服务端接入</button><p id="diagnostic" role="status">检查将发送一次合成任务，验证专用凭据与固定版本。</p>
<button id="export" type="button" disabled>下载验收报告</button><button id="async" type="button">提交合成异步任务</button><button id="receipt" type="button" disabled>刷新任务与回调状态</button><p id="async-status" role="status"></p>
<form><textarea aria-label="合成任务资料" required>合成测试资料：患者因咳嗽就诊。请整理为主诉、现病史及待补充信息，不补造事实。</textarea><br><button>运行智能体</button></form>
<p id="status" aria-live="polite">尚未运行</p><pre></pre></main>
<script>const form=document.querySelector('form'),button=document.querySelector('form button'),out=document.querySelector('pre'),status=document.querySelector('#status');
let report=null,submissionKey=null,currentJob=null;document.querySelector('#receipt').onclick=async()=>{const d=document.querySelector('#async-status');try{const j=await fetch('/icoder/jobs/'+encodeURIComponent(currentJob));if(!j.ok)throw Error('无法读取任务');const job=await j.json();const r=await fetch('/icoder/receipts/'+encodeURIComponent(currentJob));if(!r.ok)throw Error('无法读取回调');report={kind:'async',job_id:currentJob,state:job.state,version:job.version,run_id:job.run_id,notification_state:job.notification_state,receipt:await r.json(),checked_at:new Date().toISOString()};document.querySelector('#export').disabled=false;d.textContent=JSON.stringify(report,null,2);}catch{d.textContent='刷新失败，请检查权限与网络';}};document.querySelector('#export').onclick=()=>{const u=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='icoder-acceptance.json';a.click();URL.revokeObjectURL(u);};
document.querySelector('#async').onclick=async e=>{const b=e.currentTarget,d=document.querySelector('#async-status');b.disabled=true;const key=submissionKey||crypto.randomUUID();submissionKey=key;try{const r=await fetch('/icoder/jobs',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify({text:'Synthetic integration acceptance only'})});const v=await r.json();if(!r.ok)throw Error('提交失败，请检查授权及回调配置');const id=v.jobs[0].id;submissionKey=null;currentJob=id;document.querySelector('#receipt').disabled=false;d.textContent='任务 '+id+' 已提交';for(let i=0;i<60;i++){await new Promise(resolve=>setTimeout(resolve,2000));const q=await fetch('/icoder/jobs/'+encodeURIComponent(id));if(!q.ok)throw Error('读取失败，请检查权限');const job=await q.json();d.textContent='任务 '+id+' · '+job.state;if(['completed','failed','interrupted','cancelled'].includes(job.state)){const receipt=await (await fetch('/icoder/receipts/'+encodeURIComponent(id))).json();report={kind:'async',job_id:id,state:job.state,version:job.version,run_id:job.run_id,notification_state:job.notification_state,receipt,checked_at:new Date().toISOString()};document.querySelector('#export').disabled=false;d.textContent=JSON.stringify(report,null,2);break;}}}catch(error){d.textContent=error.message+'；提交键 '+key+'，结果不确定时保留此键，不要重复提交。';}finally{b.disabled=false;}};
document.querySelector('#check').onclick=async e=>{const b=e.currentTarget;b.disabled=true;const d=document.querySelector('#diagnostic');d.textContent='正在检查…';try{const r=await fetch('/icoder/check',{method:'POST'});const v=await r.json();d.textContent=JSON.stringify(v,null,2);report=v;document.querySelector('#export').disabled=false;}catch{d.textContent='本地服务连接失败';}finally{b.disabled=false;}};
form.addEventListener('icoder:completed',e=>{status.textContent='已收到完成回调 · 运行 '+e.detail.run_id;});
form.onsubmit=async e=>{e.preventDefault();button.disabled=true;status.textContent='正在运行…';out.textContent='';
try{const r=await fetch('/icoder/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:document.querySelector('textarea').value})});
const data=await r.json();out.textContent=JSON.stringify(data,null,2);
if(!r.ok||data.error){status.textContent='未完成，请查看错误信息';}else{form.dispatchEvent(new CustomEvent('icoder:completed',{detail:data,bubbles:true}));}}
catch{status.textContent='连接失败，请检查本地接入服务';}finally{button.disabled=false;}};</script></html>'''


@app.get('/', response_class=HTMLResponse)
async def home(config=Depends(require_user)):
    return PAGE


class Task(BaseModel):
    text: str = Field(min_length=1, max_length=32000)

    @field_validator('text')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Task text must not be blank')
        return value


@app.post('/icoder/run')
async def run_task(task: Task, config=Depends(require_user)):
    # Identity, agent, version and purpose are fixed server-side, never accepted
    # from browser input. No automatic retry can duplicate a clinical task.
    base = config['ICODER_BASE_URL'].rstrip('/')
    async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
        try:
            token_response = await client.post(base + '/api/oauth/token', data={
                'grant_type': 'client_credentials', 'scope': 'api:write',
                'client_id': config['ICODER_CLIENT_ID'],
                'client_secret': config['ICODER_CLIENT_SECRET'],
            })
            if token_response.status_code != 200:
                raise HTTPException(502, {'stage':'authorization', 'code':'client_authorization_failed',
                    'remedy':'核对服务端客户端 ID、密钥、有效期及 api:write 权限。'})
            token = token_response.json()['access_token']
            response = await client.post(
                base + '/api/v1/agents/' + quote(config['ICODER_AGENT_ID'], safe='') + '/run',
                headers={'Authorization': 'Bearer ' + token,
                         'Idempotency-Key': secrets.token_urlsafe(24)},
                json={'input': {'text': task.text},
                      'purpose_of_use': config['ICODER_PURPOSE'],
                      'expected_agent_version': config['ICODER_AGENT_VERSION'],
                      'expected_configuration_digest': config['ICODER_CONFIGURATION_DIGEST']},
            )
            return JSONResponse(response.json(), status_code=response.status_code)
        except httpx.TimeoutException:
            raise HTTPException(504, {'stage':'network', 'code':'upstream_timeout',
                'remedy':'请求超时。先检查运行记录，确认是否已执行，再决定是否重试。'})
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(502, {'stage':'network', 'code':'upstream_unavailable',
                'remedy':'检查服务端地址、网络连接和上游服务日志。'})


@app.post('/icoder/check')
async def check_connection(config=Depends(require_user)):
    """Exercise the actual server-held credential and binding, using synthetic input."""
    started=time.monotonic()
    try:
        response = await run_task(Task(text='合成软件接入测试，无真实患者。请标注缺失资料，不补造事实。'), config)
    except HTTPException as exc:
        return JSONResponse({'ok':False, 'diagnostic':exc.detail, 'checked_at':datetime.now(timezone.utc).isoformat(), 'elapsed_ms':round((time.monotonic()-started)*1000)}, status_code=exc.status_code)
    data = json.loads(response.body)
    status = response.status_code
    code = 'execution_failed'
    remedy = '检查运行记录中的失败原因及模型、工具就绪状态。'
    if status in (401,403):
        code, remedy = 'access_denied', '检查客户端是否授权该智能体及 quality_improvement 用途，或是否已被撤销。'
    elif status == 404:
        code, remedy = 'release_not_found', '核对智能体 ID 与发布版本，重新下载对应版本的配置。'
    elif status == 409:
        code, remedy = 'binding_conflict', '检查智能体是否归档、版本与摘要是否匹配，重新下载发布配置。'
    elif status == 422:
        code, remedy = 'input_invalid', '核对必填 text 字段、长度和用途。'
    elif status == 429:
        code, remedy = 'rate_limited', '调用频率超限，请稍后再试。'
    ok = status == 200 and data.get('error') is False and data.get('executed_agent_version')==config['ICODER_AGENT_VERSION'] and bool(data.get('run_id'))
    if status==200 and data.get('error') is False and not ok:
        code, remedy = 'execution_identity_mismatch', '实际执行版本未匹配固定版本，不能通过验收。'
    return JSONResponse({'ok':ok, 'checked_at':datetime.now(timezone.utc).isoformat(), 'elapsed_ms':round((time.monotonic()-started)*1000),
        'purpose_of_use':config['ICODER_PURPOSE'], 'expected_version':config['ICODER_AGENT_VERSION'],
        'configuration_digest':config['ICODER_CONFIGURATION_DIGEST'],
        'checks':{'authorization':status not in (401,403),'execution':ok,'version':data.get('executed_agent_version')==config['ICODER_AGENT_VERSION'],'callback':'not_checked'},
        'diagnostic':{'stage':'execution', 'code':'connected' if ok else code,
                      'remedy':'接入链路已通过；结果质量仍需人工评测。' if ok else remedy},
        'agent_id':config['ICODER_AGENT_ID'], 'version':data.get('executed_agent_version'),
        'run_id':data.get('run_id'), 'manual_review_required':data.get('manual_review_required', True),
        'finish_state':data.get('result', {}).get('finish_state')},
        status_code=200 if ok else status if status >= 400 else 502)


async def job_request(method, path, config, payload=None, key=None):
    base=config['ICODER_BASE_URL'].rstrip('/')
    async with httpx.AsyncClient(timeout=30,follow_redirects=False) as client:
        try:
            token_response=await client.post(base+'/api/oauth/token',data={
                'grant_type':'client_credentials','scope':'api:write',
                'client_id':config['ICODER_CLIENT_ID'],'client_secret':config['ICODER_CLIENT_SECRET']})
            if token_response.status_code!=200:raise HTTPException(502,'Client authorization failed')
            headers={'Authorization':'Bearer '+token_response.json()['access_token']}
            if key:headers['Idempotency-Key']=key
            response=await client.request(method,base+path,headers=headers,**({'json':payload} if payload is not None else {}))
            data=response.json()
            if method=='GET' and response.status_code==200 and data.get('agent_id')!=config['ICODER_AGENT_ID']:
                raise HTTPException(404,'Job not found')
            return JSONResponse(data,status_code=response.status_code)
        except httpx.TimeoutException:raise HTTPException(504,'Submission uncertain; retry with the same Idempotency-Key')
        except (httpx.HTTPError,ValueError,KeyError):raise HTTPException(502,'Upstream unavailable')

@app.post('/icoder/jobs')
async def submit_async_task(task: Task, request: Request, config=Depends(require_user)):
    key=request.headers.get('Idempotency-Key')
    if not key:raise HTTPException(422,'Idempotency-Key is required; keep it when retrying this submission')
    return await job_request('POST','/api/v1/agents/'+quote(config['ICODER_AGENT_ID'],safe='')+'/jobs',config,
        {'inputs':[{'text':task.text}], 'purpose_of_use':config['ICODER_PURPOSE'],
         'expected_agent_version':config['ICODER_AGENT_VERSION'],
         'expected_configuration_digest':config['ICODER_CONFIGURATION_DIGEST'],
         **({'callback_url':config['ICODER_CALLBACK_URL']} if config.get('ICODER_CALLBACK_URL') else {})},key)

@app.get('/icoder/jobs/{job_id}')
async def async_task_status(job_id: str, config=Depends(require_user)):
    return await job_request('GET','/api/v1/agent-jobs/'+quote(job_id,safe=''),config)


RECEIPT_PATH=Path(__file__).with_name('notification-receipts.db')

def receipt(event=None, job_id=None):
    with sqlite3.connect(RECEIPT_PATH, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS receipts (event_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, agent_id TEXT NOT NULL, version TEXT NOT NULL, received_at TEXT NOT NULL)')
        if event is not None:
            changed=db.execute('INSERT OR IGNORE INTO receipts VALUES (?,?,?,?,?)',(event['event_id'],event['job_id'],event['agent_id'],event['version'],datetime.now(timezone.utc).isoformat())).rowcount
            return {'accepted':True,'duplicate':changed==0}
        row=db.execute('SELECT agent_id,version,received_at FROM receipts WHERE job_id=?',(job_id,)).fetchone()
        return row

@app.post('/icoder/notifications')
async def notification(request:Request):
    # The callback authenticates with its signature, never browser Basic auth.
    from verify_notification import verify_notification
    config=configuration();secret=config.get('ICODER_CALLBACK_SECRET','')
    if len(secret)<32:raise HTTPException(503,'Callback not configured')
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>8192:raise HTTPException(413,'Notification too large')
    try:
        event=verify_notification(bytes(raw),request.headers.get('X-iCoDer-Signature',''),secret)
        if event.get('agent_id')!=config['ICODER_AGENT_ID'] or event.get('version')!=config['ICODER_AGENT_VERSION'] or not isinstance(event.get('job_id'),str) or event.get('state') not in ('completed','failed','cancelled','interrupted'):
            raise ValueError('Unexpected event')
    except (ValueError,TypeError,KeyError):raise HTTPException(401,'Invalid notification')
    return await asyncio.to_thread(receipt,event)

@app.get('/icoder/receipts/{job_id}')
async def notification_status(job_id:str,config=Depends(require_user)):
    row=await asyncio.to_thread(receipt,None,job_id)
    if not row or row[0]!=config['ICODER_AGENT_ID'] or row[1]!=config['ICODER_AGENT_VERSION']:
        return {'received':False}
    return {'received':True,'received_at':row[2],'job_id':job_id}


if __name__ == '__main__':
    configuration()
    uvicorn.run(app, host='127.0.0.1', port=13010)
