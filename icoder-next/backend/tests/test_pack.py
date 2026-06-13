"""Phase 4 — Agent 打包/分发: the .icoder-agent pack format + Marketplace + CLI.

Proves the full ISV/operator lifecycle on the slice's stdlib pack format:
pack → publish → install → AgentRunner, plus integrity (a tampered pack is refused),
round-trip fidelity (Chinese system_prompt + rule_sets survive), and latest-version
resolution. The money test installs a packed agent into a *fresh* registry and runs it
end-to-end through the 7-stage runner.
"""
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from sample_data import SAMPLE_TEXT

from icoder import cli
from icoder.experts.coding_expert import CodingExpert
from icoder.runtime import pack as packlib
from icoder.runtime.gateway import DeterministicProvider, LLMGateway
from icoder.runtime.pack import (
    Marketplace,
    PackError,
    PackIntegrityError,
    PackSchemaError,
    install,
    manifest_to_agent,
    pack,
    read_manifest,
    verify_pack,
)
from icoder.runtime.registry import AgentRegistry, default_registry
from icoder.runtime.runner import AgentRunner

AGENT_ID = "icoder/homepage-coding-review-agent"


def _agent(agent_id: str = AGENT_ID):
    return default_registry().get(agent_id)


# ---- pack format unit ----

def test_pack_writes_a_zip_icoder_agent_file(tmp_path):
    path = pack(_agent(), str(tmp_path))
    p = Path(path)
    assert p.suffix == ".icoder-agent"
    assert p.name == "icoder__homepage-coding-review-agent-1.0.0.icoder-agent"
    assert zipfile.is_zipfile(p)
    with zipfile.ZipFile(p) as z:
        assert "manifest.json" in z.namelist()


def test_round_trip_preserves_all_fields(tmp_path):
    original = _agent()
    path = pack(original, str(tmp_path))
    restored = manifest_to_agent(read_manifest(path))
    assert restored == original  # dataclass equality over all 9 fields
    # spot-check the load-bearing ones survived (Chinese prompt, experts, default rule_sets)
    assert restored.rule_sets == ["medical_coding"]
    assert "coding-expert" in restored.experts
    assert "{{COMPLIANCE_RULESET}}" in restored.system_prompt


def test_verify_pack_accepts_a_clean_pack(tmp_path):
    path = pack(_agent(), str(tmp_path))
    manifest = verify_pack(path)
    assert manifest["schema"] == "icoder-agent/v1"
    assert manifest["digest"].startswith("sha256:")


def test_install_registers_into_a_fresh_registry(tmp_path):
    path = pack(_agent(), str(tmp_path))
    reg = AgentRegistry()
    assert reg.get(AGENT_ID) is None
    agent = install(path, reg)
    assert agent.id == AGENT_ID
    assert reg.get(AGENT_ID) is agent


def test_tampered_manifest_fails_integrity(tmp_path):
    path = pack(_agent(), str(tmp_path))
    manifest = read_manifest(path)
    manifest["agent"]["name"] = "被篡改的名称"  # mutate body, keep the old digest
    tampered = tmp_path / "tampered.icoder-agent"
    with zipfile.ZipFile(tampered, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    with pytest.raises(PackIntegrityError):
        verify_pack(str(tampered))


def test_non_zip_file_is_rejected(tmp_path):
    bad = tmp_path / "bad.icoder-agent"
    bad.write_text("not a zip", encoding="utf-8")
    with pytest.raises(PackSchemaError):
        read_manifest(str(bad))


def test_unknown_schema_is_rejected(tmp_path):
    bad = tmp_path / "wrong-schema.icoder-agent"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("manifest.json", json.dumps({"schema": "bogus/v9", "agent": {}}))
    with pytest.raises(PackSchemaError):
        read_manifest(str(bad))


def test_manifest_to_agent_tolerates_forward_compat_keys():
    agent = manifest_to_agent({"agent": {
        "id": "icoder/x", "name": "X", "version": "1.0.0", "category": "C",
        "experts": ["coding-expert"], "system_prompt": "p", "non_goals": [],
        "output_contract": "o", "rule_sets": ["medical_coding"],
        "future_field": "ignored",  # a newer packer added a field this slice doesn't know
    }})
    assert agent.id == "icoder/x"
    assert not hasattr(agent, "future_field")


# ---- marketplace ----

def test_publish_then_list(tmp_path):
    path = pack(_agent(), str(tmp_path / "build"))
    market = Marketplace(str(tmp_path / "market"))
    entry = market.publish(path)
    assert entry["id"] == AGENT_ID and entry["version"] == "1.0.0"
    listed = market.list()
    assert len(listed) == 1
    assert listed[0]["digest"] == entry["digest"]
    assert (market.packs_dir / listed[0]["filename"]).is_file()


def test_publish_is_idempotent_per_id_version(tmp_path):
    path = pack(_agent(), str(tmp_path / "build"))
    market = Marketplace(str(tmp_path / "market"))
    market.publish(path)
    market.publish(path)  # re-publish same coordinates -> upsert, not duplicate
    assert len(market.list()) == 1


def test_install_from_marketplace_into_registry(tmp_path):
    path = pack(_agent(), str(tmp_path / "build"))
    market = Marketplace(str(tmp_path / "market"))
    market.publish(path)
    reg = AgentRegistry()
    agent = market.install(AGENT_ID, reg)
    assert reg.get(AGENT_ID) is agent


def test_install_resolves_latest_version(tmp_path):
    base = _agent()
    build = str(tmp_path / "build")
    market = Marketplace(str(tmp_path / "market"))
    market.publish(pack(base, build))                       # 1.0.0
    market.publish(pack(replace(base, version="1.2.0"), build))  # 1.2.0
    agent = market.install(AGENT_ID, AgentRegistry())       # no version pin
    assert agent.version == "1.2.0"


def test_install_honors_pinned_version(tmp_path):
    base = _agent()
    build = str(tmp_path / "build")
    market = Marketplace(str(tmp_path / "market"))
    market.publish(pack(base, build))
    market.publish(pack(replace(base, version="1.2.0"), build))
    agent = market.install(AGENT_ID, AgentRegistry(), version="1.0.0")
    assert agent.version == "1.0.0"


def test_install_unknown_agent_raises(tmp_path):
    market = Marketplace(str(tmp_path / "market"))
    with pytest.raises(PackError):
        market.install("icoder/nope", AgentRegistry())


# ---- the money test: pack -> publish -> install -> AgentRunner ----

def test_installed_agent_runs_end_to_end(tmp_path):
    """A packed agent, installed into an otherwise-empty registry, runs through the full
    7-stage pipeline and yields the same primary/candidates as the built-in agent."""
    path = pack(_agent(), str(tmp_path / "build"))
    market = Marketplace(str(tmp_path / "market"))
    market.publish(path)

    fresh = AgentRegistry()                       # nothing built-in
    market.install(AGENT_ID, fresh)
    expert = CodingExpert()
    gateway = LLMGateway(DeterministicProvider(expert.lexicon()))
    runner = AgentRunner(gateway=gateway, agents=fresh, expert=expert)

    run = runner.run(AGENT_ID, SAMPLE_TEXT)
    assert run.codes[0].code == "I50.900"
    cand = {c.code for c in run.candidates}
    assert {"M80.900", "45.1600x001"} <= cand
    assert run.compliance.rule_set == "medical_coding"


# ---- CLI ----

def test_cli_pack_publish_list(tmp_path, capsys):
    out = str(tmp_path / "build")
    market = str(tmp_path / "market")
    assert cli.main(["pack", AGENT_ID, "--out", out]) == 0
    packed = next(Path(out).glob("*.icoder-agent"))
    assert cli.main(["publish", str(packed), "--market", market]) == 0
    assert cli.main(["list", "--market", market]) == 0
    assert AGENT_ID in capsys.readouterr().out


def test_cli_install_reports_installed(tmp_path, capsys):
    out = str(tmp_path / "build")
    market = str(tmp_path / "market")
    cli.main(["pack", AGENT_ID, "--out", out])
    packed = next(Path(out).glob("*.icoder-agent"))
    cli.main(["publish", str(packed), "--market", market])
    assert cli.main(["install", AGENT_ID, "--market", market]) == 0
    assert "installed" in capsys.readouterr().out


def test_cli_pack_unknown_agent_returns_2(capsys):
    assert cli.main(["pack", "icoder/nope", "--out", "."]) == 2


def test_cli_install_missing_returns_1(tmp_path):
    market = str(tmp_path / "market")
    assert cli.main(["install", "icoder/nope", "--market", market]) == 1
