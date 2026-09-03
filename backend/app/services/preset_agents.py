"""iCoDer Preset Agents service — loads the A1B-AE.8 catalog and emits
Corti §6-compatible Agent Cards.

The catalog lives at ``backend/agent_catalog/icoder_preset_agents.json``.
This service loads it hermetically (no network) and exposes:

- ``all_presets()`` → list of ``PresetAgent`` dataclasses
- ``get_preset(canonical_key)`` → ``PresetAgent | None``
- ``corti_agent_card(canonical_key)`` → Corti §6 camelCase dict for the
  preset, with experts[] inline-expanded using A1B-AE.3..7 Expert
  canonical metadata.

Charter Amendment 1 §7: presets are ICODER_INTERNAL provenance; the
underlying Experts they reference may be CLEAN_ROOM_PUBLIC or
ICODER_INTERNAL individually.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CATALOG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "agent_catalog"
    / "icoder_preset_agents.json"
)


@dataclass
class PresetExpertRef:
    canonical_key: str
    role: str


@dataclass
class PresetAgent:
    canonical_key: str
    name: str
    name_zh: str
    description: str
    agent_type: str
    system_prompt: str
    experts: list[PresetExpertRef] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    corti_alignment: str = "CORTI_ADAPTED"
    delegates_to_pack: str | None = None
    red_lines: dict[str, bool] = field(default_factory=dict)
    default_runtime_mode: str = "corti_like_fast"
    available_runtime_modes: list[str] = field(default_factory=list)

    def corti_agent_card(self) -> dict[str, Any]:
        """Emit a Corti §6 Agent Card (camelCase) for this preset.

        Per A1B-AE.1 §2.1: name, description, systemPrompt, agentType,
        experts[], mcpServers[]. iCoDer extensions (red_lines,
        delegates_to_pack, runtime modes) are namespaced under
        ``icoder_ext`` to keep the Corti surface clean.
        """
        return {
            "name": self.name,
            "description": self.description,
            "systemPrompt": self.system_prompt,
            "agentType": self.agent_type,
            "experts": [
                {"canonicalKey": e.canonical_key, "role": e.role}
                for e in self.experts
            ],
            "mcpServers": list(self.mcp_servers),
            "icoder_ext": {
                "canonical_key": self.canonical_key,
                "name_zh": self.name_zh,
                "corti_alignment": self.corti_alignment,
                "delegates_to_pack": self.delegates_to_pack,
                "red_lines": dict(self.red_lines),
                "default_runtime_mode": self.default_runtime_mode,
                "available_runtime_modes": list(self.available_runtime_modes),
            },
        }


_LOADED_PRESETS: dict[str, PresetAgent] | None = None


def _load_catalog() -> dict[str, PresetAgent]:
    global _LOADED_PRESETS
    if _LOADED_PRESETS is not None:
        return _LOADED_PRESETS

    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    out: dict[str, PresetAgent] = {}
    for entry in raw.get("presets", []):
        preset = PresetAgent(
            canonical_key=entry["canonical_key"],
            name=entry["name"],
            name_zh=entry.get("name_zh", entry["name"]),
            description=entry["description"],
            agent_type=entry["agent_type"],
            system_prompt=entry["system_prompt"],
            experts=[
                PresetExpertRef(
                    canonical_key=e["canonical_key"],
                    role=e.get("role", "primary"),
                )
                for e in entry.get("experts", [])
            ],
            mcp_servers=list(entry.get("mcp_servers", [])),
            corti_alignment=entry.get("corti_alignment", "CORTI_ADAPTED"),
            delegates_to_pack=entry.get("delegates_to_pack"),
            red_lines=dict(entry.get("red_lines", {})),
            default_runtime_mode=entry.get(
                "default_runtime_mode", "corti_like_fast"
            ),
            available_runtime_modes=list(
                entry.get("available_runtime_modes", ["corti_like_fast"])
            ),
        )
        out[preset.canonical_key] = preset

    _LOADED_PRESETS = out
    return out


def all_presets() -> list[PresetAgent]:
    """Return all preset agents (deterministic order: catalog order)."""
    return list(_load_catalog().values())


def get_preset(canonical_key: str) -> PresetAgent | None:
    return _load_catalog().get(canonical_key)


def corti_agent_card(canonical_key: str) -> dict[str, Any] | None:
    preset = get_preset(canonical_key)
    if preset is None:
        return None
    return preset.corti_agent_card()


def preset_keys() -> list[str]:
    return list(_load_catalog().keys())


__all__ = [
    "CATALOG_PATH",
    "PresetExpertRef",
    "PresetAgent",
    "all_presets",
    "get_preset",
    "corti_agent_card",
    "preset_keys",
]
