"""Agent Pack — .icoder-agent format (JSON-based, self-contained).

Format spec:
  {
    "format_version": "1.1",
    "agent_type": "certified" | "community",
    "manifest": {name, version, description, category, icon},
    "system_prompt": "...",
    "experts": [{id, name, description, system_prompt, capabilities, config}],
    "tools": [{id, name, description, tier, category, requires, guarantees,
               params: {key: {type, required, description}}, accuracy_tags,
               is_injectable, executor_file: "<path in code/>"}],
    "code": {"tool_id.py": "<Python source with def run(params): return dict>"},
    "permissions": {key, name, description,
                    tools: {tool_id: {action: "allow"|"deny"|"require_human",
                                      max_per_session: int}}},
    "requirements": {min_runtime_version: "1.0.0"}
  }

- agent_type="certified": no code/ allowed, pure declarative
- agent_type="community": code/ allowed, sandboxed execution
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from .types import AgentDefinition, ExpertDefinition, ToolDefinition, ToolTier
from .permissions import PermissionPolicy, ToolPermission

logger = logging.getLogger(__name__)

FORMAT_VERSION = "1.1"
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
        valid_tiers = {t.value for t in ToolTier}
        if tier not in valid_tiers:
            errors.append(f"Tool[{i}]: invalid tier {tier} (valid: {sorted(valid_tiers)})")

    # Agent type validation
    agent_type = pack.get("agent_type", "certified")
    if agent_type not in ("certified", "community"):
        errors.append(f"Invalid agent_type: {agent_type}")

    # Code validation: only community agents may contain code
    if agent_type == "community":
        code = pack.get("code", {})
        for filename, source in code.items():
            if not isinstance(source, str) or len(source) == 0:
                errors.append(f"code/{filename}: empty or invalid")
            if len(source) > 100_000:
                errors.append(f"code/{filename}: exceeds 100KB limit")
            if "import os" in source.lower() and "import os.path" not in source.lower():
                pass  # minimal os imports may be useful, rely on sandbox restrictions
    elif pack.get("code"):
        errors.append("certified agents cannot contain code/")

    # Tool executor_file references must exist in code/
    for i, t in enumerate(pack.get("tools", [])):
        ef = t.get("executor_file")
        if ef:
            if agent_type != "community":
                errors.append(f"Tool[{i}]: executor_file requires agent_type=community")
            if ef not in pack.get("code", {}):
                errors.append(f"Tool[{i}]: executor_file '{ef}' not found in code/")

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
    # v1.1 packs use experts[].id; v1.2 packs (Phase D 2026-06-22+) use
    # experts[].expert_id. Accept either — Loader is the single point of truth
    # for which key is canonical per format_version.
    def _expert_id(e: dict) -> str:
        return e.get("id") or e.get("expert_id") or ""
    agent = AgentDefinition(
        name=manifest["name"],
        version=manifest.get("version", "1.0.0"),
        description=manifest.get("description", ""),
        category=manifest.get("category", "general"),
        icon=manifest.get("icon", "Bot"),
        system_prompt=pack.get("system_prompt", ""),
        expert_ids=[_expert_id(e) for e in pack.get("experts", [])],
    )

    experts = [
        ExpertDefinition(
            id=_expert_id(e), name=e["name"],
            description=e.get("description", ""),
            system_prompt=e.get("system_prompt", ""),
            capabilities=e.get("capabilities", []),
            config=e.get("config", {}),
        )
        for e in pack.get("experts", [])
    ]

    code_files = pack.get("code", {})
    tools = []
    for t in pack.get("tools", []):
        # Accept both string tool IDs and full tool dicts
        if isinstance(t, str):
            tool_def = {"id": t, "name": t, "description": t, "tier": 1, "category": "general"}
        else:
            tool_def = t
        # v1.2 tools use `name` as the canonical id (no separate `id` field),
        # and `type` (mcp/guard/function/builtin) instead of `tier`. Map to the
        # v1.1 ToolDefinition shape.
        tool_id = tool_def.get("id") or tool_def.get("name", "")
        tool_name = tool_def.get("name", tool_id)
        # v1.2 `type`: mcp/function/builtin → tier 1 (deterministic),
        # guard → tier 2 (LLM-backed). v1.1 `tier` overrides if present.
        t_type = tool_def.get("type")
        if "tier" in tool_def:
            tier_value = tool_def["tier"]
        elif t_type in ("mcp", "function", "builtin"):
            tier_value = 1
        elif t_type == "guard":
            tier_value = 2
        else:
            tier_value = 2
        executor = None
        ef = tool_def.get("executor_file")
        if ef and ef in code_files:
            from .sandbox import execute as sandbox_exec
            source = code_files[ef]

            def _make_executor(src):
                def _runner(**params):
                    return sandbox_exec(src, params)
                return _runner

            executor = _make_executor(source)

        tools.append(ToolDefinition(
            id=tool_id, name=tool_name,
            description=tool_def.get("description", ""),
            tier=ToolTier(tier_value),
            category=tool_def.get("category", "general"),
            icon=tool_def.get("icon", "Wrench"),
            requires=tool_def.get("requires", []),
            guarantees=tool_def.get("guarantees", {}),
            input_schema={"type": "object", "properties": tool_def.get("params", {})} if tool_def.get("params") else None,
            accuracy_tags=tool_def.get("accuracy_tags", []),
            is_injectable=tool_def.get("is_injectable", False),
            executor=executor,
        ))

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
