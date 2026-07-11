"""Phase 5 Track B B-1.4 — smoke run 5 deep-audit agents (mock LLM).

Runs all 5 B-1.4 agents through the unified /api/v1/agents/{id}/run
endpoint with ICODER_DISABLE_AUTH_FOR_TESTS=1 + LLM_PROVIDER=mock so we
capture the envelope shape, latency, and output schema for each.

Real DeepSeek latency is referenced from Phase 4-F3 smoke data
(reports/corti_parity/phase4_f3_core_agent_smoke/).

Usage:
    cd backend && python ../scripts/phase5_track_b_b1_4_smoke.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.middleware.auth import get_current_user, get_current_organization  # noqa: E402


def _make_mock_user(role: str = "admin") -> dict:
    return {
        "user_id": "test-user-1",
        "user_email": "test@icoder.local",
        "role": role,
        "organization_id": "org_default1",
        "permissions": ["*"],
    }


def _make_mock_org() -> dict:
    return {
        "id": "org_default1",
        "slug": "default-org",
        "name": "Default Org",
    }


app.dependency_overrides[get_current_user] = lambda: _make_mock_user("admin")
app.dependency_overrides[get_current_organization] = lambda: _make_mock_org()

OUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "phase5_track_b" / "b1_4_smoke"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 5 deep-audit agents per user decision "C hybrid: 3 EXACT + 2 ICODER_ONLY"
AGENTS = [
    {
        "agent_id": "medical-coding-agent",
        "pair": "001",
        "label": "medical_coding",
        "input_text": "患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。",
    },
    {
        "agent_id": "code-validation-agent",
        "pair": "002",
        "label": "code_validation",
        "input_text": "校验: primary=S22.000 (T12 椎体压缩性骨折), secondary=[M80.900]",
    },
    {
        "agent_id": "note-completeness-agent",
        "pair": "003",
        "label": "note_completeness",
        "input_text": "患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。",
    },
    {
        "agent_id": "drg-analyzer",
        "pair": "004",
        "label": "drg_analyzer",
        "input_text": "主诊断=S22.000 (T12 椎体压缩性骨折), 其他诊断=[M80.900], 手术=[], 性别=男, 年龄=78",
    },
    {
        "agent_id": "evidence-extractor",
        "pair": "005",
        "label": "evidence_extractor",
        "input_text": "患者男性,78岁,MRI 显示 T12 椎体压缩性骨折。",
    },
]


def run_smoke(agent: dict, client: TestClient) -> dict:
    aid = agent["agent_id"]
    payload = {
        "input": {
            "text": agent["input_text"],
            "extra": {},
        },
    }
    resp = client.post(f"/api/v1/agents/{aid}/run", json=payload)
    return {
        "status_code": resp.status_code,
        "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
    }


def main() -> None:
    summary = []
    with TestClient(app) as client:
        for agent in AGENTS:
            print(f"\n=== {agent['pair']} {agent['agent_id']} ===")
            result = run_smoke(agent, client)
            print(f"status: {result['status_code']}")
            out_path = OUT_DIR / f"pair{agent['pair']}_{agent['label']}_smoke.json"
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"saved: {out_path}")

            body = result["body"] if isinstance(result["body"], dict) else {}
            summary.append({
                "pair": agent["pair"],
                "agent_id": agent["agent_id"],
                "label": agent["label"],
                "status": result["status_code"],
                "run_id": body.get("run_id"),
                "trace_id": body.get("trace_id"),
                "runtime_mode": body.get("runtime_mode"),
                "latency_ms": body.get("latency_ms"),
                "error": body.get("error"),
                "error_reason": body.get("error_reason"),
                "summary": body.get("summary"),
                "result_keys": list(body.get("result", {}).keys()) if isinstance(body.get("result"), dict) else None,
                "manual_review_required": body.get("manual_review_required"),
                "trace_events_count": len(body.get("trace_events") or []),
            })

    summary_path = OUT_DIR / "_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSummary: {summary_path}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
