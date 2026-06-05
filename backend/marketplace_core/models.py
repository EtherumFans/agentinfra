"""Marketplace data models — shared across all marketplace deployments."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PackageRecord:
    """A published agent package record in the marketplace index."""

    id: str  # e.g. "compliance-guardrail-agent-1.0.0"
    name: str
    version: str
    description: str = ""
    category: str = "general"
    icon: str = "Bot"
    agent_type: str = "certified"  # "certified" | "community"
    publisher_name: str = ""
    publisher_email: str = ""
    expert_count: int = 0
    tool_count: int = 0
    downloads: int = 0
    published_at: str = ""
    integrity: dict = field(default_factory=dict)
    min_runtime_version: str = "1.0.0"

    @classmethod
    def from_dict(cls, data: dict) -> "PackageRecord":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            category=data.get("category", "general"),
            icon=data.get("icon", "Bot"),
            agent_type=data.get("agent_type", "certified"),
            publisher_name=data.get("publisher_name", ""),
            publisher_email=data.get("publisher_email", ""),
            expert_count=data.get("expert_count", 0),
            tool_count=data.get("tool_count", 0),
            downloads=data.get("downloads", 0),
            published_at=data.get("published_at", ""),
            integrity=data.get("integrity", {}),
            min_runtime_version=data.get("min_runtime_version", data.get("requirements", {}).get("min_runtime_version", "1.0.0")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "agent_type": self.agent_type,
            "publisher_name": self.publisher_name,
            "publisher_email": self.publisher_email,
            "expert_count": self.expert_count,
            "tool_count": self.tool_count,
            "downloads": self.downloads,
            "published_at": self.published_at,
            "min_runtime_version": self.min_runtime_version,
            "integrity": self.integrity,
        }

    def to_summary(self) -> dict[str, Any]:
        """API-friendly summary (subset of fields)."""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "agent_type": self.agent_type,
            "expert_count": self.expert_count,
            "tool_count": self.tool_count,
            "publisher_name": self.publisher_name,
            "downloads": self.downloads,
            "published_at": self.published_at,
        }


@dataclass
class PackageIndex:
    """In-memory representation of the marketplace index."""

    packages: dict[str, PackageRecord] = field(default_factory=dict)
    updated_at: str = ""

    def search(self, query: str = "", category: str = "", agent_type: str = "") -> list[PackageRecord]:
        results = list(self.packages.values())
        if query:
            q = query.lower()
            results = [p for p in results if q in p.name.lower() or q in p.description.lower()]
        if category:
            results = [p for p in results if p.category == category]
        if agent_type:
            results = [p for p in results if p.agent_type == agent_type]
        return results

    def sort(self, packages: list[PackageRecord], by: str = "newest") -> list[PackageRecord]:
        if by == "downloads":
            return sorted(packages, key=lambda p: p.downloads, reverse=True)
        if by == "name":
            return sorted(packages, key=lambda p: p.name)
        # newest
        return sorted(packages, key=lambda p: p.published_at, reverse=True)

    @property
    def categories(self) -> dict[str, int]:
        cats: dict[str, int] = {}
        for p in self.packages.values():
            cats[p.category] = cats.get(p.category, 0) + 1
        return cats

    @property
    def total_downloads(self) -> int:
        return sum(p.downloads for p in self.packages.values())
