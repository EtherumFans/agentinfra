"""Tenant-scoped resumable evaluations; unknown outcomes require explicit retry."""
import asyncio
import uuid
from datetime import timedelta
from fastapi import Request,HTTPException
from sqlalchemy import select,update,func
from app import database
from app.models.evaluation_dataset import EvaluationDataset as Dataset,EvaluationBatch as Batch,EvaluationBatchItem as Item,now
from app.models.organization import Organization,OrganizationMember
from app.models.user import User
from app.models.agent import Agent
from app.services.agent_jobs import AgentJobWorker
from app.services.database_tenancy import bind_tenant_to_transaction
from app.services.release_evaluation import EvaluationRequest,draft_fingerprint

class EvaluationBatchWorker(AgentJobWorker):
    async def heartbeat(self,iid,org,token):
        while True:
            await asyncio.sleep(30)
            async with database.AsyncSessionLocal() as db:
                await bind_tenant_to_transaction(db,org)
                changed=await db.execute(update(Item).where(Item.id==iid,Item.organization_id==org,Item.state=='running',Item.claim_token==token).values(lease_until=now()+timedelta(seconds=90)))
                await db.commit()
                if changed.rowcount!=1:return

    async def tick(self):
        self.reap();scheduled=0
        for org in await self.organizations():
            async with database.AsyncSessionLocal() as db:
                await bind_tenant_to_transaction(db,org)
                from app.api.evaluation_datasets import lock
                await lock(db,org)
                await db.execute(update(Item).where(Item.organization_id==org,Item.state=='running',Item.lease_until<now()).values(state='interrupted',error_code='execution_outcome_unknown',claim_token=None))
                batches=list((await db.execute(select(Batch).where(Batch.organization_id==org,Batch.state=='active').limit(100))).scalars())
                for b in batches:
                    outstanding=(await db.execute(select(func.count()).select_from(Item).where(Item.batch_id==b.id,Item.organization_id==org,Item.state.in_(('queued','running'))))).scalar_one()
                    if not outstanding:b.state='completed'
                ids=list((await db.execute(select(Item.id).join(Batch,Item.batch_id==Batch.id).where(Item.organization_id==org,Batch.organization_id==org,Item.state=='queued',Batch.state=='active').order_by(Batch.created_at,Item.case_index).limit(1))).scalars()) if len(self.tasks)<self.concurrency else []
                await db.commit()
            for iid in ids:
                task=asyncio.create_task(self.execute(iid,org));self.tasks.add(task);self.task_org[task]=org;scheduled+=1
        return scheduled

    async def execute(self,iid,org):
        token=str(uuid.uuid4())
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db,org)
            from app.api.evaluation_datasets import lock
            await lock(db,org)
            item=await db.get(Item,iid);b=await db.get(Batch,item.batch_id) if item else None
            running=(await db.execute(select(func.count()).select_from(Item).where(Item.organization_id==org,Item.state=='running'))).scalar_one()
            if not b or b.state!='active' or item.state!='queued' or running:return
            item.state='running';item.claim_token=token;item.lease_until=now()+timedelta(seconds=90)
            item.attempts=[*item.attempts,{'token':token,'started_at':now().isoformat()}]
            await db.commit()
        state='failed';error=None;result=None
        heartbeat=asyncio.create_task(self.heartbeat(iid,org,token))
        try:
            async with database.AsyncSessionLocal() as db:
                await bind_tenant_to_transaction(db,org)
                item=await db.get(Item,iid);b=await db.get(Batch,item.batch_id);d=await db.get(Dataset,b.dataset_revision_id)
                user=await db.get(User,b.created_by);organization=await db.get(Organization,org)
                member=(await db.execute(select(OrganizationMember.id).where(OrganizationMember.organization_id==org,OrganizationMember.user_id==b.created_by))).scalar_one_or_none()
                if not user or not user.is_active or not member or not organization.is_active:raise HTTPException(403,'authority_revoked')
                agent=(await db.execute(select(Agent).where(Agent.id==b.agent_id,Agent.organization_id==org))).scalar_one_or_none()
                if not agent or d.review_status!='approved' or b.draft_digest!=await draft_fingerprint(db,agent):raise HTTPException(409,'evaluation_configuration_changed')
                body=EvaluationRequest(cases=[d.cases[item.case_index]],purpose_of_use=b.purpose)
                from app.api.agent_evaluations import evaluate_agent_releases
                request=Request({'type':'http','method':'POST','path':'/evaluation-batch','headers':[],'app':self.app,'server':('127.0.0.1',0),'client':('127.0.0.1',0),'scheme':'http','query_string':b''})
                request.scope['_evaluation_batch_context']={'batch_id':b.id,'dataset_revision_id':d.id}
                from app.services.tenant_model_routing import tenant_model_scope
                with tenant_model_scope(organization.id):
                    result=await asyncio.wait_for(evaluate_agent_releases(b.agent_id,body,request,user,organization,db),1800)
                candidate=result['cases'][0]['candidate']
                from app.models.run_history import RunHistoryModel
                run=(await db.execute(select(RunHistoryModel).where(RunHistoryModel.run_id==candidate.get('run_id'),RunHistoryModel.organization_id==org))).scalar_one_or_none()
                candidate['model_usage']=run.model_usage if run else None
                current_dataset=await db.get(Dataset,d.id,populate_existing=True)
                state='completed' if candidate.get('execution_ok') and result['consistent'] and current_dataset.review_status=='approved' else 'failed'
                if state=='failed':error='execution_failed_or_configuration_changed'
        except asyncio.CancelledError:
            await self.finish_item(iid,org,token,'interrupted',None,'execution_outcome_unknown');raise
        except asyncio.TimeoutError:error='execution_timeout_outcome_unknown';state='interrupted'
        except HTTPException as exc:error='authority_or_configuration_changed' if exc.status_code in (403,409,404) else 'execution_rejected'
        except Exception:error='execution_failed'
        finally:
            heartbeat.cancel();await asyncio.gather(heartbeat,return_exceptions=True)
        await self.finish_item(iid,org,token,state,result,error)
        if error=='authority_or_configuration_changed':
            async with database.AsyncSessionLocal() as db:
                await bind_tenant_to_transaction(db,org)
                item=await db.get(Item,iid);b=await db.get(Batch,item.batch_id)
                if b.state=='active':b.state='blocked'
                await db.execute(update(Item).where(Item.organization_id==org,Item.batch_id==b.id,Item.state=='queued').values(state='failed',error_code=error))
                await db.commit()

    async def finish_item(self,iid,org,token,state,result,error):
        async with database.AsyncSessionLocal() as db:
            await bind_tenant_to_transaction(db,org)
            from app.api.evaluation_datasets import lock
            await lock(db,org)
            item=await db.get(Item,iid)
            if item.state!='running' or item.claim_token!=token:return
            item.state=state;item.result=result;item.error_code=error;item.claim_token=None;item.lease_until=None
            item.attempts=[*item.attempts,{'token':token,'state':state,'report_id':result.get('id') if result else None,'error_code':error,'finished_at':now().isoformat()}]
            await db.commit()
