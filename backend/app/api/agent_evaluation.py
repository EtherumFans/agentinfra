# DEPRECATED (P1.3 Stage 5, 2026-07-02) — F1 评估非 Corti 方向. Phase 2 删. 见 docs/backlog/PRODUCT_BACKLOG.md §5.
"""Agent Evaluation — per-agent gold case evaluation with history tracking."""
import json, time, hashlib, logging
from pathlib import Path
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.middleware.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agent-evaluation"])

# ── In-memory eval history (replace with DB in prod) ──
_eval_history: dict[str, list[dict]] = {}  # agent_ref → [eval_results]


@router.post("/{agent_id}/evaluate")
async def evaluate_agent(
    agent_id: str,
    user: User = Depends(get_current_user),
    category: str = Query("", description="Filter gold cases by category"),
    limit: int = Query(50, le=200, description="Max cases to evaluate"),
):
    """Run gold case evaluation against a specific agent.

    Returns per-case comparison, aggregate metrics, and saves to history.
    """
    gold_path = Path(__file__).parent.parent.parent / "gold_cases" / "samples.json"
    if not gold_path.exists():
        raise HTTPException(status_code=404, detail="Gold cases file not found")

    all_cases = json.loads(gold_path.read_text(encoding="utf-8")).get("gold_cases", [])
    cases = [c for c in all_cases if not category or c.get("category", "") == category][:limit]
    if not cases:
        raise HTTPException(status_code=404, detail="No gold cases found")

    # Get PlatformRuntime
    try:
        from app.main import app as _app
        rt = _app.state.platform_runtime if hasattr(_app.state, "platform_runtime") else None
    except Exception:
        rt = None

    per_case = []
    correct_dx = 0
    correct_proc = 0
    total_dx = 0
    total_proc = 0
    t0 = time.time()

    for case in cases:
        case_id = case["id"]
        encounter = case["encounter_text"]
        expected = case.get("expected", {})
        exp_dx = (expected.get("primary_diagnosis") or {}).get("code", "")
        exp_proc = (expected.get("primary_procedure") or {}).get("code", "")

        actual_dx = ""
        actual_proc = ""
        run_id = ""
        latency = 0

        if rt and exp_dx:
            try:
                start = time.time()
                result = await rt.run_agent(agent_id, encounter)
                latency = int((time.time() - start) * 1000)
                run_id = result.get("review_id", "")
                output = result.get("output", "")
                try:
                    # Handle markdown-wrapped JSON (```json ... ```)
                    clean = output.strip()
                    if clean.startswith("```"):
                        clean = clean.split("```")[1]
                        if clean.startswith("json"): clean = clean[4:]
                        clean = clean.strip()
                    parsed = json.loads(clean) if clean.startswith("{") else {}

                    # Extract primary diagnosis — handle multiple formats
                    if "primary_diagnosis" in parsed:
                        actual_dx = (parsed.get("primary_diagnosis") or {}).get("code", "")
                    elif "diagnosis_codes" in parsed:
                        codes = parsed.get("diagnosis_codes", [])
                        actual_dx = codes[0].get("code", "") if codes else ""
                    elif "diagnoses" in parsed:
                        codes = parsed.get("diagnoses", [])
                        actual_dx = codes[0].get("code", "") if codes else ""

                    # Extract primary procedure
                    if "procedures" in parsed:
                        procs = parsed.get("procedures", [])
                        actual_proc = procs[0].get("code", "") if procs else ""
                    elif "procedure_codes" in parsed:
                        procs = parsed.get("procedure_codes", [])
                        actual_proc = procs[0].get("code", "") if procs else ""
                except Exception:
                    pass
            except Exception:
                pass

        dx_match = (actual_dx == exp_dx) if exp_dx else None
        proc_match = (actual_proc == exp_proc) if exp_proc else None
        if dx_match: correct_dx += 1
        if proc_match: correct_proc += 1
        if exp_dx: total_dx += 1
        if exp_proc: total_proc += 1

        per_case.append({
            "case_id": case_id, "category": case.get("category", "unknown"),
            "expected_dx": exp_dx, "actual_dx": actual_dx, "dx_match": dx_match,
            "expected_proc": exp_proc, "actual_proc": actual_proc, "proc_match": proc_match,
            "run_id": run_id, "latency_ms": latency,
        })

    elapsed = time.time() - t0

    result = {
        "agent_id": agent_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(cases),
        "primary_dx_accuracy": round(correct_dx / max(total_dx, 1), 4),
        "primary_proc_accuracy": round(correct_proc / max(total_proc, 1), 4),
        "correct_dx": correct_dx, "total_dx": total_dx,
        "correct_proc": correct_proc, "total_proc": total_proc,
        "per_case": per_case,
        "elapsed_seconds": round(elapsed, 1),
        "execution_mode": "platform_runtime",
    }

    # Save history
    _eval_history.setdefault(agent_id, []).append(result)
    if len(_eval_history.get(agent_id, [])) > 20:
        _eval_history[agent_id] = _eval_history[agent_id][-20:]

    return result


@router.get("/{agent_id}/evaluation-history")
async def agent_evaluation_history(agent_id: str):
    """Get evaluation history for a specific agent."""
    history = _eval_history.get(agent_id, [])
    return {
        "agent_id": agent_id,
        "evaluations": history,
        "total": len(history),
        "trend": [
            {"date": h["evaluated_at"], "dx_accuracy": h["primary_dx_accuracy"],
             "proc_accuracy": h.get("primary_proc_accuracy", 0)}
            for h in history[-10:]
        ],
    }
