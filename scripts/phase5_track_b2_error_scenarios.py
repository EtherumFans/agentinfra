"""
Phase 5 Track B-2 — Step 5.12 error scenarios for medical-coding-agent.

Two scenarios:
  1. Empty input → expect structured error (no silent success)
  2. Nonexistent agent → expect HTTP 404 with structured detail
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase5_track_b2_token import get_token


def post_json(url: str, body: dict, token: str | None) -> tuple[int, dict | str]:
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        try:
            return e.code, json.loads(body_text)
        except Exception:
            return e.code, body_text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://127.0.0.1:8000')
    ap.add_argument('--user', default='admin')
    ap.add_argument('--pw', default='admin123')
    ap.add_argument('--out-root', default='outputs/phase5_track_b2/per_agent_runs/medical-coding-agent')
    args = ap.parse_args()

    try:
        token = get_token(args.base, args.user, args.pw)
    except urllib.error.HTTPError as e:
        print(f'  LOGIN HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:200]}', file=sys.stderr)
        return 2
    out_dir = Path(args.out_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    print('=== Scenario 1: empty input ===')
    body = {
        'input': {'text': '', 'extra': {}},
        'runtime_mode': 'corti_like_fast',
        'include_trace': True,
        'include_evidence': True,
    }
    status, env = post_json(f'{args.base}/api/v1/agents/medical-coding-agent/run', body, token)
    print(f'  HTTP {status}')
    if isinstance(env, dict):
        print(f'  envelope error={env.get("error")} reason={env.get("error_reason")}')
    else:
        print(f'  body (str): {str(env)[:200]}')
    (out_dir / '21_error_empty_input.json').write_text(
        json.dumps({'http_status': status, 'envelope': env}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    print()
    print('=== Scenario 2: nonexistent agent ===')
    body = {
        'input': {'text': '心梗', 'extra': {}},
        'runtime_mode': 'corti_like_fast',
    }
    status, env = post_json(f'{args.base}/api/v1/agents/this-agent-does-not-exist/run', body, token)
    print(f'  HTTP {status}')
    if isinstance(env, dict):
        detail = env.get('detail') or env.get('error_reason')
        print(f'  detail={detail}')
    else:
        print(f'  body (str): {str(env)[:200]}')
    (out_dir / '21_error_wrong_agent.json').write_text(
        json.dumps({'http_status': status, 'envelope': env}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
