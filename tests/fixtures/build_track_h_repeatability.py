"""Build repeatability fixture: 5 cases × 3 runs = 15 cases with _R1/R2/R3 suffix."""
import json
from pathlib import Path

src = json.loads(Path("tests/fixtures/track_h_mechanism_probes.json").read_text(encoding="utf-8"))
subset = [s["case_id"] for s in src["_meta"]["repeatability_subset"]]
cases_by_id = {c["case_id"]: c for c in src["cases"]}

new_cases = []
for cid in subset:
    base = cases_by_id[cid]
    for r in (1, 2, 3):
        nc = dict(base)
        nc["case_id"] = f"{cid}_R{r}"
        nc["base_case_id"] = cid
        nc["run_idx"] = r
        new_cases.append(nc)

out = {
    "_meta": {
        "source": "Track H1.4 — repeatability probes (3× each on 5 base cases)",
        "base_case_ids": subset,
        "runs_per_case": 3,
        "case_count": len(new_cases),
    },
    "cases": new_cases,
}
Path("tests/fixtures/track_h_repeatability.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"Wrote repeatability fixture: {len(new_cases)} cases ({len(subset)} base × 3)")
