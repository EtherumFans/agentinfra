"""Repeatable synthetic local-rule benchmark; no clinical or network claims."""
from __future__ import annotations
import argparse
import asyncio
import concurrent.futures
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from official_agents.note_completeness.agent_legacy import run

SAMPLE = '主诉：咳嗽。现病史：咳嗽三天。既往史：无特殊。体格检查：未记录。辅助检查：未记录。诊断：未明确。治疗经过：观察。'

def measure(index):
    start=time.perf_counter()
    result=asyncio.run(run(SAMPLE, run_id=f'benchmark-{index}'))
    return (time.perf_counter()-start)*1000, result['completeness_score'] < 1

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    output={'scope':'synthetic_local_rule_only', 'clinical_quality_proven':False,
            'python':platform.python_version(), 'platform':platform.platform(),
            'sample_sha256':hashlib.sha256(SAMPLE.encode()).hexdigest(), 'workloads':[]}
    for workers in [1,4,8]:
        start=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results=list(executor.map(measure, range(200)))
        latencies=sorted(item[0] for item in results)
        output['workloads'].append({'workers':workers, 'calls':len(results),
            'p50_ms':latencies[99], 'p95_ms':latencies[189], 'p99_ms':latencies[197],
            'wall_seconds':time.perf_counter()-start, 'unexpected_results':sum(not item[1] for item in results)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False))

if __name__ == '__main__': main()
