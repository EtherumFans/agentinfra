"""ExpertRegistry — the capability resolver behind the agents×experts split."""

from icoder.experts.coding_expert import CodingExpert
from icoder.experts.registry import ExpertRegistry, default_expert_registry


def test_default_registry_has_coding_and_grouping():
    reg = default_expert_registry()
    assert reg.get("coding-expert") is not None
    assert reg.get("grouping-expert") is not None
    assert {e.id for e in reg.list()} == {"coding-expert", "grouping-expert"}


def test_register_keys_by_expert_id():
    reg = ExpertRegistry()
    reg.register(CodingExpert())
    assert isinstance(reg.get("coding-expert"), CodingExpert)


def test_get_unknown_returns_none():
    assert ExpertRegistry().get("nope") is None


def test_register_overwrites_same_id():
    reg = ExpertRegistry()
    first, second = CodingExpert(), CodingExpert()
    reg.register(first)
    reg.register(second)
    assert reg.get("coding-expert") is second
    assert len(reg.list()) == 1
