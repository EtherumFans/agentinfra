"""RuntimeAgentRegistry — unified persistent store for installed agents.

Used by: Marketplace install, PlatformRuntime, CLI install.
Backend: filesystem JSON (default), swappable to DB later.

This is the SINGLE source of truth for "which agents are installed."
PlatformRuntime and the main platform API both read/write through this.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from .errors import AgentNotFoundError, InstallError

logger = logging.getLogger(__name__)

# Default storage location
DEFAULT_REGISTRY_DIR = Path(".icoder")
DEFAULT_REGISTRY_FILE = "agent_registry.json"
DEFAULT_LOCK_FILE = "agent_registry.lock"


class InstalledAgentRecord:
    """A record of an installed agent in the registry."""

    __slots__ = (
        "agent_id", "name", "version", "description", "category", "icon",
        "agent_type", "system_prompt", "expert_ids", "experts", "tools",
        "permissions", "publisher_name", "publisher_email",
        "min_runtime_version", "llm_capabilities", "integrity",
        "pack_data", "status", "installed_at",
    )

    def __init__(self, **kwargs):
        for k in self.__slots__:
            setattr(self, k, kwargs.get(k))

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}

    def to_summary(self) -> dict[str, Any]:
        """API-friendly summary without full pack_data."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "agent_type": self.agent_type,
            "expert_count": len(self.experts or []),
            "tool_count": len(self.tools or []),
            "publisher_name": self.publisher_name,
            "status": self.status,
            "installed_at": self.installed_at,
            "min_runtime_version": self.min_runtime_version,
        }


class RuntimeAgentRegistry:
    """Persistent registry of installed agents.

    Thread-safe file-based storage. Swappable backend via adapter pattern.

    Usage:
        registry = RuntimeAgentRegistry(storage_dir=".icoder")
        registry.install(pack, publisher="iCoDer")
        agents = registry.list_all()
        agent = registry.get("my-agent-1.0.0")
    """

    def __init__(self, storage_dir: str | Path = ""):
        self._dir = Path(storage_dir) if storage_dir else DEFAULT_REGISTRY_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / DEFAULT_REGISTRY_FILE
        self._lock_file = self._dir / DEFAULT_LOCK_FILE
        # TD-005 fix: thread lock for in-process safety + file lock for
        # cross-process safety. Multi-worker uvicorn deployments can now
        # safely share the registry JSON without corrupting it.
        self._lock = threading.Lock()
        self._file_lock = FileLock(str(self._lock_file), timeout=10)
        self._records: dict[str, InstalledAgentRecord] = {}
        self._last_exception: Exception | None = None
        self._load()

    @contextmanager
    def _dual_lock(self, *, write: bool = True):
        """Acquire thread lock + file lock.

        For reads (write=False), only the thread lock is taken — reads are
        tolerant of brief cross-process races (we'll see either the old or
        new JSON atomically, never a partial write because _persist uses
        tmp→rename).

        For writes (write=True), both locks are taken to serialize
        mutations across processes.
        """
        if write:
            try:
                with self._file_lock:
                    with self._lock:
                        yield
            except Timeout as e:
                self._last_exception = e
                logger.error("Registry file lock timeout: %s", e)
                raise
            except Exception as e:
                self._last_exception = e
                logger.error("Registry file lock error: %s", e)
                raise
        else:
            with self._lock:
                yield

    # ── CRUD ──

    def install(self, pack: dict, publisher_name: str = "", publisher_email: str = "") -> InstalledAgentRecord:
        """Install an agent pack into the registry. Validates via AgentPackageV1
        for v1.1 packs; v1.2 packs (validated by BuiltinAgentPackProvider) are
        passed through with values read directly from the pack dict.
        """
        from .agent_pack_v1 import AgentPackageV1

        is_v12 = pack.get("format_version", "1.1") != "1.1"
        if is_v12:
            manifest = pack.get("manifest", {})
            name = manifest.get("name", "")
            version = manifest.get("version", "1.0.0")
            agent_id = f"{name.lower().replace(' ', '-')}-{version}"
            # v1.2 packs use `expert_id` (Phase D convention) — Loader is the
            # canonical reader, but keep the registry tolerant.
            expert_ids = [
                e.get("id") or e.get("expert_id") or ""
                for e in pack.get("experts", [])
            ]
            record = InstalledAgentRecord(
                agent_id=agent_id,
                name=name,
                version=version,
                description=manifest.get("description", ""),
                category=manifest.get("category", "general"),
                icon=manifest.get("icon", "Bot"),
                agent_type=pack.get("agent_type", "certified"),
                system_prompt=pack.get("system_prompt", ""),
                expert_ids=expert_ids,
                experts=pack.get("experts", []),
                tools=pack.get("tools", []),
                permissions=pack.get("permissions", {}),
                publisher_name=publisher_name or pack.get("publisher_name", ""),
                publisher_email=publisher_email or pack.get("publisher_email", ""),
                min_runtime_version=pack.get("requirements", {}).get("min_runtime_version", "1.0.0"),
                llm_capabilities=pack.get("llm_capabilities", {}),
                integrity=pack.get("integrity", {}),
                pack_data=pack,
                status="installed",
                installed_at=datetime.now(timezone.utc).isoformat(),
            )
        else:
            pkg = AgentPackageV1.from_dict(pack)
            agent_id = f"{pkg.name.lower().replace(' ', '-')}-{pkg.version}"

            record = InstalledAgentRecord(
                agent_id=agent_id,
                name=pkg.name,
                version=pkg.version,
                description=pkg.description,
                category=pkg.category,
                icon=pkg.icon,
                agent_type=pkg.agent_type,
                system_prompt=pkg.system_prompt,
                expert_ids=[e.get("id") for e in pkg.experts],
                experts=pkg.experts,
                tools=pkg.tools,
                permissions=pkg.permissions,
                publisher_name=publisher_name or pkg.publisher_name,
                publisher_email=publisher_email or pkg.publisher_email,
                min_runtime_version=pkg.requirements.get("min_runtime_version", "1.0.0"),
                llm_capabilities=pkg.llm_capabilities,
                integrity=pkg.integrity,
                pack_data=pack,
                status="installed",
                installed_at=datetime.now(timezone.utc).isoformat(),
            )

        with self._dual_lock():
            self._records[agent_id] = record
            self._persist()

        logger.info(f"Agent installed: {agent_id}")
        return record

    def get(self, agent_id: str) -> InstalledAgentRecord:
        """Get an installed agent by ID. Raises AgentNotFoundError if missing."""
        with self._dual_lock(write=False):
            record = self._records.get(agent_id)
        if not record:
            # Try case-insensitive match
            with self._dual_lock(write=False):
                for rid, rec in self._records.items():
                    if rid.lower() == agent_id.lower():
                        return rec
            raise AgentNotFoundError(agent_id)
        return record

    def find(self, query: str) -> InstalledAgentRecord | None:
        """Find an agent by ID, partial ID, or name. Returns None if not found."""
        try:
            return self.get(query)
        except AgentNotFoundError:
            pass
        q = query.lower()
        with self._dual_lock(write=False):
            for rec in self._records.values():
                if q in rec.agent_id.lower() or q in rec.name.lower():
                    return rec
        return None

    def list_all(self, agent_type: str = "") -> list[InstalledAgentRecord]:
        """List all installed agents, optionally filtered by type."""
        with self._dual_lock(write=False):
            records = list(self._records.values())
        if agent_type:
            records = [r for r in records if r.agent_type == agent_type]
        return sorted(records, key=lambda r: r.installed_at or "", reverse=True)

    def remove(self, agent_id: str):
        """Remove an installed agent."""
        with self._dual_lock():
            if agent_id not in self._records:
                raise AgentNotFoundError(agent_id)
            del self._records[agent_id]
            self._persist()
        logger.info(f"Agent removed: {agent_id}")

    @property
    def count(self) -> int:
        with self._dual_lock(write=False):
            return len(self._records)

    # ── Persistence ──

    SCHEMA_VERSION = "1.0"
    _BAK_SUFFIX = ".bak"

    @property
    def registry_path(self) -> str:
        return str(self._file.resolve())

    def _load(self):
        """Load registry from disk. Attempts recovery from .bak if main file is corrupted."""
        loaded = self._try_load(self._file)
        if loaded is not None:
            return

        # Try backup recovery
        bak = self._file.with_suffix(self._file.suffix + self._BAK_SUFFIX)
        if bak.exists():
            logger.warning(f"Registry corrupted, attempting recovery from {bak}")
            loaded = self._try_load(bak)
            if loaded is not None:
                self._records = loaded
                self._persist()  # Restore main file from backup
                logger.info(f"Registry recovered from backup: {len(loaded)} agent(s)")
                return

        logger.warning("Registry file corrupted and no backup available, starting fresh.")
        self._records = {}

    def _try_load(self, path: Path) -> dict | None:
        """Try to load registry from a path. Returns records dict or None on failure."""
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            schema_ver = data.get("schema_version", "0")
            if schema_ver != self.SCHEMA_VERSION:
                logger.info(f"Registry schema version {schema_ver}, current is {self.SCHEMA_VERSION}")
            records = {}
            for agent_id, rec_data in data.get("agents", {}).items():
                records[agent_id] = InstalledAgentRecord(**rec_data)
            return records
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"Failed to load registry from {path}: {e}")
            return None
        except OSError as e:
            logger.error(f"OS error reading registry {path}: {e}")
            return None

    def _persist(self):
        """Atomic write with fsync + backup rotation."""
        data = {
            "schema_version": self.SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "agents": {aid: rec.to_dict() for aid, rec in self._records.items()},
        }
        payload = json.dumps(data, ensure_ascii=False, indent=2)

        # Create backup of current file before overwriting
        if self._file.exists():
            bak = self._file.with_suffix(self._file.suffix + self._BAK_SUFFIX)
            try:
                bak.write_text(self._file.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass  # Best-effort backup

        # Atomic write: tmp → fsync → rename
        tmp = self._file.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            if tmp.exists():
                tmp.unlink()
            raise

        tmp.replace(self._file)

    # ── Multi-worker warning ──

    def check_worker_safety(self) -> dict:
        """Check if the registry is safe for the current deployment.

        TD-005 fix: now reports cross-process file lock status. The
        previous warning (threading.Lock only, no inter-process lock) is
        resolved — filelock protects mutations across workers.
        """
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        issues = []
        # File lock is now in place — multi-worker is safe.
        # Surface the cpu_count for observability but don't warn.
        lock_status = {
            "type": "threading.Lock + filelock.FileLock",
            "file_lock_path": str(self._lock_file),
            "file_lock_timeout_seconds": 10,
            "cross_process_safe": True,
        }
        # Surface any last-seen exception (doctor / runtime_status can
        # read this to expose hidden failures).
        last_exc = self._last_exception
        if last_exc is not None:
            issues.append({
                "level": "warning",
                "message": (
                    f"Registry last exception: {type(last_exc).__name__}: "
                    f"{last_exc}. Check logs for context."
                ),
            })
        return {
            "safe": len(issues) == 0,
            "storage_path": self.registry_path,
            "schema_version": self.SCHEMA_VERSION,
            "lock_type": lock_status["type"],
            "lock_status": lock_status,
            "cpu_count": cpu_count,
            "issues": issues,
            "last_exception": (
                f"{type(last_exc).__name__}: {last_exc}"
                if last_exc is not None
                else None
            ),
        }


# Global singleton — initialized by PlatformRuntime or main.py
_global_registry: RuntimeAgentRegistry | None = None


def get_registry(storage_dir: str | Path = "") -> RuntimeAgentRegistry:
    """Get or create the global RuntimeAgentRegistry singleton."""
    global _global_registry
    if _global_registry is None:
        _global_registry = RuntimeAgentRegistry(storage_dir)
    return _global_registry


def init_registry(storage_dir: str | Path) -> RuntimeAgentRegistry:
    """Initialize the global registry with a specific storage directory."""
    global _global_registry
    _global_registry = RuntimeAgentRegistry(storage_dir)
    return _global_registry
