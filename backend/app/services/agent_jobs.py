"""Durable queue with atomic claims, live authority checks and signed outbox delivery."""
import asyncio
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
import httpx
from fastapi import HTTPException, Request
from sqlalchemy import select, update, or_, text
from app.models.agent_job import AgentJob
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.models.oauth import OAuthClient
from app.services.database_tenancy import bind_tenant_to_transaction
from app.services.phi_encryption import encrypt_phi, decrypt_phi
import app.database as database

logger=logging.getLogger(__name__)
TERMINAL=('completed','failed','interrupted','cancelled')

def now():return datetime.now(timezone.utc)

def actor(principal):
    user,client=principal
    if client is not None:
        if client.get('token_type')!='client_credentials':raise HTTPException(403,'machine_token_required')
        return 'oauth',str(client['client_id'])
    return 'user',str(user.id)

def callback_secret(org):
    try:secret=json.loads(os.getenv('ICODER_TASK_CALLBACK_SECRETS','{}')).get(org,'')
    except (ValueError,AttributeError):secret=''
    if not isinstance(secret,str) or len(secret)<32:raise HTTPException(503,'callback_signing_not_configured')
    return secret

def validate_callback(url,org):
    if not url:return
    try:allowed=json.loads(os.getenv('ICODER_TASK_CALLBACK_URLS','{}')).get(org,[])
    except (ValueError,AttributeError):allowed=[]
    try:
        parsed=urlsplit(url);port=parsed.port
    except ValueError:raise HTTPException(422,'callback_not_registered')
    if not isinstance(allowed,list) or url not in allowed or parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query or port not in (None,443):
        raise HTTPException(422,'callback_not_registered')
    callback_secret(org)

async def live_principal(db,job):
    org=await db.get(Organization,job.organization_id)
    if not org or not org.is_active:raise HTTPException(403,'organization_inactive')
    if job.actor_kind=='oauth':
        c=(await db.execute(select(OAuthClient).where(OAuthClient.client_id==job.actor_id,OAuthClient.organization_id==job.organization_id,OAuthClient.is_active.is_(True)))).scalar_one_or_none()
        if not c:raise HTTPException(403,'client_revoked')
        stored=json.loads(decrypt_phi(job.payload))
        granted=set(c.scopes.split()) & set(stored.get('scopes',[]))
        return (None,{'client_id':c.client_id,'owner_id':c.owner_id,'org_id':c.organization_id,'token_type':'client_credentials',
            'scopes':sorted(granted),'allowed_agent_ids':c.allowed_agent_ids,'allowed_purposes':c.allowed_purposes}),org
    user=await db.get(User,job.actor_id)
    member=(await db.execute(select(OrganizationMember.id).where(OrganizationMember.organization_id==job.organization_id,OrganizationMember.user_id==job.actor_id))).scalar_one_or_none()
    if not user or not user.is_active or not member:raise HTTPException(403,'user_access_revoked')
    return (user,None),org

def projection(job,include_result=False):
    data={'id':job.id,'item_index':int(job.idempotency_key.rsplit(':',1)[-1]),'batch_id':hashlib.sha256(job.idempotency_key.rsplit(':',1)[0].encode()).hexdigest()[:16],'agent_id':job.agent_id,'version':job.version,'state':job.state,'error_code':job.error_code,
        'run_id':job.run_id,'created_at':job.created_at.isoformat(),'notification_state':job.notification_state,
        'notification_attempts':job.notification_attempts,'result_url':f'/api/v1/agent-jobs/{job.id}'}
    if include_result and job.result:data['result']=json.loads(decrypt_phi(job.result))
    return data

async def send_notification(url,payload,signature):
    from app.services.connector_http_transport import PinnedAsyncHTTPTransport
    async with httpx.AsyncClient(transport=PinnedAsyncHTTPTransport(),trust_env=False,follow_redirects=False,timeout=10) as client:
        async with client.stream('POST',url,content=payload,headers={'Content-Type':'application/json','X-iCoDer-Signature':signature}) as response:
            return response.status_code

class AgentJobWorker:
    def __init__(self):
        self.loop=None;self.app=None;self.tasks=set();self.notifications=set()
        self.task_org={};self.notification_ids={};self.org_cursor=''
        def setting(name,default,maximum):
            try:value=int(os.getenv(name,str(default)))
            except ValueError:raise ValueError(f'{name} must be an integer')
            if not 1<=value<=maximum:raise ValueError(f'{name} outside supported range')
            return value
        self.concurrency=setting('ICODER_JOB_CONCURRENCY',2,32)
        self.per_org=setting('ICODER_JOB_PER_ORG_CONCURRENCY',1,32)
        self.notification_concurrency=setting('ICODER_NOTIFICATION_CONCURRENCY',4,32)
        self.poll_seconds=setting('ICODER_JOB_POLL_SECONDS',2,60)
        self.idle_seconds=self.poll_seconds

    async def start(self,app):
        self.app=app;self.loop=asyncio.create_task(self._loop())

    async def stop(self):
        active=[*self.tasks,*self.notifications,*([self.loop] if self.loop else [])]
        for task in active:task.cancel()
        await asyncio.gather(*active,return_exceptions=True)

    def reap(self):
        for pool in (self.tasks,self.notifications):
            for task in list(pool):
                if not task.done():continue
                if not task.cancelled() and task.exception() is not None:
                    logger.error('Agent worker persistence failed: %s',type(task.exception()).__name__)
                pool.discard(task);self.task_org.pop(task,None);self.notification_ids.pop(task,None)

    async def _loop(self):
        while True:
            try:
                scheduled=await self.tick()
                self.idle_seconds=self.poll_seconds if scheduled or self.tasks or self.notifications else min(30,self.idle_seconds*2)
            except asyncio.CancelledError:raise
            except Exception as exc:
                logger.error('Agent job scan failed: %s',type(exc).__name__)
                self.idle_seconds=min(30,self.idle_seconds*2)
            await asyncio.sleep(self.idle_seconds)

    async def organizations(self):
        # Bound each scan and rotate its first organization, including when all
        # organizations fit on one page. No fixed first tenant owns every slot.
        async with database.AsyncSessionLocal() as db:
            query=select(Organization.id).where(Organization.is_active.is_(True))
            orgs=list((await db.execute(query.where(Organization.id>self.org_cursor).order_by(Organization.id).limit(200))).scalars())
            if len(orgs)<200 and self.org_cursor:
                orgs+=list((await db.execute(query.where(Organization.id<=self.org_cursor).order_by(Organization.id).limit(200-len(orgs)))).scalars())
        if orgs:self.org_cursor=orgs[0]
        return orgs

    async def tick(self):
        self.reap();scheduled=0
        orgs=await self.organizations()
        for org in orgs:
            free=max(0,min(self.concurrency-len(self.tasks),self.per_org-sum(value==org for value in self.task_org.values())))
            notice_free=max(0,self.notification_concurrency-len(self.notifications))
            async with database.AsyncSessionLocal() as db:
                await bind_tenant_to_transaction(db,org)
                await db.execute(update(AgentJob).where(AgentJob.organization_id==org,AgentJob.state=='running',AgentJob.lease_until<now()).values(
                    state='interrupted',error_code='execution_outcome_unknown',finished_at=now(),notification_due=now()))
                queued=list((await db.execute(select(AgentJob.id).where(AgentJob.organization_id==org,AgentJob.state=='queued').order_by(AgentJob.created_at,AgentJob.id).limit(free))).scalars()) if free else []
                notice_query=select(AgentJob.id).where(
                    AgentJob.organization_id==org,AgentJob.state.in_(TERMINAL),
                    AgentJob.notification_state=='pending',AgentJob.notification_due<=now(),
                    or_(AgentJob.notification_lease.is_(None),AgentJob.notification_lease<now()),
                ).order_by(AgentJob.notification_due,AgentJob.id).limit(1)
                notifications=list((await db.execute(notice_query)).scalars()) if notice_free else []
                await db.commit()
            for jid in queued:
                task=asyncio.create_task(self.execute(jid,org));self.tasks.add(task);self.task_org[task]=org;scheduled+=1
            for jid in notifications:
                if jid in self.notification_ids.values():continue
                task=asyncio.create_task(self.deliver(jid,org));self.notifications.add(task);self.notification_ids[task]=jid;scheduled+=1
        return scheduled
    async def execute(self,jid,org):
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db,org)
            claim=await db.execute(update(AgentJob).where(AgentJob.id==jid,AgentJob.organization_id==org,AgentJob.state=='queued').values(state='running',lease_until=now()+timedelta(seconds=1860)))
            await db.commit()
            if claim.rowcount!=1:return
        result=None;state='failed';error=None
        try:
            async with database.AsyncSessionLocal() as db:
                await bind_tenant_to_transaction(db,org)
                job=await db.get(AgentJob,jid)
                principal,organization=await live_principal(db,job)
                from app.api.agent_run import run_agent,AgentRunRequest
                body=AgentRunRequest(**json.loads(decrypt_phi(job.payload))['request'])
                scope={'type':'http','method':'POST','path':f'/api/v1/agents/{job.agent_id}/run','headers':[(b'idempotency-key',('job-'+jid).encode())],
                    'app':self.app,'server':('127.0.0.1',0),'client':('127.0.0.1',0),'scheme':'http','query_string':b''}
                from app.services.tenant_model_routing import tenant_model_scope
                with tenant_model_scope(organization.id):
                    response=await asyncio.wait_for(run_agent(job.agent_id,body,Request(scope),principal,organization,db),timeout=1800)
                result=response.model_dump(mode='json');state='failed' if response.error else 'completed'
                error=response.error_reason if response.error else None
        except asyncio.CancelledError:
            await asyncio.shield(self.finish(jid,org,'interrupted',None,'execution_outcome_unknown'))
            raise
        except asyncio.TimeoutError:state='interrupted';error='execution_timeout_outcome_unknown'
        except HTTPException as exc:error=f'access_or_configuration_{exc.status_code}'
        except Exception as exc:
            logger.error('Agent job failed %s: %s',jid,type(exc).__name__);error='execution_failed'
        await self.finish(jid,org,state,result,error)
    async def finish(self,jid,org,state,result,error):
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db,org)
            await db.execute(update(AgentJob).where(AgentJob.id==jid,AgentJob.organization_id==org,AgentJob.state=='running').values(state=state,
                result=encrypt_phi(json.dumps(result,ensure_ascii=False)) if result else None,run_id=result.get('run_id') if result else None,
                error_code=(error or '')[:80] or None,finished_at=now(),lease_until=None,notification_due=now()))
            await db.commit()
    async def deliver(self,jid,org):
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db,org)
            claim=await db.execute(update(AgentJob).where(AgentJob.id==jid,AgentJob.organization_id==org,AgentJob.notification_state=='pending',
                AgentJob.state.in_(TERMINAL),AgentJob.notification_due<=now(),or_(AgentJob.notification_lease.is_(None),AgentJob.notification_lease<now())).values(notification_lease=now()+timedelta(seconds=30)))
            await db.commit()
            if claim.rowcount!=1:return
            job=await db.get(AgentJob,jid)
            attempts=job.notification_attempts+1;success=False;blocked=False
            try:
                await live_principal(db,job)
                validate_callback(job.callback_url,org)
                payload=json.dumps({'event_id':job.id+':terminal','job_id':job.id,'agent_id':job.agent_id,'version':job.version,
                    'state':job.state,'run_id':job.run_id,'result_url':f'/api/v1/agent-jobs/{job.id}'},sort_keys=True,separators=(',',':')).encode()
                timestamp=str(int(now().timestamp()))
                signature=timestamp+'.'+hmac.new(callback_secret(org).encode(),timestamp.encode()+b'.'+payload,hashlib.sha256).hexdigest()
                status=await send_notification(job.callback_url,payload,signature)
                success=200<=status<300
                blocked=400<=status<500 and status!=429 or 300<=status<400
            except HTTPException:blocked=True
            except Exception as exc:logger.warning('Notification failed %s: %s',jid,type(exc).__name__)
            job.notification_attempts=attempts
            job.notification_state='delivered' if success else 'failed' if blocked or attempts>=5 else 'pending'
            job.notification_due=now()+timedelta(seconds=min(3600,10*2**attempts))
            job.notification_lease=None
            await db.commit()
