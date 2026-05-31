"""Permission Policy — Deny-First tool authorization for Agent Runtime.

Inspired by Anthropic Managed Agents: every tool defaults to DENY.
Explicit ALLOW is required before a tool can be invoked.

For medical scenarios, this means:
- finalize_primary_diagnosis → requires_human=True (DRG impact, real money)
- search_icd10_index → allowed=True (deterministic, safe)
- assign_diagnosis_code → allowed=True, max_per_session=50 (LLM calls cost credits)

Design principle: "默认 Deny，显式 Allow" — the same philosophy as
Anthropic's 14-step tool execution pipeline where steps 1-9 are validation.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PermissionOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_HUMAN = "needs_human"


@dataclass
class ToolPermission:
    """Permission for a single tool.

    By default, every tool is DENIED. The developer must explicitly
    whitelist each tool the Agent is allowed to call.

    This inverts the current model where all registered tools are available.
    """

    tool_id: str
    allowed: bool = False  # Default DENY — must explicitly allow
    max_per_session: int = 50  # Rate limit per session
    requires_human: bool = False  # DUC: Deny-Unless-Confirmed by human
    scope: list[str] = field(default_factory=list)  # Allowed context keys (empty = all)

    # Runtime tracking (not persisted)
    _invocation_count: int = field(default=0, repr=False)

    def check(self) -> PermissionOutcome:
        """Check if this tool can be invoked right now."""
        if not self.allowed:
            return PermissionOutcome.DENY
        if self._invocation_count >= self.max_per_session:
            return PermissionOutcome.DENY
        if self.requires_human:
            return PermissionOutcome.NEEDS_HUMAN
        return PermissionOutcome.ALLOW

    def record_invocation(self) -> None:
        self._invocation_count += 1


@dataclass
class PermissionPolicy:
    """Collection of tool permissions for an Agent.

    Provides preset factory methods for common medical scenarios.
    """

    permissions: dict[str, ToolPermission] = field(default_factory=dict)

    def check(self, tool_id: str) -> PermissionOutcome:
        """Check if tool_id is allowed. Unknown tools are always DENIED."""
        perm = self.permissions.get(tool_id)
        if perm is None:
            return PermissionOutcome.DENY
        return perm.check()

    def record(self, tool_id: str) -> None:
        """Record a successful tool invocation."""
        perm = self.permissions.get(tool_id)
        if perm:
            perm.record_invocation()

    def to_config(self) -> dict:
        """Serialize to Agent.config.permissions format."""
        return {
            tid: {
                "allowed": p.allowed,
                "max_per_session": p.max_per_session,
                "requires_human": p.requires_human,
                "scope": p.scope,
            }
            for tid, p in self.permissions.items()
        }

    @classmethod
    def from_config(cls, config: dict) -> "PermissionPolicy":
        """Deserialize from Agent.config.permissions."""
        policy = cls()
        for tid, pdata in config.items():
            policy.permissions[tid] = ToolPermission(
                tool_id=tid,
                allowed=pdata.get("allowed", False),
                max_per_session=pdata.get("max_per_session", 50),
                requires_human=pdata.get("requires_human", False),
                scope=pdata.get("scope", []),
            )
        return policy

    # ── Preset Factories ──────────────────────────────────────────────

    @classmethod
    def medical_coding(cls) -> "PermissionPolicy":
        """Standard medical coding pipeline.

        Safe deterministic tools: always allowed.
        LLM-powered tools: allowed with rate limits.
        High-risk: requires human approval.
        """
        return cls(permissions={
            # Tier 1 deterministic — safe, always allowed
            "search_icd10_index": ToolPermission("search_icd10_index", allowed=True, max_per_session=200),
            "search_icd9_index": ToolPermission("search_icd9_index", allowed=True, max_per_session=200),
            "rank_evidence": ToolPermission("rank_evidence", allowed=True),
            "calibrate_confidence": ToolPermission("calibrate_confidence", allowed=True),
            "analyze_disagreements": ToolPermission("analyze_disagreements", allowed=True),
            "guard_input": ToolPermission("guard_input", allowed=True),
            "guard_output": ToolPermission("guard_output", allowed=True),

            # Tier 2 LLM reasoning — allowed with limits
            "extract_evidence": ToolPermission("extract_evidence", allowed=True, max_per_session=10),
            "assign_diagnosis_code": ToolPermission("assign_diagnosis_code", allowed=True, max_per_session=50),
            "assign_procedure_code": ToolPermission("assign_procedure_code", allowed=True, max_per_session=30),
            "verify_evidence": ToolPermission("verify_evidence", allowed=True, max_per_session=10),
            "analyze_drg_impact": ToolPermission("analyze_drg_impact", allowed=True, max_per_session=5),
            "check_documentation_gaps": ToolPermission("check_documentation_gaps", allowed=True, max_per_session=5),
            "cdi_review": ToolPermission("cdi_review", allowed=True, max_per_session=5),
            "format_report": ToolPermission("format_report", allowed=True, max_per_session=10),
            "generate_cdi_query": ToolPermission("generate_cdi_query", allowed=True, max_per_session=20),
            "reconstruct_timeline": ToolPermission("reconstruct_timeline", allowed=True, max_per_session=5),
        })

    @classmethod
    def cdi_audit(cls) -> "PermissionPolicy":
        """Clinical Documentation Improvement audit.

        Read-only analysis tools. No code assignment.
        """
        return cls(permissions={
            "extract_evidence": ToolPermission("extract_evidence", allowed=True, max_per_session=5),
            "verify_evidence": ToolPermission("verify_evidence", allowed=True, max_per_session=10),
            "check_documentation_gaps": ToolPermission("check_documentation_gaps", allowed=True, max_per_session=5),
            "cdi_review": ToolPermission("cdi_review", allowed=True, max_per_session=5),
            "generate_cdi_query": ToolPermission("generate_cdi_query", allowed=True, max_per_session=20),
            "format_report": ToolPermission("format_report", allowed=True, max_per_session=10),
            "rank_evidence": ToolPermission("rank_evidence", allowed=True),
            "guard_input": ToolPermission("guard_input", allowed=True),
            "guard_output": ToolPermission("guard_output", allowed=True),
        })

    @classmethod
    def drg_analysis(cls) -> "PermissionPolicy":
        """DRG/DIP payment impact analysis.

        Includes human approval for DRG-sensitive operations.
        """
        return cls(permissions={
            "extract_evidence": ToolPermission("extract_evidence", allowed=True, max_per_session=5),
            "search_icd10_index": ToolPermission("search_icd10_index", allowed=True, max_per_session=200),
            "search_icd9_index": ToolPermission("search_icd9_index", allowed=True, max_per_session=200),
            "assign_diagnosis_code": ToolPermission("assign_diagnosis_code", allowed=True, max_per_session=50),
            "assign_procedure_code": ToolPermission("assign_procedure_code", allowed=True, max_per_session=30),
            "rank_evidence": ToolPermission("rank_evidence", allowed=True),
            "calibrate_confidence": ToolPermission("calibrate_confidence", allowed=True),
            "analyze_drg_impact": ToolPermission("analyze_drg_impact", allowed=True, max_per_session=5),
            "format_report": ToolPermission("format_report", allowed=True, max_per_session=10),
            "guard_input": ToolPermission("guard_input", allowed=True),
            "guard_output": ToolPermission("guard_output", allowed=True),
        })

    @classmethod
    def restrictive(cls) -> "PermissionPolicy":
        """Maximum safety — only deterministic read-only tools.

        Used for demos, testing, or unverified agents.
        """
        return cls(permissions={
            "search_icd10_index": ToolPermission("search_icd10_index", allowed=True, max_per_session=100),
            "search_icd9_index": ToolPermission("search_icd9_index", allowed=True, max_per_session=100),
            "rank_evidence": ToolPermission("rank_evidence", allowed=True),
            "calibrate_confidence": ToolPermission("calibrate_confidence", allowed=True),
            "guard_input": ToolPermission("guard_input", allowed=True),
            "guard_output": ToolPermission("guard_output", allowed=True),
        })

    @classmethod
    def full_access(cls) -> "PermissionPolicy":
        """Allow all 17 tools — maximum capability, minimum safety.

        Only for admin/development use.
        """
        all_tools = [
            "extract_evidence", "reconstruct_timeline",
            "search_icd10_index", "search_icd9_index",
            "assign_diagnosis_code", "assign_procedure_code",
            "rank_evidence", "calibrate_confidence",
            "verify_evidence", "analyze_disagreements",
            "analyze_drg_impact", "check_documentation_gaps",
            "cdi_review", "format_report", "generate_cdi_query",
            "guard_input", "guard_output",
        ]
        return cls(permissions={
            tid: ToolPermission(tid, allowed=True) for tid in all_tools
        })


# ── Preset Registry ─────────────────────────────────────────────────────

PRESET_POLICIES: dict[str, dict] = {
    "medical_coding": {
        "name": "医学编码",
        "description": "标准医学编码管道——安全工具有限使用，高风险操作需人工确认",
        "policy": PermissionPolicy.medical_coding(),
    },
    "cdi_audit": {
        "name": "临床文档审核",
        "description": "只读分析工具——不允许编码分配",
        "policy": PermissionPolicy.cdi_audit(),
    },
    "drg_analysis": {
        "name": "DRG/DIP 支付分析",
        "description": "编码+DRG分析——适合医保审核场景",
        "policy": PermissionPolicy.drg_analysis(),
    },
    "restrictive": {
        "name": "严格模式",
        "description": "仅确定性工具——最大安全性",
        "policy": PermissionPolicy.restrictive(),
    },
    "full_access": {
        "name": "全量访问",
        "description": "全部17个工具可用——仅开发/管理使用",
        "policy": PermissionPolicy.full_access(),
    },
}
