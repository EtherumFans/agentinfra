"""AgentPackageV1 — formal schema for .icoder-agent version 1.x.

Every agent pack is validated against this schema before install or publish.
Validation covers: manifest, sha256 integrity, runtime_version compatibility,
permissions shape, and LLM capabilities declaration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .errors import ValidationError

FORMAT_VERSION_V1 = "1.1"

# Fields that are excluded from the integrity hash (metadata that changes post-pack)
_INTEGRITY_EXCLUDE = {"integrity", "downloads", "published_at", "loaded_at"}


def _sha256(data: dict) -> str:
    """Compute SHA-256 hash of a dict (excluding metadata fields)."""
    clean = {k: v for k, v in data.items() if k not in _INTEGRITY_EXCLUDE}
    raw = json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class AgentPackageV1:
    """Validated agent package V1.

    Use AgentPackageV1.from_dict(pack) to create a validated instance.

    Security tiers (computed):
      Tier 0: Pure prompt, no tools, no code
      Tier 1: Read-only tools (code dicts, rule lookups), no code execution
      Tier 2: Executable code via sandbox (community agents)
      Tier 3: Network access / external API calls
      Tier 4: Write-back to business systems (HIS/EMR/医保)
    """

    format_version: str
    agent_type: str  # "certified" | "community"
    name: str
    version: str
    description: str = ""
    category: str = "general"
    icon: str = "Bot"
    system_prompt: str = ""
    publisher_name: str = ""
    publisher_email: str = ""
    expert_count: int = 0
    tool_count: int = 0
    experts: list[dict] = field(default_factory=list)
    tools: list[dict] = field(default_factory=list)
    code: dict[str, str] = field(default_factory=dict)
    permissions: dict = field(default_factory=dict)
    requirements: dict = field(default_factory=dict)
    integrity: dict = field(default_factory=dict)
    llm_capabilities: dict = field(default_factory=dict)

    # ── Security tier ──

    @property
    def security_tier(self) -> int:
        """Compute the security tier for this agent."""
        if self.code:
            return 2  # Code execution
        if self.tools:
            # Check for network-requiring tools
            for t in self.tools:
                cat = (t.get("category") or "").lower()
                desc = (t.get("description") or "").lower()
                if any(kw in cat or kw in desc for kw in ("his", "emr", "api", "network", "http", "医保接口")):
                    return 3
                if any(kw in cat or kw in desc for kw in ("write", "modify", "update", "delete", "insert", "写")):
                    return 4
            # Has tools but no code → Tier 1 (read-only assumed)
            return 1
        return 0  # Pure prompt

    @property
    def approval_required(self) -> bool:
        """Tier 3+ requires admin approval."""
        return self.security_tier >= 3

    @property
    def default_disabled(self) -> bool:
        """Tier 2+ should be disabled by default after install."""
        return self.security_tier >= 2

    @property
    def tier_label(self) -> str:
        labels = {0: "Tier 0 — Pure Prompt", 1: "Tier 1 — Read-only Tools",
                  2: "Tier 2 — Sandbox Code", 3: "Tier 3 — Network Access",
                  4: "Tier 4 — System Write-back"}
        return labels.get(self.security_tier, f"Tier {self.security_tier} — Unknown")

    def permission_summary(self) -> dict:
        """Return a summary of permissions for audit/review before install."""
        tools_perm = self.permissions.get("tools", {})
        actions: dict[str, int] = {}
        for t_id, tperm in tools_perm.items():
            action = tperm.get("action", "allow") if isinstance(tperm, dict) else str(tperm)
            actions[action] = actions.get(action, 0) + 1
        return {
            "security_tier": self.security_tier,
            "tier_label": self.tier_label,
            "approval_required": self.approval_required,
            "default_disabled": self.default_disabled,
            "agent_type": self.agent_type,
            "tool_count": self.tool_count,
            "code_files": list(self.code.keys()),
            "permission_actions": actions,
            "llm_capabilities": self.llm_capabilities,
        }

    @classmethod
    def from_dict(cls, pack: dict, *, verify_integrity: bool = True) -> "AgentPackageV1":
        """Create a validated AgentPackageV1 from a raw pack dict.

        Raises ValidationError if validation fails.
        """
        errors: list[str] = []

        # ── Format version ──
        format_version = pack.get("format_version", "")
        if format_version != FORMAT_VERSION_V1:
            errors.append(f"Unsupported format_version: {format_version!r}. Expected {FORMAT_VERSION_V1!r}.")

        # ── Manifest ──
        manifest = pack.get("manifest", {})
        if not isinstance(manifest, dict):
            errors.append("manifest must be a dict.")
            manifest = {}

        name = manifest.get("name", "")
        version = manifest.get("version", "")
        if not name:
            errors.append("manifest.name is required.")
        if not version:
            errors.append("manifest.version is required.")

        description = manifest.get("description", "")
        category = manifest.get("category", "general")
        icon = manifest.get("icon", "Bot")

        # ── Agent type ──
        agent_type = pack.get("agent_type", "certified")
        if agent_type not in ("certified", "community"):
            errors.append(f"agent_type must be 'certified' or 'community', got {agent_type!r}.")

        # ── System prompt ──
        system_prompt = pack.get("system_prompt", "")
        if not system_prompt or not isinstance(system_prompt, str):
            errors.append("system_prompt is required and must be a non-empty string.")

        # ── Experts ──
        experts = pack.get("experts", [])
        if not isinstance(experts, list):
            errors.append("experts must be a list.")
            experts = []
        for i, e in enumerate(experts):
            if not e.get("id"):
                errors.append(f"experts[{i}]: id is required.")
            if not e.get("name"):
                errors.append(f"experts[{i}]: name is required.")

        # ── Tools ──
        tools = pack.get("tools", [])
        if not isinstance(tools, list):
            errors.append("tools must be a list.")
            tools = []
        valid_tiers = {1, 2}
        for i, t in enumerate(tools):
            if not t.get("id"):
                errors.append(f"tools[{i}]: id is required.")
            if not t.get("name"):
                errors.append(f"tools[{i}]: name is required.")
            tier = t.get("tier")
            if tier not in valid_tiers:
                errors.append(f"tools[{i}]: tier must be 1 or 2, got {tier!r}.")
            ef = t.get("executor_file")
            if ef:
                if agent_type != "community":
                    errors.append(f"tools[{i}]: executor_file requires agent_type='community'.")
                code = pack.get("code", {})
                if ef not in code:
                    errors.append(f"tools[{i}]: executor_file {ef!r} not found in code/.")

        # ── Code (community only) ──
        code = pack.get("code", {})
        if not isinstance(code, dict):
            errors.append("code must be a dict.")
            code = {}
        if agent_type == "certified" and code:
            errors.append("certified agents cannot contain code/.")
        for filename, source in code.items():
            if not isinstance(source, str) or len(source) == 0:
                errors.append(f"code/{filename}: empty or invalid.")
            if len(source) > 100_000:
                errors.append(f"code/{filename}: exceeds 100KB limit.")

        # ── Permissions ──
        permissions = pack.get("permissions", {})
        if not isinstance(permissions, dict):
            errors.append("permissions must be a dict.")
            permissions = {}
        tools_perm = permissions.get("tools", {})
        if not isinstance(tools_perm, dict):
            errors.append("permissions.tools must be a dict.")
        for tool_id, tperm in tools_perm.items():
            if not isinstance(tperm, dict):
                errors.append(f"permissions.tools.{tool_id}: must be a dict.")
                continue
            action = tperm.get("action", "")
            if action not in ("allow", "deny", "require_human", ""):
                errors.append(f"permissions.tools.{tool_id}.action: must be allow/deny/require_human.")

        # ── Requirements ──
        requirements = pack.get("requirements", {})
        if not isinstance(requirements, dict):
            errors.append("requirements must be a dict.")
            requirements = {}
        min_runtime = requirements.get("min_runtime_version", "")
        if not min_runtime:
            errors.append("requirements.min_runtime_version is required.")

        # ── LLM Capabilities ──
        llm_capabilities = pack.get("llm_capabilities", {})
        if not isinstance(llm_capabilities, dict):
            errors.append("llm_capabilities must be a dict.")
            llm_capabilities = {}
        else:
            _validate_llm_capabilities(llm_capabilities, errors)

        # ── Integrity check ──
        integrity = pack.get("integrity", {})
        if verify_integrity and integrity:
            expected_sha = integrity.get("sha256", "")
            if expected_sha:
                actual_sha = _sha256(pack)
                if actual_sha != expected_sha:
                    errors.append(
                        f"Integrity check failed: sha256 mismatch. "
                        f"Expected {expected_sha[:16]}..., got {actual_sha[:16]}..."
                    )

        if errors:
            raise ValidationError(errors)

        return cls(
            format_version=format_version,
            agent_type=agent_type,
            name=name,
            version=version,
            description=description,
            category=category,
            icon=icon,
            system_prompt=system_prompt,
            publisher_name=pack.get("publisher_name", ""),
            publisher_email=pack.get("publisher_email", ""),
            expert_count=len(experts),
            tool_count=len(tools),
            experts=experts,
            tools=tools,
            code=code,
            permissions=permissions,
            requirements=requirements,
            integrity=integrity,
            llm_capabilities=llm_capabilities,
        )

    def to_summary(self) -> dict[str, Any]:
        """Return a summary dict suitable for API responses."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "agent_type": self.agent_type,
            "format_version": self.format_version,
            "expert_count": self.expert_count,
            "tool_count": self.tool_count,
            "publisher_name": self.publisher_name,
            "publisher_email": self.publisher_email,
            "min_runtime_version": self.requirements.get("min_runtime_version", ""),
            "llm_capabilities": self.llm_capabilities,
            "integrity": self.integrity,
        }


def _validate_llm_capabilities(caps: dict, errors: list[str]):
    """Validate the llm_capabilities section of an agent pack."""
    # Optional: validate specific capability shapes
    required_models = caps.get("required_models", [])
    if isinstance(required_models, list):
        for i, model_spec in enumerate(required_models):
            if isinstance(model_spec, dict):
                if not model_spec.get("name"):
                    errors.append(f"llm_capabilities.required_models[{i}]: name is required.")
            else:
                errors.append(f"llm_capabilities.required_models[{i}]: must be a dict.")
    elif required_models:
        errors.append("llm_capabilities.required_models: must be a list if present.")

    min_tokens = caps.get("min_total_tokens")
    if min_tokens is not None and not isinstance(min_tokens, (int, float)):
        errors.append("llm_capabilities.min_total_tokens: must be a number.")

    supports_tools = caps.get("supports_tool_calling")
    if supports_tools is not None and not isinstance(supports_tools, bool):
        errors.append("llm_capabilities.supports_tool_calling: must be a boolean.")

    supports_json = caps.get("supports_json_mode")
    if supports_json is not None and not isinstance(supports_json, bool):
        errors.append("llm_capabilities.supports_json_mode: must be a boolean.")
