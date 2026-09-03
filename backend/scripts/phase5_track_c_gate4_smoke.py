"""Phase 5 Track C Gate 4 — Real DeepSeek smoke test.

Runs the 7-stage coding compliance mainline against the live backend,
exercising the same agents that Gate 7's browser walkthrough will use.

Usage (from backend/):
    python scripts/phase5_track_c_gate4_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

BASE_URL = os.environ.get("ICODER_BASE_URL", "http://127.0.0.1:8000")
TOKEN_FILE = Path(os.environ.get("ICODER_TOKEN_FILE", "/tmp/icoder_token.txt"))


def _load_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    raise SystemExit("No token at /tmp/icoder_token.txt — login first.")


def _post_agent(agent_id: str, input_text: str, token: str) -> dict:
    body = json.dumps({"input": {"text": input_text}}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/agents/{agent_id}/run",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"_error": f"HTTP {e.code}: {body[:200]}", "_latency_ms": int((time.monotonic() - t0) * 1000)}
    payload["_latency_ms"] = int((time.monotonic() - t0) * 1000)
    return payload


def main() -> int:
    token = _load_token()
    sample = (
        "患者男性,78岁,因跌倒后腰背疼痛12小时入院。"
        "既往糖尿病史10年,高血压20年。"
        "查体:T12棘突压痛(+),叩痛(+)。"
        "MRI:T12椎体压缩性骨折。"
        "入院诊断:T12椎体压缩性骨折,2型糖尿病,高血压病3级。"
        "住院期间行后路椎体成形术+骨水泥注入术,手术顺利。"
        "术后恢复良好,出院。"
    )
    stages = [
        ("discharge-summary-structuring", sample),
        ("medical-coding-agent", sample),
        ("principal-diagnosis-review", sample),
        ("evidence-extractor", sample),
        ("compliance-guardrail", json.dumps({"primary_diagnosis": {"code": "S22.000"}, "secondary_diagnoses": [{"code": "M80.900"}], "procedures": [{"code": "81.0100"}]}, ensure_ascii=False)),
        ("note-completeness", sample),
        ("drg-analyzer", json.dumps({"primary_diagnosis": {"code": "S22.000"}, "procedures": [{"code": "81.0100"}]}, ensure_ascii=False)),
    ]
    print(f"=== Phase 5 Track C Gate 4 smoke ===")
    print(f"BASE_URL={BASE_URL} sample_len={len(sample)}\n")
    for stage, input_text in stages:
        out = _post_agent(stage, input_text, token)
        lat = out.get("_latency_ms", 0)
        err = out.get("_error")
        if err:
            print(f"[FAIL] {stage:38s} {lat:5d}ms  {err}")
            continue
        # Pull a structured-output snippet for visibility.
        so = out.get("structured_output") or {}
        cost = (out.get("cost") or {}).get("amount", 0.0)
        keys = list(so.keys())[:4] if isinstance(so, dict) else []
        print(f"[OK]   {stage:38s} {lat:5d}ms  cost=¥{cost:.6f}  keys={keys}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
