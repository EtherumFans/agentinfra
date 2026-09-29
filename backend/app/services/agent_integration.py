"""Fail-closed binding to a tenant Agent's selected published snapshot.

Release storage is provided by agent_releases. External model,
tool and knowledge-source versions are outside this fingerprint.
"""
import hashlib
import json

from fastapi import HTTPException


def configuration_digest(agent) -> str:
    fields = ('id', 'organization_id', 'version', 'system_prompt', 'config',
              'expert_ids', 'default_expert_id', 'a2a_enabled')
    payload = {field: getattr(agent, field, None) for field in fields}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def integration_manifest(agent) -> dict:
    if agent.is_prebuilt or agent.status != 'published' or not agent.is_published:
        raise HTTPException(409, detail={'error': 'integration_requires_published_custom_agent'})
    return {
        'agent_id': agent.id,
        'name': agent.name,
        'version': agent.version,
        'configuration_digest': configuration_digest(agent),
        'run_path': f'/api/v1/agents/{agent.id}/run',
        'token_path': '/api/oauth/token',
        'binding_mode': 'published_snapshot',
    }


def validate_integration_binding(agent, version: str | None, digest: str | None) -> None:
    if version is None and digest is None:
        return
    if not version or not digest:
        raise HTTPException(422, detail={'error': 'integration_binding_incomplete'})
    if agent is None:
        raise HTTPException(404, detail={'error': 'integration_agent_not_found'})
    manifest = integration_manifest(agent)
    if version != manifest['version'] or digest != manifest['configuration_digest']:
        raise HTTPException(409, detail={'error': 'integration_configuration_changed',
                                        'message': '版本与配置摘要不匹配，请重新获取该发布版本的集成配置。'})
