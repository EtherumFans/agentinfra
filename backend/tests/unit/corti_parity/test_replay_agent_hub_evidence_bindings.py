from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "corti_parity"
    / "replay_agent_hub_evidence_bindings.py"
)
SPEC = importlib.util.spec_from_file_location("replay_agent_hub_evidence_bindings", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_every_declared_evidence_binding_fails_closed_adversarially() -> None:
    agents_dir = Path(__file__).resolve().parents[3] / "official_agents"

    report = MODULE.replay(agents_dir)

    assert report["passed"] is True
    assert report["binding_agents"] == 19
    assert report["bindings"] == 30
    assert report["adversarial_assertions"] == 60
    assert report["detected_assertions"] == 60
    assert report["definition_errors"] == []
