"""Minimal organization model setup. Only synthetic connectivity text leaves here."""
import asyncio
import time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user, require_org_role, require_org_membership
from app.models.model_connection import ModelConnection
from app.models.audit_log import AuditLog
from app.services.model_connection import cipher, encrypt_key, provider_for, public_connection
from icoder_runtime.core.data_policy import RuntimeDataPolicy

router = APIRouter(prefix='/api/v1/model-connection', tags=['model-connection'])


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: Literal['deepseek-v4-flash', 'deepseek-v4-pro'] = 'deepseek-v4-flash'
    api_key: SecretStr = SecretStr('')
    expected_version: int


class DisableInput(BaseModel):
    expected_version: int


def policy_for(request):
    return getattr(request.app.state, 'data_policy', None) or RuntimeDataPolicy.from_env()


@router.get('')
async def read_connection(request: Request, response: Response,
                          org=Depends(get_current_organization), member=Depends(require_org_membership),
                          db: AsyncSession=Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    row = await db.get(ModelConnection, org.id)
    try:
        cipher(); encryption_ready = True
    except ValueError:
        encryption_ready = False
    return {**public_connection(row), 'editable': member.role.value in {'owner', 'admin'},
            'encryption_ready': encryption_ready,
            'external_allowed': policy_for(request).egress_decision('deepseek').get('decision') == 'allow'}


def audit(db, org, user, action, version):
    db.add(AuditLog(user_id=user.id, username=user.username, organization_id=org.id,
                    action=action, resource_type='model_connection', resource_id=org.id,
                    details={'provider': 'deepseek', 'version': version}))


@router.post('/test-and-enable')
async def test_and_enable(body: ConnectionInput, request: Request, response: Response,
                          org=Depends(get_current_organization), user=Depends(get_current_user),
                          _member=Depends(require_org_role('owner', 'admin')),
                          db: AsyncSession=Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    if policy_for(request).egress_decision('deepseek').get('decision') != 'allow':
        raise HTTPException(403, '当前部署未允许向 DeepSeek 发送数据，请联系部署管理员开启外部模型访问。')
    row = await db.get(ModelConnection, org.id)
    version = row.version if row else 0
    if body.expected_version != version:
        raise HTTPException(409, '配置已更新，请刷新后重试。')
    # Bound repeated paid probes; the limit is per tenant, not per user.
    cooldowns = getattr(request.app.state, 'model_connection_probes', None)
    if cooldowns is None:
        cooldowns = {}; request.app.state.model_connection_probes = cooldowns
    if time.monotonic() - cooldowns.get(org.id, -60) < 10:
        raise HTTPException(429, '请稍后再测试连接。')
    key = body.api_key.get_secret_value().strip()
    if key and (len(key) > 512 or any(c.isspace() for c in key)):
        raise HTTPException(422, 'API Key 格式不正确。')
    if not key and not row:
        raise HTTPException(422, '请填写 API Key。')
    try:
        encrypted = encrypt_key(org.id, key) if key else row.encrypted_key
        candidate = ModelConnection(organization_id=org.id, model=body.model, encrypted_key=encrypted)
        provider = provider_for(candidate)
    except Exception:
        raise HTTPException(503, '密钥加密服务不可用，请联系部署管理员检查持久化服务密钥。') from None
    cooldowns[org.id] = time.monotonic()
    try:
        result = await asyncio.wait_for(provider.generate(
            messages=[{'role': 'user', 'content': 'Synthetic connectivity check. Reply exactly ICODER_OK.'}],
            context={'max_tokens': 256, 'max_attempts': 1, 'timeout_seconds': 30}), 35)
    except Exception:
        raise HTTPException(502, '连接测试失败，原配置保持不变，请检查密钥、额度和网络。') from None
    if result.get('degraded') or result.get('finish_reason') != 'stop' or result.get('content', '').strip() != 'ICODER_OK':
        raise HTTPException(502, '连接测试未通过，原配置保持不变，请检查密钥、额度和模型权限。')
    values = dict(model=body.model, encrypted_key=encrypted, enabled=True, version=version + 1)
    try:
        if row:
            changed = await db.execute(update(ModelConnection).where(
                ModelConnection.organization_id == org.id, ModelConnection.version == version).values(**values))
            if changed.rowcount != 1:
                raise HTTPException(409, '配置已更新，请刷新后重试。')
        else:
            db.add(ModelConnection(organization_id=org.id, **values))
        audit(db, org, user, 'model_connection.enabled', version + 1)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, '配置已更新，请刷新后重试。') from None
    return {'configured': True, 'provider': 'deepseek', 'model': body.model,
            'enabled': True, 'version': version + 1, 'connection_verified': True,
            'latency_ms': result.get('latency_ms', 0)}


@router.post('/disable')
async def disable(body: DisableInput, org=Depends(get_current_organization), user=Depends(get_current_user),
                  _member=Depends(require_org_role('owner', 'admin')), db: AsyncSession=Depends(get_db)):
    changed = await db.execute(update(ModelConnection).where(
        ModelConnection.organization_id == org.id, ModelConnection.version == body.expected_version
    ).values(enabled=False, version=body.expected_version + 1))
    if changed.rowcount != 1:
        raise HTTPException(409, '配置已更新，请刷新后重试。')
    audit(db, org, user, 'model_connection.disabled', body.expected_version + 1)
    await db.commit()
    return {'enabled': False, 'version': body.expected_version + 1}
