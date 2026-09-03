"""iCoDer A1C.3 — HIS/EMR Simulator.

A pure-Python, no-third-party-dep simulator that emits realistic HIS/EMR
requests against the iCoDer patient-context API + document ingestion API +
agent_run + result callback webhook.

16 scenarios per PDF A1C.3 §七. Each scenario is a generator function that
yields request dicts; the simulator runner POSTs them sequentially and
records the outcome.

The simulator is **self-contained** — it does NOT depend on a live iCoDer
server. It can run in two modes:
- DRY_RUN (default): prints request/response JSON, no network calls
- LIVE: POSTs to a configurable base URL (ICODER_PILOT_URL)

Usage:
    python -m his_emr_simulator --scenario 1   # smoke
    python -m his_emr_simulator --all          # all 16
    python -m his_emr_simulator --list         # list scenarios
    ICODER_PILOT_URL=http://localhost:8000 python -m his_emr_simulator --all
"""
from .runner import SimulatorRunner, run_all_scenarios, SCENARIOS

__all__ = ["SimulatorRunner", "run_all_scenarios", "SCENARIOS"]
