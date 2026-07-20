"""Build Gate 4R node-ID transition ledger from two JUnit XML files.

Reads two JUnit XMLs (baseline + gate4) and produces:
  * gate4r_diff/transition_ledger.json   — full per-node record
  * gate4r_diff/pass_to_fail.txt         — load-bearing regressions
  * gate4r_diff/fail_to_pass.txt         — concurrent heals
  * gate4r_diff/fail_to_fail.txt         — baseline FAIL that stayed FAIL
  * gate4r_diff/pass_to_pass.txt         — count only (no full dump)
  * gate4r_diff/error_to_error.txt       — baseline ERROR that stayed ERROR
  * gate4r_diff/transition_summary.json  — aggregate counts

Every transition is keyed by the canonical pytest node ID
(`path::ClassName::method` or `path::function`). Node IDs are taken
verbatim from the JUnit classname+name fields, normalized to the
pytest form via a simple path-agnostic match against the filter
files written by the gate4r diff step.

This script is hermetic: it reads two XML files and writes JSON/TXT
files. No network, no env mutation.
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from typing import Dict, Set, Tuple


def _normalize(classname: str, name: str) -> str:
    """Reconstruct the pytest node ID from JUnit classname + name.

    pytest emits classname as 'tests.unit.app.api.test_tickets_api' or
    'tests.unit.app.api.test_tickets_api.TestDeleteTicket'. We convert
    dots to slashes in the path portion and rejoin as path::Class::method.
    """
    parts = classname.split(".")
    # The first segment is the top-level test root (e.g. 'tests'); the
    # last segment is the test module (e.g. 'test_tickets_api'). Convert
    # these into a path: tests/unit/app/api/test_tickets_api.py
    # Then append any in-between class-ish segments after the module.
    if len(parts) < 2:
        return f"{classname}::{name}"
    # Find the last segment that starts with 'test_' — treat that as module
    module_idx = max(i for i, p in enumerate(parts) if p.startswith("test_"))
    path_segments = parts[: module_idx + 1]
    class_segments = parts[module_idx + 1 :]
    path = "/".join(path_segments) + ".py"
    if class_segments:
        return f"{path}::{'::'.join(class_segments)}::{name}"
    return f"{path}::{name}"


def _status_of(tc) -> str:
    if tc.find("failure") is not None:
        return "failed"
    if tc.find("error") is not None:
        return "error"
    if tc.find("skipped") is not None:
        return "skipped"
    return "passed"


def _parse(xml_path: str) -> Dict[str, str]:
    """Return {normalized_nodeid: status}."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    out: Dict[str, str] = {}
    for tc in root.findall(".//testcase"):
        cls = tc.get("classname", "")
        nm = tc.get("name", "")
        nodeid = _normalize(cls, nm)
        out[nodeid] = _status_of(tc)
    return out


def main(baseline_xml: str, gate4_xml: str, out_dir: str) -> int:
    baseline = _parse(baseline_xml)
    gate4 = _parse(gate4_xml)

    os.makedirs(out_dir, exist_ok=True)

    common = set(baseline) & set(gate4)
    baseline_only = set(baseline) - set(gate4)
    gate4_only = set(gate4) - set(baseline)

    transitions: Dict[str, Dict[str, str]] = {}
    buckets: Dict[Tuple[str, str], list] = {}

    for nodeid in sorted(common):
        b = baseline[nodeid]
        g = gate4[nodeid]
        transitions[nodeid] = {"baseline": b, "gate4": g}
        buckets.setdefault((b, g), []).append(nodeid)

    summary = {
        "baseline_total": len(baseline),
        "gate4_total": len(gate4),
        "common": len(common),
        "baseline_only": len(baseline_only),
        "gate4_only": len(gate4_only),
        "transition_counts": {
            f"{b}->{g}": len(nodes) for (b, g), nodes in sorted(buckets.items())
        },
    }

    # Per-bucket dumps (only for non-PASS->PASS — that one is too big)
    bucket_files = {
        "passed->failed": "pass_to_fail.txt",
        "failed->passed": "fail_to_pass.txt",
        "failed->failed": "fail_to_fail.txt",
        "error->error": "error_to_error.txt",
        "passed->error": "pass_to_error.txt",
        "error->failed": "error_to_fail.txt",
        "failed->error": "fail_to_error.txt",
        "error->passed": "error_to_pass.txt",
        "passed->passed": "pass_to_pass.count.txt",
        "passed->skipped": "pass_to_skipped.txt",
        "skipped->skipped": "skipped_to_skipped.count.txt",
    }
    for (b, g), nodes in sorted(buckets.items()):
        key = f"{b}->{g}"
        fname = bucket_files.get(key)
        if fname is None:
            continue
        path = os.path.join(out_dir, fname)
        if fname.endswith(".count.txt"):
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"{len(nodes)}\n")
        else:
            with open(path, "w", encoding="utf-8") as f:
                for n in sorted(nodes):
                    f.write(n + "\n")

    with open(os.path.join(out_dir, "transition_ledger.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "summary": summary,
                "baseline_only": sorted(baseline_only),
                "gate4_only": sorted(gate4_only),
                "transitions": transitions,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    with open(os.path.join(out_dir, "transition_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary["transition_counts"], indent=2))
    print(f"baseline_only = {len(baseline_only)}")
    print(f"gate4_only = {len(gate4_only)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: gate4r_build_transition_ledger.py <baseline.xml> <gate4.xml> <out_dir>")
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
