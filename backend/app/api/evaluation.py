# DEPRECATED (P1.3 Stage 5, 2026-07-02) — F1 评估非 Corti 方向. Phase 2 删. 见 docs/backlog/PRODUCT_BACKLOG.md §5.
# iCoDer — Evaluation API (Runtime-integrated)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.post("/run")
async def run_evaluation():
    """Run gold case evaluation via PlatformRuntime + Medical Coding Agent. No auth for dev."""
    import json, time, hashlib
    from pathlib import Path

    gold_path = Path(__file__).parent.parent.parent / "gold_cases" / "samples.json"
    if not gold_path.exists():
        raise HTTPException(status_code=404, detail="Gold cases file not found")

    cases = json.loads(gold_path.read_text(encoding="utf-8")).get("gold_cases", [])
    if not cases:
        raise HTTPException(status_code=404, detail="No gold cases found")

    # Get PlatformRuntime
    try:
        from app.main import app as _app
        rt = _app.state.platform_runtime if hasattr(_app.state, "platform_runtime") else None
    except Exception:
        rt = None

    per_case = []
    correct = 0
    total = len(cases)
    t0 = time.time()

    for case in cases:
        case_id = case["id"]
        encounter = case["encounter_text"]
        expected = case.get("expected", {})
        exp_dx = (expected.get("primary_diagnosis") or {}).get("code", "")

        actual_dx = ""
        run_id = ""
        latency = 0
        is_mock = None

        if rt:
            try:
                from icoder_runtime.core.registry import get_registry
                reg = get_registry()
                rec = reg.find("medical-coding-agent-1.0.0")
                if rec:
                    start = time.time()
                    result = await rt.run_agent(rec.agent_id, encounter)
                    latency = int((time.time() - start) * 1000)
                    run_id = result.get("review_id", "")
                    output = result.get("output", "")
                    try:
                        parsed = json.loads(output) if isinstance(output, str) and output.strip().startswith("{") else {}
                        actual_dx = (parsed.get("primary_diagnosis") or {}).get("code", "")
                    except Exception:
                        pass
            except Exception:
                pass

        match = (actual_dx == exp_dx)
        if match:
            correct += 1

        per_case.append({
            "case_id": case_id,
            "category": case.get("category", "unknown"),
            "title": case.get("title", ""),
            "expected_dx": exp_dx,
            "actual_dx": actual_dx,
            "correct": match,
            "run_id": run_id,
            "latency_ms": latency,
        })

    elapsed = time.time() - t0

    # Per-category
    cats = {}
    for r in per_case:
        c = r["category"]
        if c not in cats:
            cats[c] = {"total": 0, "correct": 0}
        cats[c]["total"] += 1
        if r["correct"]:
            cats[c]["correct"] += 1

    return {
        "total_cases": total,
        "correct": correct,
        "primary_dx_match_rate": round(correct / max(total, 1), 4),
        "per_case": per_case,
        "per_category": {k: {"total": v["total"], "correct": v["correct"],
                            "rate": round(v["correct"] / max(v["total"], 1), 4)}
                        for k, v in sorted(cats.items())},
        "elapsed_seconds": round(elapsed, 1),
        "execution_mode": "platform_runtime",
    }
