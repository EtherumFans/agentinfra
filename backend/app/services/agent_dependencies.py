"""Published dependency declarations fail closed on registered revision drift.

This compares tenant registry identities, not remote weights or remote content.
Operators must register changes before replacing mutable upstream deployments.
"""
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict
from fastapi import HTTPException
from sqlalchemy import select
from app.models.agent_dependency import AgentDependency

class DependencyBinding(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['model','tool','knowledge']
    name:str=Field(pattern=r'^[A-Za-z0-9_.-]{1,100}$')
class DependencyRegistration(DependencyBinding):
    version:str=Field(pattern=r'^[A-Za-z0-9_.+-]{1,100}$')
    artifact_digest:str | None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
class DependencyBindings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    bindings:list[DependencyBinding]=Field(max_length=30)

def project(row):
    return {'kind':row.kind,'name':row.name,'version':row.version,'artifact_digest':row.artifact_digest}

async def resolve_bindings(db,org,bindings):
    locks=[];seen=set()
    for raw in bindings:
        try:binding=DependencyBinding.model_validate(raw)
        except ValueError:raise HTTPException(422,'invalid_dependency_binding')
        key=(binding.kind,binding.name)
        if key in seen:raise HTTPException(422,'duplicate_dependency_binding')
        seen.add(key)
        row=(await db.execute(select(AgentDependency).where(AgentDependency.organization_id==org,
            AgentDependency.kind==binding.kind,AgentDependency.name==binding.name,AgentDependency.is_current.is_(True)))).scalar_one_or_none()
        if row is None:raise HTTPException(409,detail={'error':'dependency_not_registered','kind':binding.kind,'name':binding.name})
        locks.append(project(row))
    return sorted(locks,key=lambda x:(x['kind'],x['name']))

async def draft_locks(db,agent):
    bindings=(agent.config or {}).get('dependency_bindings',[])
    if not isinstance(bindings,list) or len(bindings)>30:raise HTTPException(422,'invalid_dependency_bindings')
    return await resolve_bindings(db,agent.organization_id,bindings)

async def release_drift(db,release):
    locks=release.runtime_pack.get('_dependency_lock',[])
    changes=[]
    for expected in locks:
        try:current=(await resolve_bindings(db,release.organization_id,[{'kind':expected['kind'],'name':expected['name']}]))[0]
        except HTTPException:current=None
        if current!=expected:changes.append({'expected':expected,'current':current})
    return changes

async def verify_release(db,release):
    changes=await release_drift(db,release)
    if changes:raise HTTPException(409,detail={'error':'dependency_drift','message':'已登记的外部依赖版本发生变化，请核验依赖并重新评测、发布。','changes':changes})
