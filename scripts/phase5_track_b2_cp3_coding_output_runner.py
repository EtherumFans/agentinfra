"""
Phase 5 Track B-2 CP3 — compliance-guardrail-agent runner.

RuleEngineProvider expects structured input, not plain text. This script
chains medical-coding output → compliance-guardrail input by:

  1. Run medical-coding-agent on a fixture → get CodeAssignmentV2
  2. Wrap the medical-coding result as `coding_output` and pass to
     compliance-guardrail-agent
  3. Save both envelopes

Usage:
    python scripts/phase5_track_b2_cp3_coding_output_runner.py \\
        --fixture fixtures/phase5_track_b2/01_orthopedics.json \\
        --tag 01_orthopedics
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixture', required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--base', default='http://127.0.0.1:8000')
    ap.add_argument('--user', default='admin')
    ap.add_argument('--pw', default='admin123')
    ap.add_argument('--out-root', default='outputs/phase5_track_b2/per_agent_runs/compliance-guardrail-agent')
    args = ap.parse_args()

    token = get_token(args.base, args.user, args.pw)

    # Step 1: run medical-coding-agent
    fixture = json.loads(Path(args.fixture).read_text(encoding='utf-8'))
    input_text = fixture['input_text']
    print(f'[cp3] step 1: medical-coding-agent on {args.tag}…', flush=True)
    status, mc_env = post(
        f'{args.base}/api/v1/agents/medical-coding-agent/run',
        {
            'input': {'text': input_text, 'extra': {}},
            'runtime_mode': 'corti_like_fast',
            'include_trace': True,
            'include_evidence': True,
        },
        token,
    )
    print(f'  HTTP {status}, run_id={mc_env.get("run_id")}', flush=True)
    mc_codes = (mc_env.get('result') or {}).get('codes') or []
    print(f'  codes_count={len(mc_codes)}', flush=True)

    # Step 2: build compliance-guardrail input with coding_output shape
    # per MedicalCodingOutputSchema (the shape _validate_coding_output expects).
    # Translate medical-coding v2 codes (with `system` field) → DiagnosisEntry
    # shape (code/description/confidence/category/evidence only).
    def _to_entry(c: dict, default_cat: str) -> dict:
        return {
            'code': c.get('code', ''),
            'description': c.get('description', ''),
            'confidence': c.get('confidence', 0.0),
            'category': c.get('category') or default_cat,
            'evidence': c.get('evidence', []) or [],
        }

    primary = next((c for c in mc_codes if c.get('type') == 'primary_diagnosis'), None)
    secondary = [c for c in mc_codes if c.get('type') == 'secondary_diagnosis']
    procedures = [c for c in mc_codes if c.get('type') == 'procedure']
    coding_output_schema = {
        'primary_diagnosis': _to_entry(primary, 'principal') if primary else {},
        'secondary_diagnoses': [_to_entry(c, 'secondary') for c in secondary],
        'procedures': [_to_entry(c, 'secondary') for c in procedures],
        'encounter_summary': mc_env.get('summary', ''),
        'validation_summary': {
            'passed': True,
            'issues_found': [],
            'manual_review_required': False,
        },
    }

    print(f'[cp3] step 2: compliance-guardrail-agent with coding_output ({len(mc_codes)} codes)…', flush=True)
    status, cg_env = post(
        f'{args.base}/api/v1/agents/compliance-guardrail-agent/run',
        {
            'input': {
                'text': input_text,  # some text is required (min_length=1)
                'extra': {'coding_output': coding_output_schema},  # schema-shaped
            },
            'runtime_mode': 'corti_like_fast',
            'include_trace': True,
            'include_evidence': True,
        },
        token,
    )
    print(f'  HTTP {status}, run_id={cg_env.get("run_id")}', flush=True)
    print(f'  summary: {(cg_env.get("summary") or "")[:200]}', flush=True)

    cg_env['_input_shape'] = 'coding_output (chained from medical-coding-agent)'
    cg_env['_medical_coding_run_id'] = mc_env.get('run_id')

    out_dir = Path(args.out_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'{args.tag}.json'
    out_path.write_text(json.dumps(cg_env, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[cp3] → {out_path}', flush=True)

    # Print structured issues if any
    issues = (cg_env.get('result') or {}).get('issues') or []
    if issues:
        print(f'[cp3] {len(issues)} compliance issues:')
        for i, iss in enumerate(issues[:5]):
            print(f'  [{i}] {iss.get("code","")} | {iss.get("severity","")} | {iss.get("message","")[:80]}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
