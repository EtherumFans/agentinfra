"""Run only the 2 failed probe cases (H-SUS-B-004, H-CMP-A-005)."""
import json, sys
from pathlib import Path

src = json.loads(Path("tests/fixtures/track_h_mechanism_probes.json").read_text(encoding="utf-8"))
keep = {"H-SUS-B-004", "H-CMP-A-005"}
src["cases"] = [c for c in src["cases"] if c["case_id"] in keep]
src["_meta"]["case_count"] = len(src["cases"])
Path("tests/fixtures/track_h_mechanism_probes_retry.json").write_text(
    json.dumps(src, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"Wrote retry fixture with {len(src['cases'])} cases")
