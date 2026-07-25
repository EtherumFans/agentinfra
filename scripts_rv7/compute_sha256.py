"""Compute SHA256 sums for all RV evidence files."""
import hashlib
from pathlib import Path

ROOT = Path("E:/Corti4C-agent-expert-reverification")
REPORTS = ROOT / "reports/phase-a1b/agent-expert-reverification"

files = []
for pattern in ("*.json", "*.md", "*.txt", "*.csv", "*.xml"):
    files.extend(REPORTS.rglob(pattern))

results = []
seen = set()
for p in files:
    if not p.is_file():
        continue
    if p in seen:
        continue
    seen.add(p)
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    rel = p.relative_to(ROOT).as_posix()
    results.append((h, rel))

results.sort(key=lambda x: x[1])

out_path = REPORTS / "EVIDENCE_SHA256SUMS.txt"
with out_path.open("w", encoding="utf-8", newline="\n") as out:
    for h, p in results:
        out.write(f"{h}  {p}\n")

print(f"wrote {len(results)} sha256 entries to {out_path}")
