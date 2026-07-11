"""
Phase 5 Track B-2 — Per-agent run runner.

Hits the unified /api/v1/agents/{agent_id}/run endpoint with a given fixture
and saves the full envelope to outputs/phase5_track_b2/per_agent_runs/{agent}/{tag}.json.

Why a runner instead of curl: Windows shell mangles JSON quotes; this Python
runner reads the fixture from disk and posts the body via urllib so quoting
is a non-issue.

Usage:
    python scripts/phase5_track_b2_per_agent_runner.py \\
        --agent medical-coding-agent \\
        --fixture fixtures/phase5_track_b2/02_cardiology.json \\
        --tag 13_long_input \\
        --user admin --pw admin123 \\
        --base http://127.0.0.1:8000
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
from phase5_track_b2_token import get_token  # shared JWT cache


def post_json(url: str, body: dict, token: str | None) -> dict:
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode('utf-8'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--agent', required=True, help='short agent_id e.g. medical-coding-agent')
    ap.add_argument('--fixture', required=True, help='path to fixture JSON')
    ap.add_argument('--tag', required=True, help='output filename tag (e.g. 13_long_input)')
    ap.add_argument('--user', default='admin')
    ap.add_argument('--pw', default='admin123')
    ap.add_argument('--base', default='http://127.0.0.1:8000')
    ap.add_argument('--runtime-mode', default='corti_like_fast')
    ap.add_argument('--out-root', default='outputs/phase5_track_b2/per_agent_runs')
    args = ap.parse_args()

    fixture = json.loads(Path(args.fixture).read_text(encoding='utf-8'))
    input_text = fixture['input_text']

    print(f'[runner] token (cached after first login)…', flush=True)
    try:
        token = get_token(args.base, args.user, args.pw)
    except urllib.error.HTTPError as e:
        print(f'  LOGIN HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:200]}', file=sys.stderr)
        return 2
    if not token:
        print('  LOGIN FAILED', file=sys.stderr)
        return 2

    body = {
        'input': {'text': input_text, 'extra': {}},
        'runtime_mode': args.runtime_mode,
        'include_trace': True,
        'include_evidence': True,
    }
    url = f'{args.base}/api/v1/agents/{args.agent}/run'
    print(f'[runner] POST {url}', flush=True)
    print(f'[runner] fixture={args.fixture} text_len={len(input_text)}', flush=True)
    t0 = time.perf_counter()
    try:
        env = post_json(url, body, token)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        print(f'  HTTPError {e.code}: {body_text[:400]}', file=sys.stderr)
        env = {'error': True, 'error_reason': f'HTTP {e.code}', 'http_body': body_text[:1000]}
    dt_ms = int((time.perf_counter() - t0) * 1000)

    env['_client_wall_ms'] = dt_ms
    env['_fixture'] = args.fixture
    env['_agent'] = args.agent
    env['_tag'] = args.tag
    env['_ts'] = time.strftime('%Y-%m-%dT%H:%M:%S')

    out_dir = Path(args.out_root) / args.agent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{args.tag}.json'
    out_path.write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[runner] → {out_path}  (envelope error={env.get("error")})', flush=True)

    # Quick summary
    summary = {
        'run_id': env.get('run_id'),
        'trace_id': env.get('trace_id'),
        'latency_ms': env.get('latency_ms'),
        'runtime_mode': env.get('runtime_mode'),
        'error': env.get('error'),
        'cost': env.get('cost'),
        'codes_count': len((env.get('result') or {}).get('codes') or []),
        'evidence_count': len(env.get('evidence') or []),
        'trace_events_count': len(env.get('trace_events') or []),
        'warnings_count': len(env.get('warnings') or []),
        'manual_review_required': env.get('manual_review_required'),
    }
    print('[runner] summary:')
    for k, v in summary.items():
        print(f'  {k}: {v}')
    return 0 if not env.get('error') else 1


if __name__ == '__main__':
    sys.exit(main())
