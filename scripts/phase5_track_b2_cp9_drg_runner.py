"""Phase 5 Track B-2 CP9 — drg-analyzer runner.

drg-analyzer expects (text + codes) input, same as evidence-extractor.
This script builds the input from a fixture's input_text + gold_codes and
posts to /api/v1/agents/drg-analyzer/run.

Output: outputs/phase5_track_b2/per_agent_runs/drg-analyzer/{tag}.json
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


def post(url: str, body: dict, token: str) -> tuple[int, dict]:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        try:
            return e.code, json.loads(body_text)
        except Exception:
            return e.code, {'_raw': body_text[:500]}


def build_input(fixture: dict, tag: str) -> tuple[str, list[str]]:
    input_text = fixture['input_text']
    gold_codes = fixture.get('gold_codes') or []

    if tag in ('14_missing_info', '17_invalid_input'):
        # Use fixture input as-is (likely no real content + no codes)
        return input_text, gold_codes

    augmented = (
        f"{input_text}\n\n"
        f"---\n待评估编码集 (DRG/DIP 风险复核):\n"
        + "\n".join(f"- {c}" for c in gold_codes)
    )
    return augmented, gold_codes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixture', required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--base', default='http://127.0.0.1:8000')
    ap.add_argument('--user', default='admin')
    ap.add_argument('--pw', default='admin123')
    args = ap.parse_args()

    token = get_token(args.base, args.user, args.pw)
    fixture = json.loads(Path(args.fixture).read_text(encoding='utf-8'))
    augmented_input, gold_codes = build_input(fixture, args.tag)

    body = {
        'input': {'text': augmented_input, 'extra': {'codes': gold_codes}},
        'runtime_mode': 'corti_like_fast',
        'include_trace': True,
        'include_evidence': True,
    }
    url = f'{args.base}/api/v1/agents/drg-analyzer/run'
    t0 = time.perf_counter()
    status, env = post(url, body, token)
    dt_ms = int((time.perf_counter() - t0) * 1000)
    print(f'[{args.tag}] HTTP {status} run_id={env.get("run_id")} '
          f'latency={env.get("latency_ms")}ms cost={env.get("cost")} '
          f'client_wall={dt_ms}ms')

    env['_input_shape'] = f'augmented_text ({len(augmented_input)} chars) + codes ({len(gold_codes)})'
    env['_gold_codes'] = gold_codes
    env['_client_wall_ms'] = dt_ms
    env['_fixture'] = args.fixture
    env['_tag'] = args.tag
    env['_ts'] = time.strftime('%Y-%m-%dT%H:%M:%S')

    out_dir = Path('outputs/phase5_track_b2/per_agent_runs/drg-analyzer')
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f'{args.tag}.json').write_text(
        json.dumps(env, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
