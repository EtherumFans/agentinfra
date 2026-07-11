"""
Phase 5 Track B-2 — shared JWT cache.

Logs in once and caches the access_token to
outputs/phase5_track_b2/.dev_token until it's stale (>1h old or missing).
Avoids the 5-logins/5-min cap in LoginRateLimiter (auth.py:435).

Other scripts import `get_token(base, user, pw)` instead of calling login
per-run.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error
from pathlib import Path


CACHE_PATH = Path('outputs/phase5_track_b2/.dev_token')
_MAX_AGE_S = 3600  # 1h


def _read_cache() -> str | None:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding='utf-8'))
    except Exception:
        return None
    if time.time() - data.get('ts', 0) > _MAX_AGE_S:
        return None
    return data.get('access_token')


def _write_cache(token: str) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps({'access_token': token, 'ts': time.time()}),
        encoding='utf-8',
    )


def login_fresh(base: str, user: str, pw: str) -> str:
    body = {'username': user, 'password': pw}
    req = urllib.request.Request(
        f'{base}/api/auth/login',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        out = json.loads(r.read().decode('utf-8'))
    return out.get('access_token') or out.get('token') or ''


def get_token(base: str, user: str = 'admin', pw: str = 'admin123') -> str:
    cached = _read_cache()
    if cached:
        return cached
    token = login_fresh(base, user, pw)
    if token:
        _write_cache(token)
    return token


if __name__ == '__main__':
    import sys
    base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
    user = sys.argv[2] if len(sys.argv) > 2 else 'admin'
    pw = sys.argv[3] if len(sys.argv) > 3 else 'admin123'
    t = get_token(base, user, pw)
    print(f'token: {t[:32]}… ({len(t)} chars)' if t else 'LOGIN FAILED')
