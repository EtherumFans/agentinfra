"""Agent Pack — .icoder-agent format (JSON-based, self-contained).

Format spec:
  {
    "format_version": "1.0",
    "manifest": {name, version, description, category, icon},
    "system_prompt": "...",
    "experts": [{id, name, description, system_prompt, capabilities, config}],
    "tools": [{id, name, description, tier, category, requires, guarantees,
               params: {key: {type, required, description}}, accuracy_tags,
               is_injectable}],
    "permissions": {key, name, description,
                    tools: {tool_id: {action: "allow"|"deny"|"require_human",
                                      max_per_session: int}}},
    "requirements": {min_runtime_version: "1.0.0"}
  }

All references are self-contained — no external service dependencies.
"""

import json
import hashlib
import logging
from pathlib import Path
from typing import Optional

from .types import AgentDefinition, ExpertDefinition, ToolDefinition, ToolTier
from .permissions import PermissionPolicy, ToolPermission

logger = logging.getLogger(__name__)

FORMAT_VERSION = "1.0"
FILE_EXTENSION = ".icoder-agent"


def _hash(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def export_pack(agent: AgentDefinition,
                experts: list[ExpertDefinition] | None = None,
                tools: list[ToolDefinition] | None = None,
                permission: dict | None = None) -> dict:
    """Build a .icoder-agent pack dict from Agent + Experts + Tools."""
    pack = {
        "format_version": FORMAT_VERSION,
        "manifest": {
            "name": agent.name,
            "version": agent.version,
            "description": agent.description,
            "category": agent.category,
            "icon": agent.icon,
        },
        "system_prompt": agent.system_prompt,
        "experts": [
            {
                "id": e.id, "name": e.name, "description": e.description,
                "system_prompt": e.system_prompt, "capabilities": e.capabilities,
                "config": e.config,
            }
            for e in (experts or [])
        ],
        "tools": [
            {
                "id": t.id, "name": t.name, "description": t.description,
                "tier": t.tier.value, "category": t.category, "icon": t.icon,
                "requires": t.requires, "guarantees": t.guarantees,
                "params": (t.input_schema or {}).get("properties", {}),
                "accuracy_tags": t.accuracy_tags,
                "is_injectable": t.is_injectable,
            }
            for t in (tools or [])
        ],
        "permissions": permission or {},
        "requirements": {
            "min_runtime_version": "1.0.0",
        },
    }
    pack["integrity"] = {"sha256": _hash(pack)}
    return pack


def save_pack(pack: dict, path: str | Path) -> Path:
    """Save pack dict to a .icoder-agent file."""
    path = Path(path)
    if not path.suffix:
        path = path.with_suffix(FILE_EXTENSION)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=2)
    return path


def load_pack(path: str | Path) -> dict:
    """Load a .icoder-agent file and return the pack dict."""
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        pack = json.load(f)
    return pack


def validate_pack(pack: dict) -> list[str]:
    """Validate a pack dict. Returns list of errors (empty = valid)."""
    errors = []

    # Format version
    if pack.get("format_version") != FORMAT_VERSION:
        errors.append(f"Unsupported format version: {pack.get('format_version')}")

    # Manifest
    manifest = pack.get("manifest", {})
    if not manifest.get("name"):
        errors.append("Missing manifest.name")
    if not manifest.get("version"):
        errors.append("Missing manifest.version")

    # System prompt
    if not pack.get("system_prompt"):
        errors.append("Missing system_prompt")

    # Experts
    for i, e in enumerate(pack.get("experts", [])):
        if not e.get("id"):
            errors.append(f"Expert[{i}]: missing id")
        if not e.get("name"):
            errors.append(f"Expert[{i}]: missing name")

    # Tools
    for i, t in enumerate(pack.get("tools", [])):
        if not t.get("id"):
            errors.append(f"Tool[{i}]: missing id")
        if not t.get("name"):
            errors.append(f"Tool[{i}]: missing name")
        tier = t.get("tier")
        if tier not in (1, 2):
            errors.append(f"Tool[{i}]: invalid tier {tier}")

    # Requirements
    req = pack.get("requirements", {})
    if not req.get("min_runtime_version"):
        errors.append("Missing requirements.min_runtime_version")

    return errors


def import_pack(pack: dict) -> tuple[AgentDefinition, list[ExpertDefinition],
                                      list[ToolDefinition], dict]:
    """Import a pack dict, returning Agent + Experts + Tools + Permissions.

    Validation should be called first — this does NOT validate.
    """
    manifest = pack["manifest"]
    agent = AgentDefinition(
        name=manifest["name"],
        version=manifest.get("version", "1.0.0"),
        description=manifest.get("description", ""),
        category=manifest.get("category", "general"),
        icon=manifest.get("icon", "Bot"),
        system_prompt=pack.get("system_prompt", ""),
        expert_ids=[e["id"] for e in pack.get("experts", [])],
    )

    experts = [
        ExpertDefinition(
            id=e["id"], name=e["name"],
            description=e.get("description", ""),
            system_prompt=e.get("system_prompt", ""),
            capabilities=e.get("capabilities", []),
            config=e.get("config", {}),
        )
        for e in pack.get("experts", [])
    ]

    tools = [
        ToolDefinition(
            id=t["id"], name=t["name"],
            description=t.get("description", ""),
            tier=ToolTier(t.get("tier", 2)),
            category=t.get("category", "general"),
            icon=t.get("icon", "Wrench"),
            requires=t.get("requires", []),
            guarantees=t.get("guarantees", {}),
            input_schema={"type": "object", "properties": t.get("params", {})} if t.get("params") else None,
            accuracy_tags=t.get("accuracy_tags", []),
            is_injectable=t.get("is_injectable", False),
        )
        for t in pack.get("tools", [])
    ]

    permissions = pack.get("permissions", {})

    return agent, experts, tools, permissions


def pack_from_template(template: dict) -> dict:
    """Convert an Agent template dict (from AGENT_TEMPLATES) to a .icoder-agent pack.

    Template format: {id, title, description, category, icon, expert_ids, system_prompt, config}
    """
    agent = AgentDefinition(
        name=template.get("title", template.get("id", "Untitled")),
        description=template.get("description", ""),
        category=template.get("category", "general"),
        icon=template.get("icon", "Bot"),
        system_prompt=template.get("system_prompt", ""),
        expert_ids=template.get("expert_ids", []),
        config=template.get("config", {}),
    )
    return export_pack(agent)


def export_template_as_file(template: dict, output_path: str | Path) -> Path:
    """Export an Agent template to a .icoder-agent file."""
    pack = pack_from_template(template)
    filename = f"{template.get('id', 'agent')}-v1.0.0"
    return save_pack(pack, Path(output_path) / filename)
