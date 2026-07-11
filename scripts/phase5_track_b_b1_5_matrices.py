"""Phase 5 Track B B-1.5 — build 3 matrices per PDF §8/§9/§10.

Outputs (under outputs/phase5_track_b/):
  - agent_ux_matrix.csv + agent_ux_matrix.json
  - agent_capability_matrix.csv
  - agent_integration_matrix.csv

Sources:
  - outputs/phase5_track_b/icoder_agents_hub_v2.json (24 iCoDer agents)
  - outputs/phase5_track_b/corti_raw/external_agents_experts.json (20 Corti agents)
  - outputs/phase5_track_b/agent_mapping.json (24 mappings)
  - reports/phase5_track_b/agents/001-005 (deep audit data)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "outputs" / "phase5_track_b"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_corti_agents() -> list[dict]:
    data = load_json(OUT_DIR / "corti_raw" / "external_agents_experts.json")
    return data.get("agents", [])


def load_icoder_agents() -> list[dict]:
    data = load_json(OUT_DIR / "icoder_agents_hub_v2.json")
    return data.get("agents", [])


def load_mapping() -> dict:
    return load_json(OUT_DIR / "agent_mapping.json")


# ── UX matrix (12 dims) ─────────────────────────────────────────────────────

UX_DIMS = [
    ("discoverability", "Hub card visible with clear name + icon + description"),
    ("comprehensibility", "Description + system prompt + use_case clear to a buyer"),
    ("input_clarity", "Example inputs documented; input schema enforced"),
    ("output_transparency", "Output schema documented; evidence quotes required"),
    ("error_handling", "Tool failures flagged; no silent fallback"),
    ("latency_transparency", "Latency visible per run + trace events"),
    ("auditability", "RunHistory + RunTrace pages; trace_refs in output"),
    ("trust_signals", "Maturity badge + red_lines + manual_review gate"),
    ("customization", "Clone + customize URL; config schema for params"),
    ("sdk_support", "A2A card + JS/Python SDK tabs in chat page"),
    ("cost_transparency", "Topbar live cost + per-run cost in trace"),
    ("consistency", "Same envelope shape across all agents"),
]


def score_ux_corti(agent: dict) -> dict:
    """Corti agents — assume production quality but limited transparency."""
    return {
        "discoverability": 5,
        "comprehensibility": 5,
        "input_clarity": 4,
        "output_transparency": 5,
        "error_handling": 4,
        "latency_transparency": 2,  # Corti doesn't expose latency per run
        "auditability": 2,  # No RunTrace UI per memory
        "trust_signals": 3,  # No maturity badge
        "customization": 5,
        "sdk_support": 5,
        "cost_transparency": 3,  # Topbar shows total but not per-run
        "consistency": 4,
    }


def score_ux_icoder(agent: dict) -> dict:
    """iCoDer agents — score based on hub metadata richness + runnable state."""
    is_metadata_only = agent.get("maturity") == "metadata-only" or not agent.get("runnable")
    base = {
        "discoverability": 5 if agent.get("category_display") else 3,
        "comprehensibility": 5 if agent.get("description") else 2,
        "input_clarity": 4 if agent.get("example_inputs") else 2,
        "output_transparency": 5 if agent.get("output_contract") else 2,
        "error_handling": 4,  # Phase 3-C1 7 error codes
        "latency_transparency": 5,  # latency_ms in envelope
        "auditability": 5,  # RunHistory + RunTrace
        "trust_signals": 5 if agent.get("red_lines") else 2,
        "customization": 5 if agent.get("clone_url") else 2,
        "sdk_support": 4,  # A2A for 5 agents only (GAP-13-01)
        "cost_transparency": 5,  # Topbar live cost (Phase 4-G)
        "consistency": 5,  # unified 13-field envelope
    }
    if is_metadata_only:
        # Metadata-only agents can't be run, so runtime UX dims are 0
        for k in ("input_clarity", "output_transparency", "error_handling",
                 "latency_transparency", "auditability", "cost_transparency", "consistency"):
            base[k] = 0
    return base


def build_ux_matrix(corti: list[dict], icoder: list[dict]) -> tuple[list[dict], dict]:
    rows = []
    summary = {"corti_avg": {}, "icoder_avg": {}, "icoder_runnable_avg": {}, "icoder_metadata_avg": {}}
    # Corti rows
    for a in corti:
        scores = score_ux_corti(a)
        rows.append({
            "agent_id": a.get("id"),
            "side": "corti",
            "category": a.get("category"),
            **scores,
            "total": sum(scores.values()),
        })
    # iCoDer rows
    icoder_runnable_totals = {d[0]: [] for d in UX_DIMS}
    icoder_metadata_totals = {d[0]: [] for d in UX_DIMS}
    for a in icoder:
        scores = score_ux_icoder(a)
        rows.append({
            "agent_id": a.get("agent_id"),
            "side": "icoder",
            "category": a.get("category_display") or a.get("category"),
            "runnable": a.get("runnable"),
            **scores,
            "total": sum(scores.values()),
        })
        bucket = icoder_runnable_totals if a.get("runnable") else icoder_metadata_totals
        for k, v in scores.items():
            bucket[k].append(v)
    # Averages
    corti_totals = {d[0]: [] for d in UX_DIMS}
    icoder_totals = {d[0]: [] for d in UX_DIMS}
    for r in rows:
        target = corti_totals if r["side"] == "corti" else icoder_totals
        for d, _ in UX_DIMS:
            target[d].append(r[d])
    for d, _ in UX_DIMS:
        summary["corti_avg"][d] = round(sum(corti_totals[d]) / max(1, len(corti_totals[d])), 2)
        summary["icoder_avg"][d] = round(sum(icoder_totals[d]) / max(1, len(icoder_totals[d])), 2)
        summary["icoder_runnable_avg"][d] = round(sum(icoder_runnable_totals[d]) / max(1, len(icoder_runnable_totals[d])), 2)
        summary["icoder_metadata_avg"][d] = round(sum(icoder_metadata_totals[d]) / max(1, len(icoder_metadata_totals[d])), 2)
    return rows, summary


# ── Capability matrix (23 dims) ─────────────────────────────────────────────

CAPABILITIES = [
    "fact_extraction",
    "normalization",
    "validation",
    "documentation_completeness",
    "code_search",
    "compliance_rules",
    "evidence_anchoring",
    "risk_scoring",
    "drg_dip_grouping",
    "coding_guidelines",
    "multi_language",
    "phi_redaction",
    "audit_trail",
    "streaming",
    "tool_calls",
    "expert_routing",
    "config_schema",
    "output_schema",
    "manual_review_gate",
    "trace_events",
    "cost_tracking",
    "latency_tracking",
    "api_key_auth",
]


def cap_corti(agent: dict, all_agents: list[dict]) -> dict:
    aid = agent.get("id", "")
    has_tools = bool(agent.get("tools"))
    return {
        "fact_extraction": 1 if "extractor" in aid or "coding" in aid else 0,
        "normalization": 1 if "coding" in aid else 0,
        "validation": 1 if "validation" in aid else 0,
        "documentation_completeness": 1 if "note-completeness" in aid or "cdi" in aid else 0,
        "code_search": 1 if "coding" in aid or "navigator" in aid else 0,
        "compliance_rules": 1 if "compliance" in aid or "validation" in aid else 0,
        "evidence_anchoring": 1 if "coding" in aid else 0,
        "risk_scoring": 1 if "risk" in aid or "triage" in aid else 0,
        "drg_dip_grouping": 0,  # No DRG/DIP in Corti
        "coding_guidelines": 1,
        "multi_language": 1,
        "phi_redaction": 1,
        "audit_trail": 1,
        "streaming": 1,
        "tool_calls": 1 if has_tools else 0,
        "expert_routing": 1,
        "config_schema": 1,
        "output_schema": 1,
        "manual_review_gate": 0,  # Corti prompt mentions but no hard gate
        "trace_events": 0,  # Not exposed in Corti UI
        "cost_tracking": 1,
        "latency_tracking": 0,  # Not exposed
        "api_key_auth": 1,
    }


def cap_icoder(agent: dict) -> dict:
    aid = agent.get("agent_id", "")
    is_meta = agent.get("maturity") == "metadata-only" or not agent.get("runnable")
    if is_meta:
        # Metadata-only agents have declared intent but no executable capability
        return {c: 0 for c in CAPABILITIES}
    base = {
        "fact_extraction": 1 if "extractor" in aid or "coding" in aid else 0,
        "normalization": 1 if "coding" in aid else 0,
        "validation": 1 if "validation" in aid else 0,
        "documentation_completeness": 1 if "note-completeness" in aid or "discharge-summary" in aid else 0,
        "code_search": 1 if "coding" in aid or "navigator" in aid else 0,
        "compliance_rules": 1 if "compliance" in aid or "validation" in aid else 0,
        "evidence_anchoring": 1 if "evidence" in aid else 0,
        "risk_scoring": 1 if "drg" in aid else 0,
        "drg_dip_grouping": 1 if "drg" in aid else 0,  # iCoDer ADVANTAGE
        "coding_guidelines": 1 if "coding" in aid else 0,
        "multi_language": 0,  # CN-only currently
        "phi_redaction": 1,  # Phase 3-C1
        "audit_trail": 1,  # RunHistory + AuditLog
        "streaming": 0,  # capabilities.streaming=false per A2A card
        "tool_calls": 1 if "validation" in aid else 0,
        "expert_routing": 0,  # Deterministic pipeline, not LLM routing
        "config_schema": 1,
        "output_schema": 1,
        "manual_review_gate": 1,  # red_lines + human_review
        "trace_events": 1,  # Inline + persisted
        "cost_tracking": 1,  # Phase 4-G
        "latency_tracking": 1,
        "api_key_auth": 1,
    }
    return base


def build_cap_matrix(corti: list[dict], icoder: list[dict]) -> list[dict]:
    rows = []
    for a in corti:
        caps = cap_corti(a, corti)
        rows.append({"agent_id": a.get("id"), "side": "corti", **caps})
    for a in icoder:
        caps = cap_icoder(a)
        rows.append({"agent_id": a.get("agent_id"), "side": "icoder",
                     "runnable": a.get("runnable"), **caps})
    return rows


# ── Integration matrix (16 dims) ────────────────────────────────────────────

INTEGRATIONS = [
    "browser_only",
    "server_api",
    "sdk_js",
    "sdk_python",
    "embedded_web_component",
    "batch_api",
    "streaming_sse",
    "webhook_callbacks",
    "a2a_protocol",
    "mcp_protocol",
    "oauth2",
    "api_key",
    "mtls",
    "webhooks_outbound",
    "storage_api",
    "multi_tenant",
]


def integ_corti() -> dict:
    return {
        "browser_only": 1,
        "server_api": 1,
        "sdk_js": 1,  # @corti/sdk
        "sdk_python": 0,  # No official Python SDK observed
        "embedded_web_component": 1,
        "batch_api": 0,
        "streaming_sse": 1,
        "webhook_callbacks": 1,
        "a2a_protocol": 1,  # A2A v0.3 per memory
        "mcp_protocol": 1,
        "oauth2": 1,
        "api_key": 1,
        "mtls": 0,
        "webhooks_outbound": 1,
        "storage_api": 1,
        "multi_tenant": 1,
    }


def integ_icoder() -> dict:
    return {
        "browser_only": 1,
        "server_api": 1,
        "sdk_js": 1,  # packages/icoder-embedded
        "sdk_python": 0,  # No Python SDK yet
        "embedded_web_component": 1,  # Phase 5 A4
        "batch_api": 0,
        "streaming_sse": 0,  # capabilities.streaming=false
        "webhook_callbacks": 0,
        "a2a_protocol": 1,  # Phase 4-F2
        "mcp_protocol": 1,  # Phase 3-C
        "oauth2": 1,
        "api_key": 1,  # Phase 4-G API Client
        "mtls": 0,
        "webhooks_outbound": 0,
        "storage_api": 1,
        "multi_tenant": 1,  # Cloud-flip Phase 5
    }


def build_integ_matrix() -> list[dict]:
    return [
        {"side": "corti", **integ_corti()},
        {"side": "icoder", **integ_icoder()},
    ]


# ── Main ────────────────────────────────────────────────────────────────────

def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    # Union of all keys to handle optional 'runnable' field
    fields = list({k for r in rows for k in r.keys()})
    # Stable order: known first
    priority = ["agent_id", "side", "category", "runnable", "total"]
    fields.sort(key=lambda x: priority.index(x) if x in priority else 99 + hash(x) % 1000)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    corti = load_corti_agents()
    icoder = load_icoder_agents()
    print(f"Corti agents: {len(corti)}")
    print(f"iCoDer agents: {len(icoder)}")

    # UX matrix
    ux_rows, ux_summary = build_ux_matrix(corti, icoder)
    write_csv(OUT_DIR / "agent_ux_matrix.csv", ux_rows)
    with (OUT_DIR / "agent_ux_matrix.json").open("w", encoding="utf-8") as f:
        json.dump({"rows": ux_rows, "summary": ux_summary, "dims": [d[0] for d in UX_DIMS]},
                  f, indent=2, ensure_ascii=False)
    print(f"UX matrix: {len(ux_rows)} rows; corti_avg total={sum(ux_summary['corti_avg'].values()):.1f}/60, "
          f"icoder_avg total={sum(ux_summary['icoder_avg'].values()):.1f}/60, "
          f"icoder_runnable total={sum(ux_summary['icoder_runnable_avg'].values()):.1f}/60")

    # Capability matrix
    cap_rows = build_cap_matrix(corti, icoder)
    write_csv(OUT_DIR / "agent_capability_matrix.csv", cap_rows)
    print(f"Capability matrix: {len(cap_rows)} rows × {len(CAPABILITIES)} dims")

    # Integration matrix
    integ_rows = build_integ_matrix()
    write_csv(OUT_DIR / "agent_integration_matrix.csv", integ_rows)
    print(f"Integration matrix: {len(integ_rows)} rows × {len(INTEGRATIONS)} dims")


if __name__ == "__main__":
    main()
