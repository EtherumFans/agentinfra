import importlib.util
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = BACKEND_ROOT / "scripts" / "corti_parity" / "replay_agent_hub_cross_agent_relations.py"
SPEC = importlib.util.spec_from_file_location("replay_agent_hub_cross_agent_relations", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_visible_cross_agent_relations_detect_conflict_and_ambiguity() -> None:
    report = MODULE.replay(BACKEND_ROOT / "official_agents")

    assert report["passed"] is True
    assert report["relation_agents"] == 6
    assert report["relations"] == 10
    assert report["adversarial_assertions"] == 20
    assert report["detected_assertions"] == 20
    assert report["definition_errors"] == []
