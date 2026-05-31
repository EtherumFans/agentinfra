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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("concurrency_test")


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


async def run_single_pipeline(encounter_text: str, index: int) -> dict:
    """Run one pipeline and return timing/stats."""
    import httpx
    start = time.time()
    result = {"index": index, "success": False, "time_s": 0, "error": None}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            # Login
            r = await client.post(
                "http://localhost:8000/api/auth/login",
                json={"username": "admin", "password": "admin123"},
            )
            token = r.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Create encounter
            r = await client.post(
                "http://localhost:8000/api/encounters/text",
                json={"raw_text": encounter_text, "department": "test"},
                headers=headers,
            )
            enc_id = r.json()["id"]

            # Run pipeline
            r = await client.post(
                "http://localhost:8000/api/reviews",
                json={"encounter_id": enc_id},
                headers=headers,
            )
            review = r.json()
            result["success"] = bool(review.get("review_id"))
            result["time_s"] = round(time.time() - start, 2)
            result["health"] = review.get("pipeline_health", "unknown")
            result["candidates"] = len(review.get("candidates", []))
            result["errors"] = len(review.get("error_message", "") or [])
    except Exception as e:
        result["error"] = str(e)[:100]
        result["time_s"] = round(time.time() - start, 2)

    return result


async def test_concurrent_pipelines():
    """Run pipelines concurrently and verify all complete successfully."""
    concurrency = min(5, len(CLINICAL_TEXTS))
    texts = CLINICAL_TEXTS[:concurrency]

    print(f"\n{'='*60}")
    print(f"Concurrency Test: {concurrency} simultaneous pipelines")
    print(f"{'='*60}\n")

    t0 = time.time()
    tasks = [run_single_pipeline(text, i) for i, text in enumerate(texts)]
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
    avg_time = sum(r["time_s"] for r in results) / len(results)

    print(f"\n--- Summary ---")
    print(f"Total wall time: {total_time}s")
    print(f"Avg pipeline time: {avg_time:.1f}s")
    print(f"Successful: {success_count}/{len(results)}")
    print(f"Failed: {fail_count}/{len(results)}")

    # Assertions
    assert fail_count == 0, f"{fail_count} pipeline(s) failed under concurrency"
    assert total_time < 300, f"Concurrency test took {total_time}s, expected <300s"

    print(f"\nPASS: All {success_count} concurrent pipelines completed successfully.\n")


if __name__ == "__main__":
    asyncio.run(test_concurrent_pipelines())
