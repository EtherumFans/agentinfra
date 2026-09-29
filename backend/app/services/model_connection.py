"""Encrypted, tenant-bound credentials and fixed-endpoint DeepSeek adapter."""
import base64
import hashlib
import json
import os
from cryptography.fernet import Fernet
from app.config import settings
from icoder_runtime.core.llm_gateway import DeepSeekProvider


def cipher():
    # Require a deployment-provided stable key, never the ephemeral dev fallback.
    key = os.environ.get('ICODER_SECRET_KEY', '').strip()
    if len(key) < 32:
        raise ValueError('stable_encryption_key_required')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(
        ('icoder-model-credentials-v1\0' + key).encode()).digest()))


def encrypt_key(org_id, key):
    return cipher().encrypt(json.dumps({'org_id': org_id, 'key': key}).encode()).decode()


def provider_for(row):
    payload = json.loads(cipher().decrypt(row.encrypted_key.encode()))
    if payload['org_id'] != row.organization_id:
        raise ValueError('credential_tenant_mismatch')
    return DeepSeekProvider(api_key=payload['key'], base_url='https://api.deepseek.com',
                            model=row.model, max_tokens=settings.LLM_MAX_TOKENS,
                            timeout=settings.LLM_TIMEOUT,
                            thinking=os.environ.get('ICODER_DEEPSEEK_THINKING') or None)


def public_connection(row):
    return {'configured': row is not None, 'provider': 'deepseek',
            'model': row.model if row else 'deepseek-v4-flash',
            'enabled': bool(row and row.enabled), 'version': row.version if row else 0}
