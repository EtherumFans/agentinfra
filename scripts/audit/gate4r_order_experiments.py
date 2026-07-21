"""Gate 4R Order Pollution Experiments A/B/C/D.

Hypothesis: the +43 net FAIL delta at 880f49c is partly or wholly an
artifact of test-order-dependent state leakage, NOT a true regression
introduced by Gate 4 code changes.

We test this hypothesis by running the common-node suite (3591 nodes
that exist at both b737eab and 880f49c) under four order regimes:

  A — default (pytest's natural collection order)
  B -p no:randomly (explicitly disable any random-order plugin)
  C --forked (subprocess per test; isolates all in-process state)
  D -p randomly with seed=4294674 (different order; if results differ
      from A, order-pollution is proven)

Experiments A and B establish the baseline. If C dramatically changes
the failure count, single-test isolation heals the pollution, which
proves the in-process state leak. If D produces a different set of
failing nodes from A, order is load-bearing for the failure surface.

Output:
  gate4r_diff/order_experiment_A.{xml,log}
  gate4r_diff/order_experiment_B.{xml,log}
  gate4r_diff/order_experiment_C.{xml,log}
  gate4r_diff/order_experiment_D.{xml,log}
  gate4r_diff/order_experiment_summary.json

This is a driver script — it shells out to pytest via subprocess.
The actual pytest invocations are written to be hermetic per run:
each uses GATE4R_NODE_FILTER_FILE to restrict to common nodes only.

Usage:
    python scripts/audit/gate4r_order_experiments.py \\
        --workdir E:/Corti4C-audit-gate4 \\
        --common gate4r_diff/common_nodeids.txt \\
        --outdir gate4r_diff

Run this AFTER the gate4 full JUnit XML has been captured.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Dict, List


FOUR_EXPERIMENTS: List[Dict[str, List[str]]] = [
    {
        "name": "A_default",
        "pytest_args": ["-q", "--no-header", "--tb=line"],
    },
    {
        "name": "B_no_randomly",
        "pytest_args": ["-q", "--no-header", "--tb=line", "-p", "no:randomly"],
    },
    {
        "name": "C_forked",
        "pytest_args": ["-q", "--no-header", "--tb=line", "--forked"],
    },
    {
        "name": "D_random_seed_4294674",
        "pytest_args": [
            "-q",
            "--no-header",
            "--tb=line",
            "-p",
            "randomly",
            "--randomly-seed=4294674",
        ],
    },
]


def run_one(name: str, pytest_args: List[str], workdir: str, common: str, outdir: str) -> Dict:
    env = os.environ.copy()
    env["GATE4R_NODE_FILTER_FILE"] = os.path.abspath(common)
    env["PYTEST_ADDOPTS"] = "-p scripts.audit.gate4r_node_filter"
    xml_out = os.path.join(outdir, f"order_experiment_{name}.xml")
    log_out = os.path.join(outdir, f"order_experiment_{name}.log")
    cmd = ["python", "-m", "pytest", "backend/tests", f"--junit-xml={xml_out}"] + pytest_args
    t0 = time.time()
    with open(log_out, "w", encoding="utf-8") as logf:
        proc = subprocess.run(
            cmd,
            cwd=workdir,
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
    elapsed = time.time() - t0
    return {
        "name": name,
        "exit_code": proc.returncode,
        "elapsed_seconds": round(elapsed, 1),
        "xml": xml_out,
        "log": log_out,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workdir", required=True, help="pytest workdir (gate4 worktree)")
    p.add_argument("--common", required=True, help="common_nodeids.txt path")
    p.add_argument("--outdir", required=True, help="output directory")
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    results = []
    for exp in FOUR_EXPERIMENTS:
        print(f"--- running experiment {exp['name']} ---", flush=True)
        r = run_one(exp["name"], exp["pytest_args"], args.workdir, args.common, args.outdir)
        results.append(r)
        print(f"--- {exp['name']}: exit={r['exit_code']} elapsed={r['elapsed_seconds']}s")

    with open(os.path.join(args.outdir, "order_experiment_summary.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
