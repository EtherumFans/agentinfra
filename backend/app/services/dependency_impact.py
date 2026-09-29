"""Read-only dependency impact projection; never exposes client credentials."""
import re
from sqlalchemy import select,func
from app.models.agent import Agent
from app.models.agent_release import AgentRelease
from app.models.agent_job import AgentJob
from app.models.oauth import OAuthClient

async def dependency_impact(db,org,kind,name):
    agents=(await db.execute(select(Agent).where(Agent.organization_id==org,Agent.is_prebuilt.is_(False)))).scalars().all()
    releases=(await db.execute(select(AgentRelease).where(AgentRelease.organization_id==org))).scalars().all()
    clients=(await db.execute(select(OAuthClient).where(OAuthClient.organization_id==org,OAuthClient.is_active.is_(True)))).scalars().all()
    counts=dict((await db.execute(select(AgentJob.agent_id,func.count()).where(AgentJob.organization_id==org,AgentJob.state.in_(['queued','running'])).group_by(AgentJob.agent_id))).all())
    result=[]
    for agent in agents:
        bound=any(d.get('kind')==kind and d.get('name')==name for d in (agent.config or {}).get('dependency_bindings',[]))
        affected=[]
        for release in releases:
            if release.agent_id!=agent.id:continue
            locks=[d for d in release.runtime_pack.get('_dependency_lock',[]) if d.get('kind')==kind and d.get('name')==name]
            if locks:affected.append({'version':release.version,'dependency_version':locks[0]['version'],'active':bool(agent.is_published and agent.version==release.version)})
        if bound or affected:
            result.append({'agent_id':agent.id,'name':agent.name,'draft_bound':bound,'releases':affected,'pending_jobs':counts.get(agent.id,0),
                'authorized_clients':[{'name':c.name,'client_id':c.client_id} for c in clients if agent.id in c.delegated_agent_ids()]})
    return result

async def configured_dependency_candidates(db,agent):
    from app.services.agent_releases import runtime_definition
    from app.services.agent_runtime_pack import pack_from_tenant_agent
    resolved=await runtime_definition(db,agent,preview=True)
    pack=await pack_from_tenant_agent(resolved,agent.organization_id,db)
    model=pack.get('model') or {};tools=pack.get('tools') or []
    candidates=[]
    if isinstance(model,dict):
        for key in ('primary','fallback'):
            if isinstance(model.get(key),str):candidates.append({'kind':'model','name':model[key]})
    for tool in tools:
        name=tool if isinstance(tool,str) else tool.get('id') or tool.get('name') if isinstance(tool,dict) else None
        if name:candidates.append({'kind':'tool','name':name})
    unique={(c['kind'],c['name']):c for c in candidates if re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',c['name'])}
    return list(unique.values())
