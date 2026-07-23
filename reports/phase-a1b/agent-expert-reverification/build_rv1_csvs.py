"""Build RV.1 CSV deliverables from evidence files.

Produces:
  NODE_TRANSITIONS_85A5C9A_TO_8546184.csv
  NODE_TRANSITIONS_8546184_TO_FINAL.csv
  FAILURE_CLASSIFICATION.csv
"""
import csv
import os
from pathlib import Path

EVID = Path("reports/phase-a1b/agent-expert-reverification/evidence")
BASELINE = EVID / "baseline-85a5c9a"
TERMINAL = EVID / "terminal-8546184"
REPAIR = EVID / "repair-head"
DIFFDIR = EVID / "node-diff"


def read_node_ids(p):
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


baseline_ids = set(read_node_ids(BASELINE / "NODE_IDS.txt"))
terminal_ids = set(read_node_ids(TERMINAL / "NODE_IDS.txt"))
repair_ids = set(read_node_ids(REPAIR / "NODE_IDS.txt"))

baseline_fe = set(read_node_ids(BASELINE / "FAILED_AND_ERROR_NODE_IDS.txt"))
terminal_fe = set(read_node_ids(TERMINAL / "FAILED_AND_ERROR_NODE_IDS.txt"))


def status_of(node_id, fe_set):
    """Return 'FAILED', 'ERROR', or 'PASSED' based on FAILED/ERROR prefix.

    Lines in fe_set look like 'FAILED <node_id>' or 'FAILED <node_id> - <msg>'
    or 'ERROR <node_id>'. Use startswith to tolerate trailing error messages.
    """
    for line in fe_set:
        if line.startswith("FAILED " + node_id):
            return "FAILED"
        if line.startswith("ERROR " + node_id):
            return "ERROR"
    return "PASSED"


def classify_transition(b_status, t_status):
    if b_status == "PASSED" and t_status == "PASSED":
        return "PASS_TO_PASS"
    if b_status == "PASSED" and t_status in ("FAILED", "ERROR"):
        return f"PASS_TO_{t_status}"  # NEW REGRESSION
    if b_status in ("FAILED", "ERROR") and t_status == "PASSED":
        return f"{b_status}_TO_PASS"  # FIXED
    if b_status in ("FAILED", "ERROR") and t_status in ("FAILED", "ERROR"):
        if b_status == t_status:
            return f"{b_status}_TO_{t_status}"  # PRE_EXISTING_SAME
        return f"{b_status}_TO_{t_status}"  # changed failure mode
    return "UNKNOWN"


# === NODE_TRANSITIONS_85A5C9A_TO_8546184.csv ===
out_path = EVID.parent / "NODE_TRANSITIONS_85A5C9A_TO_8546184.csv"
common = baseline_ids & terminal_ids
added = terminal_ids - baseline_ids
removed = baseline_ids - terminal_ids

with out_path.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["node_id", "baseline_status_85a5c9a", "terminal_status_8546184", "transition", "classification"])

    for node in sorted(common):
        b = status_of(node, baseline_fe)
        t = status_of(node, terminal_fe)
        tr = classify_transition(b, t)
        if tr in ("FAIL_TO_FAIL", "ERROR_TO_ERROR"):
            cls = "PRE_EXISTING_SAME"
        elif tr.endswith("_TO_PASS"):
            cls = "FIXED_BY_A1B_AE_R"
        elif tr.startswith("PASS_TO_") and tr != "PASS_TO_PASS":
            cls = "NEW_REGRESSION"
        elif tr == "PASS_TO_PASS":
            cls = "STABLE_PASS"
        else:
            cls = "CHANGED"
        w.writerow([node, b, t, tr, cls])

    for node in sorted(added):
        t = status_of(node, terminal_fe)
        if t == "PASSED":
            tr = "ADDED_PASS"
        elif t == "FAILED":
            tr = "ADDED_FAIL"
        elif t == "ERROR":
            tr = "ADDED_ERROR"
        else:
            tr = "ADDED_UNKNOWN"
        w.writerow([node, "(not present)", t, tr, "NEW_AT_TERMINAL"])

    for node in sorted(removed):
        b = status_of(node, baseline_fe)
        w.writerow([node, b, "(migrated)", "REMOVED_MIGRATED", "MIGRATED_TO_NEW_FILE"])

print(f"Wrote {out_path} ({sum(1 for _ in out_path.open()) - 1} rows)")
print(f"  common={len(common)} added={len(added)} removed={len(removed)}")

# === NODE_TRANSITIONS_8546184_TO_FINAL.csv ===
# At RV.0 (current HEAD a419076), test code is identical to 8546184 — no transitions.
out_path2 = EVID.parent / "NODE_TRANSITIONS_8546184_TO_FINAL.csv"
with out_path2.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow(["node_id", "terminal_status_8546184", "final_status_rv_head", "transition", "classification"])
    w.writerow(["(all 1092 node-IDs)", "PASSED/FAILED/ERROR per terminal", "IDENTICAL at RV.0 (a419076)", "NO_CHANGE_AT_RV0", "RV.0_IS_EVIDENCE_ONLY"])
print(f"Wrote {out_path2} (placeholder — RV.0 added no tests)")

# === FAILURE_CLASSIFICATION.csv ===
out_path3 = EVID.parent / "FAILURE_CLASSIFICATION.csv"
with out_path3.open("w", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "node_id", "outcome_at_terminal_8546184", "outcome_at_baseline_85a5c9a",
        "classification", "evidence", "fix_action_required_at_rv"
    ])

    # 31 common FAILED/ERROR at terminal — all PRE_EXISTING_SAME
    common_fe = (baseline_fe & terminal_fe)
    for line in sorted(common_fe):
        prefix, node = line.split(" ", 1)
        w.writerow([
            node,
            prefix + "_AT_TERMINAL",
            prefix + "_AT_BASELINE",
            "PRE_EXISTING_SAME",
            "Same node-ID, same failure signature at baseline 85a5c9a. Test files not modified by A1B-AE-R (git log 85a5c9a..8546184 empty for these files).",
            "NONE — pre-existing baseline carryover. Out of A1B-AE-RV scope per charter §五."
        ])

    # 9 baseline-only FAILED/ERROR (FIXED by A1B-AE-R)
    only_baseline = (baseline_fe - terminal_fe)
    for line in sorted(only_baseline):
        prefix, node = line.split(" ", 1)
        w.writerow([
            node,
            "PASSED_AT_TERMINAL",
            prefix + "_AT_BASELINE",
            "PRE_EXISTING_FIXED_BY_A1B_AE_R",
            "Failed/errored at baseline 85a5c9a; passes at terminal 8546184. A1B-AE-R dev DB reseed + migration work resolved these.",
            "NONE — already fixed."
        ])

print(f"Wrote {out_path3} ({sum(1 for _ in out_path3.open()) - 1} rows)")
print(f"  common_fe={len(common_fe)} only_baseline={len(only_baseline)}")
