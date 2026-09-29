"""Drafts remain in agents; agents.version selects the default published snapshot."""
from copy import deepcopy
from sqlalchemy import select, text
from fastapi import HTTPException
from app.models.agent import Agent
from app.models.agent_release import AgentRelease

DEFINITION_FIELDS = ('id','organization_id','name','description','system_prompt','icon','category',
                     'expert_ids','default_expert_id','a2a_enabled','config','agent_type','canonical_key','aliases')


def definition(agent):
    return {key: deepcopy(getattr(agent, key, None)) for key in DEFINITION_FIELDS}


def released_agent(release):
    agent = Agent(**deepcopy(release.definition))
    agent.version = release.version
    agent.status = 'published'
    agent.is_published = True
    agent.is_prebuilt = False
    agent._release_pack = deepcopy(release.runtime_pack)
    agent._release_pack.pop('_dependency_lock', None)
    agent._release_pack.pop('_evaluation_evidence', None)
    return agent


async def find_release(db, agent, version):
    return (await db.execute(select(AgentRelease).where(
        AgentRelease.organization_id == agent.organization_id,
        AgentRelease.agent_id == agent.id, AgentRelease.version == version,
    ))).scalar_one_or_none()


async def capture(db, agent, version, actor):
    from app.services.agent_runtime_pack import pack_from_tenant_agent
    detached = Agent(**definition(agent))
    detached.version = version
    detached.status = 'published'
    detached.is_published = True
    detached.is_prebuilt = False
    pack = await pack_from_tenant_agent(detached, agent.organization_id, db)
    from app.services.agent_dependencies import draft_locks
    pack['_dependency_lock'] = await draft_locks(db, agent)
    release = AgentRelease(organization_id=agent.organization_id, agent_id=agent.id,
        version=version, definition=definition(agent), runtime_pack=pack, created_by=actor)
    db.add(release)
    await db.flush()
    return release


async def preserve_current(db, agent, actor):
    """Capture a legacy online definition before the first edit, atomically."""
    if agent.is_prebuilt or not agent.is_published:
        return None
    release = await find_release(db, agent, agent.version or '1.0.0')
    return release or await capture(db, agent, agent.version or '1.0.0', actor)


async def publish(db, agent, actor, purpose="quality_improvement"):
    await db.execute(text('UPDATE organizations SET id=id WHERE id=:org'),{'org':agent.organization_id})
    current = await preserve_current(db, agent, actor)
    from app.services.agent_dependencies import draft_locks
    from app.services.release_evaluation import publication_gate
    gate = await publication_gate(db, agent, purpose)
    prior_digest = current.runtime_pack.get('_evaluation_evidence', {}).get('draft_digest') if current else None
    if (not prior_digest or prior_digest == gate['draft_digest']) and current and current.definition == definition(agent) and current.runtime_pack.get('_dependency_lock', []) == await draft_locks(db, agent):
        return current
    if not gate['can_publish']:
        raise HTTPException(409, detail={'error': 'evaluation_required',
            'message': '当前草稿缺少该用途的有效通过评测，请重新评测后发布。', **gate})
    versions = list((await db.execute(select(AgentRelease.version).where(
        AgentRelease.organization_id == agent.organization_id, AgentRelease.agent_id == agent.id,
    ))).scalars())
    if versions:
        def numeric(v):
            try: return tuple(int(n) for n in v.split('.'))
            except ValueError: raise HTTPException(409, detail={'error':'invalid_release_version'})
        highest = max(versions, key=numeric)
        parts = list(numeric(highest))
        if len(parts) != 3: raise HTTPException(409, detail={'error':'invalid_release_version'})
        version = f'{parts[0]}.{parts[1]}.{parts[2]+1}'
    else:
        version = agent.version or '1.0.0'
    release = await capture(db, agent, version, actor)
    release.runtime_pack = {**release.runtime_pack, '_evaluation_evidence': gate}
    agent.version = version
    agent.status = 'published'
    agent.is_published = True
    return release


async def runtime_definition(db, agent, version=None, preview=False):
    if agent is None or agent.is_prebuilt:
        if version or preview:
            raise HTTPException(404, detail={'error':'custom_agent_not_found'})
        return agent
    if preview:
        if agent.status == 'archived':
            raise HTTPException(409, detail={'error':'agent_archived'})
        draft = Agent(**definition(agent))
        draft.version = 'draft'
        draft.status = 'published'
        draft.is_published = True
        draft.is_prebuilt = False
        return draft
    if agent.status != 'published' or not agent.is_published:
        return agent  # Shared lifecycle gate rejects archived/draft Agents.
    release = await find_release(db, agent, version or agent.version or '1.0.0')
    if release:
        from app.services.agent_dependencies import verify_release
        await verify_release(db, release)
        return released_agent(release)
    if version and version != agent.version:
        raise HTTPException(404, detail={'error':'agent_release_not_found'})
    return agent  # Unedited legacy online definition; first edit captures it.
