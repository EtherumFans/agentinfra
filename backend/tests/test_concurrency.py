"""Concurrency stress test for the coding audit pipeline.
Run multiple pipeline executions in parallel to verify stability under load.

Usage:
    python -m pytest tests/test_concurrency.py -v -s
    or directly:
    python tests/test_concurrency.py
"""
import asyncio
import time
import json
import logging
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("concurrency_test")

# This test drives a separately started server on localhost:8000 and therefore
# must never be collected by the hermetic default suite. Run it explicitly in
# a controlled live-server environment with ``pytest -m infra``.
pytestmark = [pytest.mark.infra, pytest.mark.asyncio]


CLINICAL_TEXTS = [
    "Back pain for 4 months. MRI shows T7 T9 T12 L2 compression fractures. "
    "Diagnosis: lumbar compression fracture, osteoporosis. "
    "Procedure: percutaneous kyphoplasty T7 T9 T12 L2.",
    "Patient admitted for community-acquired pneumonia. Chest X-ray shows left lower lobe infiltrate. "
    "Sputum culture positive for Streptococcus pneumoniae. "
    "Diagnosis: bacterial pneumonia, left lower lobe. Treated with IV antibiotics.",
    "68-year-old male with acute myocardial infarction. "
    "Cardiac catheterization shows 90% LAD stenosis. "
    "Procedure: PTCA with drug-eluting stent placement in LAD. "
    "Diagnosis: STEMI anterior wall, coronary artery disease.",
    "Patient presents with right hip pain after fall. X-ray shows intertrochanteric fracture. "
    "Comorbidities: type 2 diabetes, hypertension. "
    "Procedure: open reduction internal fixation right hip.",
    "Cerebral infarction with left hemiparesis. MRI brain shows right MCA territory infarct. "
    "Diagnosis: acute ischemic stroke. tPA administered within 3-hour window. "
    "Comorbidities: atrial fibrillation, hyperlipidemia.",
]


async def run_single_pipeline(encounter_text: str, index: int, token: str) -> dict:
    """Run one pipeline and return timing/stats."""
    import httpx
    start = time.time()
    result = {
        "index": index,
        "success": False,
        "completed": False,
        "clinical_success": False,
        "safe_failure": False,
        "time_s": 0,
        "error": None,
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            headers = {"Authorization": f"Bearer {token}"}
            # Run the current unified Agent API.  The legacy /api/reviews
            # endpoint was removed; keeping it here made every task look like
            # a concurrency failure when it was actually an HTTP 404.
            r = await client.post(
                "http://localhost:8000/api/v1/agents/medical-coding-agent/run",
                json={
                    "input": {
                        "text": encounter_text,
                        "extra": {
                            "region": "中国",
                            "code_system": "ICD-10-CN/ICD-9-CM-3",
                        },
                    },
                    "include_trace": True,
                },
                headers=headers,
            )
            review = r.json()
            result["http_status"] = r.status_code
            result["completed"] = (
                r.status_code == 200
                and bool(review.get("run_id"))
            )
            result["clinical_success"] = (
                result["completed"] and review.get("error") is False
            )
            error_reason = str(review.get("error_reason") or "")
            safe_reasons = {
                "llm_degraded",
                "mock_provider",
                "degraded:mock_provider",
                "no_api_key",
            }
            result["safe_failure"] = (
                result["completed"]
                and review.get("error") is True
                and error_reason in safe_reasons
            )
            # ``success`` means the concurrency contract completed safely.  A
            # mock/no-key server must fail closed and is not a clinical success.
            result["success"] = result["clinical_success"] or result["safe_failure"]
            result["time_s"] = round(time.time() - start, 2)
            payload = review.get("result") or {}
            result["health"] = (
                "clinical_success"
                if result["clinical_success"]
                else f"safe_failure:{error_reason}"
                if result["safe_failure"]
                else payload.get("finish_state", "unknown")
            )
            candidates = payload.get("candidates") or payload.get("codes") or []
            result["candidates"] = len(candidates) if isinstance(candidates, list) else 0
            if not result["success"]:
                result["error"] = (
                    review.get("error_reason")
                    or review.get("detail")
                    or f"HTTP {r.status_code}: {r.text[:160]}"
                )
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"[:160]
        result["time_s"] = round(time.time() - start, 2)

    return result


async def test_concurrent_pipelines():
    """Run pipelines concurrently and verify all complete successfully."""
    concurrency = min(5, len(CLINICAL_TEXTS))
    texts = CLINICAL_TEXTS[:concurrency]

    print(f"\n{'='*60}")
    print(f"Concurrency Test: {concurrency} simultaneous pipelines")
    print(f"{'='*60}\n")

    import httpx
    # Authenticate once.  Five simultaneous logins exercise the auth rate
    # limiter instead of pipeline concurrency and can lock the test account.
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
        login = await client.post(
            "http://localhost:8000/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        login.raise_for_status()
        token = login.json()["access_token"]

    t0 = time.time()
    tasks = [run_single_pipeline(text, i, token) for i, text in enumerate(texts)]
    results = await asyncio.gather(*tasks)
    total_time = round(time.time() - t0, 1)

    # Report
    print(f"{'#':<4} {'Success':<8} {'Time(s)':<10} {'Health':<12} {'Candidates':<12}")
    print("-" * 50)
    for r in results:
        status = "OK" if r["success"] else "FAIL"
        print(f"{r['index']:<4} {status:<8} {r['time_s']:<10} {r.get('health','?'):<12} {r.get('candidates','?'):<12}")
        if r["error"]:
            print(f"     Error: {r['error']}")

    success_count = sum(1 for r in results if r["success"])
    fail_count = len(results) - success_count
    clinical_success_count = sum(1 for r in results if r["clinical_success"])
    safe_failure_count = sum(1 for r in results if r["safe_failure"])
    avg_time = sum(r["time_s"] for r in results) / len(results)

    print(f"\n--- Summary ---")
    print(f"Total wall time: {total_time}s")
    print(f"Avg pipeline time: {avg_time:.1f}s")
    print(f"Successful: {success_count}/{len(results)}")
    print(f"Clinical successes: {clinical_success_count}/{len(results)}")
    print(f"Safe fail-closed completions: {safe_failure_count}/{len(results)}")
    print(f"Failed: {fail_count}/{len(results)}")

    # Assertions
    assert fail_count == 0, f"{fail_count} pipeline(s) failed under concurrency"
    assert total_time < 300, f"Concurrency test took {total_time}s, expected <300s"

    print(f"\nPASS: All {success_count} concurrent pipelines completed successfully.\n")


if __name__ == "__main__":
    asyncio.run(test_concurrent_pipelines())
