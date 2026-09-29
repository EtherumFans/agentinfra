"""Read-only, consent-scoped memory search; never grants memory access."""
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_user,get_current_organization
from app.models.user import User
from app.models.organization import Organization
from app.api.agent_connectors import _get_agent,_memory_store
from app.services.connector_executor import ConnectorInvocation,ConnectorExecutionError
router=APIRouter(prefix='/api/v2/agentic/agents',tags=['memory-search'])
class MemorySearch(BaseModel):
    query:str=Field(min_length=1,max_length=500)
    purpose_of_use:str='treatment'
    candidate_offset:int=Field(default=0,ge=0,le=100000)
    candidate_limit:int=Field(default=100,ge=1,le=1000)
@router.post('/{agent_id}/memory-search')
async def search_memory(agent_id:str,body:MemorySearch,user:User=Depends(get_current_user),org:Organization=Depends(get_current_organization),db:AsyncSession=Depends(get_db)):
    await _get_agent(db,organization_id=org.id,agent_id=agent_id)
    try:
        return await _memory_store.invoke(db,ConnectorInvocation(organization_id=org.id,agent_id=agent_id,connector_id='memory-history',operation='recall',arguments={**body.model_dump(),'top_k':20},data_classification='deidentified',purpose_of_use=body.purpose_of_use,actor_type='user',actor_id=user.id))
    except ConnectorExecutionError as exc:
        raise HTTPException(403 if 'CONSENT' in exc.code else 422,detail={'code':exc.code})
