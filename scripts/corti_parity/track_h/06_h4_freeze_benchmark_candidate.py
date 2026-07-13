"""Track H4.2 — Freeze formal benchmark candidate (icoder-cdi-agent-v1.0.0-rc3).

Snapshots the iter 5 baseline into a single reproducible artifact directory:

    reports/track_h/h4_benchmark_candidate_rc3/
        MANIFEST.json
        gate8_icoder_40case_results.json          (copy)
        gate8_icoder_per_case/                    (40 copies)
        h34_normalizer_40case.json                (copy)
        h41_quality_safety_expert_40case.json     (copy)
        corti_40_summary.json                     (copy, Corti baseline reference)
        H4_BENCHMARK_CANDIDATE_README.md          (generated)

MANIFEST.json contains sha256 checksums, version label, commit SHA, timestamp,
and the H4.1 verdict summary so the snapshot is self-describing.

No LLM, no network. Pure file copy + hashing.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DST = REPO_ROOT / "reports" / "track_h" / "h4_benchmark_candidate_rc4"

CANDIDATE_VERSION = "icoder-cdi-agent-v1.0.0-rc4"
ITER = 6
TIER_LABEL = "PASS_CALIBRATION_TUNING_ITERATION_6"

SOURCES = {
    "gate8_icoder_40case_results.json":
        REPO_ROOT / "backend" / "reports" / "phase5_d_p05" / "gate8_icoder_40case_results.json",
    "h34_normalizer_40case.json":
        REPO_ROOT / "reports" / "track_h" / "h34_normalizer_40case.json",
    "h41_quality_safety_expert_40case.json":
        REPO_ROOT / "reports" / "track_h" / "h41_quality_safety_expert_40case.json",
    "corti_40_summary.json":
        REPO_ROOT / "reports" / "track_h" / "corti_40_summary.json",
}
PER_CASE_SRC = REPO_ROOT / "backend" / "reports" / "phase5_d_p05" / "gate8_icoder_per_case"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def main() -> int:
    if DST.exists():
        shutil.rmtree(DST)
    DST.mkdir(parents=True, exist_ok=True)
    (DST / "per_case").mkdir(exist_ok=True)

    manifest_files = []
    for rel, src in SOURCES.items():
        if not src.exists():
            print(f"WARN: source missing, skipping: {src}", file=sys.stderr)
            continue
        dst = DST / rel
        shutil.copy2(src, dst)
        manifest_files.append({
            "path": rel,
            "source": str(src.relative_to(REPO_ROOT)),
            "sha256": _sha256(dst),
            "size_bytes": dst.stat().st_size,
        })

    per_case_files = []
    for src in sorted(PER_CASE_SRC.glob("*.json")):
        dst = DST / "per_case" / src.name
        shutil.copy2(src, dst)
        per_case_files.append({
            "path": f"per_case/{src.name}",
            "sha256": _sha256(dst),
            "size_bytes": dst.stat().st_size,
        })

    # Load H4.1 summary for self-describing manifest
    h41_summary = {}
    h41_path = DST / "h41_quality_safety_expert_40case.json"
    if h41_path.exists():
        h41_data = json.loads(h41_path.read_text(encoding="utf-8"))
        h41_summary = h41_data.get("summary", {})

    # Load normalizer for §9.9 + §9.10 snapshot
    normalizer_summary = {}
    norm_path = DST / "h34_normalizer_40case.json"
    if norm_path.exists():
        norm_data = json.loads(norm_path.read_text(encoding="utf-8"))
        normalizer_summary = {
            "section_9_9_cross_platform": {
                "avg_abs_query_count_delta":
                    norm_data.get("section_9_9_cross_platform", {}).get("avg_abs_query_count_delta"),
                "agreement_rate_delta_le_1":
                    norm_data.get("section_9_9_cross_platform", {}).get("agreement_rate_delta_le_1"),
                "icoder_range_conformance":
                    norm_data.get("section_9_9_cross_platform", {}).get("icoder_range_conformance"),
                "corti_range_conformance":
                    norm_data.get("section_9_9_cross_platform", {}).get("corti_range_conformance"),
            },
            "section_9_10_icoder_safety": norm_data.get("section_9_10_icoder_safety"),
        }

    manifest = {
        "candidate_version": CANDIDATE_VERSION,
        "frozen_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": _git_sha(),
        "iter": ITER,
        "tier": TIER_LABEL,
        "case_count": len(per_case_files),
        "description": (
            "Frozen iter 6 baseline of iCoDer CDI Agent on the 40-case Corti/iCoDer "
            "cross-platform calibration fixture. iter 6 = H3.16 lab-positive-"
            "uncertain safety net (3 deterministic fixes) + H3.18 response_options "
            "padding. Closes 4 of 5 iter 5 stuck points (lab_uncertain emit, "
            "clear_gap under-query, response_options_4plus, doc_conflict emit "
            "fully closed at 1.0). Snapshot is the reference for H1.2-H1.4 Corti "
            "controlled probes (Tier 2)."
        ),
        "headline_metrics": {
            "iter_6_avg_queries_per_case": 0.925,
            "iter_6_icoder_range_conformance": "34/40 (85%)",
            "iter_6_agreement_rate_vs_corti": 0.70,
            "iter_6_avg_abs_query_count_delta": 0.97,
            "iter_6_multi_dim_leaked_total": 0,
            "iter_6_complete_chart_over_query": "0/10",
            "iter_6_clear_gap_under_query": "1/10",
            "iter_6_evidence_quote_verbatim": 0.973,
            "iter_6_unsupported_query_rate": 0.027,
            "iter_6_document_conflict_emit_rate": 1.000,
            "iter_6_contradiction_risk_flag_cases": 6,
            "iter_6_response_options_4plus": 1.000,
            "iter_6_non_leading_query_rate": 1.000,
        },
        "h4_1_quality_summary": h41_summary.get("quality", {}),
        "h4_1_safety_summary": h41_summary.get("safety", {}),
        "h4_1_expert_summary": h41_summary.get("expert", {}),
        "cross_platform_normalizer": normalizer_summary,
        "caveats": [
            "document_conflict emit_rate fully closed (0.60 → 1.000, target ≥0.80) — iter 6 WIN, H3.16 CEA-004 'chart' doc_id fix unblocked all conflict queries",
            "response_options_4plus closed (0.900 → 1.000, target ≥0.95) — iter 6 WIN, H3.18 deterministic padding",
            "non_leading_query_rate closed (0.968 → 1.000) — iter 6 WIN",
            "lab_positive_uncertain emit lifted (0/5 → 2/5 emit, 4/5 in_range) — iter 6 WIN, H3.16 three deterministic safety nets",
            "clear_gap under-query big lift (4/10 → 1/10) — iter 6 WIN",
            "Avg |Δq| improved (1.30 → 0.97) — iter 6 WIN",
            "Agreement rate improved (0.57 → 0.70) — iter 6 WIN",
            "iCoDer range conformance improved (78% → 85%) — iter 6 WIN",
            "insufficient_evidence agreement big lift (0.40 → 1.00) — iter 6 WIN",
            "complete_chart over-query maintained at 0/10 (5 iters) — structural",
            "contradiction_risk_flag maintained at 6/40 — iter 4 WIN preserved",
            "multi_dim_leaked = 0 maintained (structural, deterministic gate)",
            "evidence_quote_verbatim slight drift (1.000 → 0.973) — 1 query LLM drift, within tolerance",
            "unsupported_query_rate slight drift (0.000 → 0.027) — 1 query LLM drift",
            "clear_gap over-query 1/10 (GAP-010) — LLM drift; defer prompt tuning to iter 7",
            "expert_rejection behavior not exercised (EXP-005) — H1.3 carry-forward",
        ],
        "files": manifest_files,
        "per_case_files": per_case_files,
        "file_count_total": len(manifest_files) + len(per_case_files),
    }

    (DST / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # Self-describing README
    readme = f"""# H4.2 Benchmark Candidate — `{CANDIDATE_VERSION}`

**Frozen at (UTC)**: {manifest['frozen_at_utc']}
**Git commit**: `{manifest['git_commit']}`
**Iter**: {ITER}
**Tier**: `{TIER_LABEL}`
**Case count**: {len(per_case_files)}

## What this is

A reproducible snapshot of the iCoDer CDI Agent's iter 6 calibration baseline
on the 40-case Corti × iCoDer cross-platform fixture. iter 6 = H3.16 lab-positive-
uncertain safety net (3 deterministic fixes in extract_claims + CEA-004 + gap
prompt) + H3.18 response_options padding. Closes 4 of 5 iter 5 stuck points.
Tier 2 work (H1.2/H1.3/H1.4 Corti controlled probes) will measure deltas against
this artifact.

## Files

| Path | Purpose |
|---|---|
| `MANIFEST.json` | Self-describing manifest with sha256 + headlines |
| `gate8_icoder_40case_results.json` | iter 6 iCoDer 40-case aggregate results |
| `per_case/*.json` | 40 per-case trace files (stage_traces, gaps, queries, experts) |
| `h34_normalizer_40case.json` | §9.9 cross-platform + §9.10 safety metrics |
| `h41_quality_safety_expert_40case.json` | H4.1 quality + safety + expert scoring |
| `corti_40_summary.json` | Corti baseline reference (for delta comparison) |

## Headline metrics

| Metric | Value | Target | Status |
|---|---|---|---|
| avg queries/case | 0.925 | n/a | informational |
| iCoDer range conformance | 34/40 (85%) | ≥ 60% | ✅ PASS |
| agreement rate vs Corti (\\|Δ\\|≤1) | 0.70 | ≥ 0.80 | ⚠ partial |
| avg \\|Δ query count\\| | 0.97 | ≤ 0.50 | ⚠ partial |
| multi_dim_leaked_total | 0 | 0 | ✅ PASS (structural) |
| complete_chart over-query | 0/10 | 0 | ✅ PASS (6 iters) |
| clear_gap under-query | 1/10 | 0 | ⚠ partial (iter 6 BIG WIN: 4→1) |
| evidence_quote_verbatim | 0.973 | ≥ 0.95 | ✅ PASS (1 query drift) |
| document_conflict emit rate | 1.000 | ≥ 0.80 | ✅ PASS (iter 6 fully closed) |
| unsupported_query_rate | 0.027 | = 0 | ⚠ 1 query drift |
| response_options_4plus | 1.000 | ≥ 0.95 | ✅ PASS (iter 6 closed) |
| non_leading_query_rate | 1.000 | ≥ 0.95 | ✅ PASS (iter 6 closed) |
| contradiction_risk_flag cases | 6/40 | n/a | ✅ iter 4 hold |

## Iter 6 wins (vs iter 5)

1. **document_conflict emit_rate 0.60 → 1.000** — H3.16 CEA-004 'chart' doc_id
   acceptance unblocked every LLM-extracted alignment (was failing because
   'chart' ∉ {'DOC-001'}).
2. **response_options_4plus 0.900 → 1.000** — H3.18 deterministic padding.
3. **non_leading_query_rate 0.968 → 1.000** — LLM drift resolved.
4. **lab_positive_uncertain emit 0/5 → 2/5** — H3.16 three safety nets
   (critical+empty quote demote, critical+fuzzy mismatch demote, CEA-004
   'chart' accept, gap_identification lab-positive prompt rule).
5. **clear_gap under-query 4/10 → 1/10** — same H3.16 fixes.
6. **Avg |Δq| 1.30 → 0.97** — closer to Corti baseline.
7. **Agreement rate 0.57 → 0.70** — insufficient_evidence 0.40 → 1.00.
8. **iCoDer range conformance 78% → 85%** (34/40).

## Carry-forward (does not block freeze)

1. **H3.19** — negation_history agreement 0.60 (was 0.80 iter 4). ~2h.
2. **H1.2/H1.3/H1.4** — Corti controlled probes for the 3 UNKNOWN capabilities
   + EXP-005 rejection behavior (~3-4h). Requires Corti JWT.
3. **clear_gap over-query 1/10 (GAP-010)** — LLM emits 3 gaps for a max=2
   case. Defer prompt tuning to iter 7.
4. **evidence_quote_verbatim 1.000 → 0.973** — 1 query LLM drift.
5. **unsupported_query_rate 0.000 → 0.027** — 1 query LLM drift.
6. **multi_dim "6 iters at 0" framing** — structural (deterministic gate),
   not a tuned achievement.

## How to regenerate

```bash
# Restore the snapshot from any commit:
python scripts/corti_parity/track_h/06_h4_freeze_benchmark_candidate.py

# Re-run H4.1 scoring on the snapshot:
python scripts/corti_parity/track_h/05_h4_quality_safety_expert_scoring.py

# Re-run normalizer on the snapshot:
python scripts/corti_parity/track_h/04_normalize_and_compare.py
```

To unfreeze / delete:
```bash
rm -rf reports/track_h/h4_benchmark_candidate_rc4/
```
"""
    (DST / "H4_BENCHMARK_CANDIDATE_README.md").write_text(readme, encoding="utf-8")

    # stdout
    print(f"H4.2 benchmark candidate frozen: {CANDIDATE_VERSION}")
    print(f"  dst: {DST.relative_to(REPO_ROOT)}")
    print(f"  files: {manifest['file_count_total']} ({len(manifest_files)} aggregate + {len(per_case_files)} per-case)")
    print(f"  git: {manifest['git_commit']}")
    print(f"  frozen_at_utc: {manifest['frozen_at_utc']}")
    print()
    print("Headline metrics:")
    for k, v in manifest["headline_metrics"].items():
        print(f"  {k}: {v}")
    print()
    print(f"Manifest: {DST.relative_to(REPO_ROOT) / 'MANIFEST.json'}")
    print(f"README:   {DST.relative_to(REPO_ROOT) / 'H4_BENCHMARK_CANDIDATE_README.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
