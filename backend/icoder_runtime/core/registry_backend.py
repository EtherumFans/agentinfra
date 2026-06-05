"""RegistryBackend — abstract storage interface for RuntimeAgentRegistry.

Current implementation: FileRegistryBackend (JSON file).
Reserved: SQLiteRegistryBackend, PostgresRegistryBackend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class RegistryBackend(ABC):
    """Abstract storage backend for agent registry data."""

    backend_name: str = "abstract"

    @abstractmethod
    def load(self) -> dict[str, Any] | None:
        """Load registry data. Returns None if no data exists."""
        ...

    @abstractmethod
    def save(self, data: dict[str, Any]):
        """Save registry data atomically."""
        ...

    @abstractmethod
    def health_check(self) -> dict:
        """Return backend health status."""
        ...


class FileRegistryBackend(RegistryBackend):
    """JSON file backend — current production backend."""

    backend_name = "file"

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def load(self) -> dict[str, Any] | None:
        if not self._path.exists():
            return None
        import json
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save(self, data: dict[str, Any]):
        import json
        import os
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self._path)

    def health_check(self) -> dict:
        return {
            "backend": self.backend_name,
            "path": str(self._path.resolve()),
            "exists": self._path.exists(),
            "status": "healthy",
        }


class SQLiteRegistryBackend(RegistryBackend):
    """SQLite backend — production-ready, thread-safe via WAL mode."""

    backend_name = "sqlite"

    def __init__(self, path: str = ""):
        self._path = path or ".icoder/registry.db"

    def _get_conn(self):
        import sqlite3
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("CREATE TABLE IF NOT EXISTS registry (agent_id TEXT PRIMARY KEY, data TEXT, updated_at TEXT)")
        return conn

    def load(self) -> dict[str, Any] | None:
        try:
            conn = self._get_conn()
            rows = conn.execute("SELECT agent_id, data FROM registry").fetchall()
            conn.close()
            agents = {}
            for aid, data_json in rows:
                import json
                agents[aid] = json.loads(data_json)
            return {"agents": agents, "schema_version": "1.0"}
        except Exception:
            return None

    def save(self, data: dict[str, Any]):
        import json
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM registry")
            agents = data.get("agents", {})
            for aid, rec in agents.items():
                conn.execute(
                    "INSERT INTO registry (agent_id, data, updated_at) VALUES (?, ?, ?)",
                    (aid, json.dumps(rec, ensure_ascii=False, default=str), now),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def health_check(self) -> dict:
        import os
        return {
            "backend": self.backend_name,
            "path": self._path,
            "exists": os.path.exists(self._path),
            "status": "healthy" if os.path.exists(self._path) else "initialized",
        }


class PostgresRegistryBackend(RegistryBackend):
    """PostgreSQL backend — reserved for future implementation."""

    backend_name = "postgres"

    def __init__(self, dsn: str = ""):
        self._dsn = dsn
        raise NotImplementedError("PostgresRegistryBackend is not yet implemented. Use FileRegistryBackend.")

    def load(self) -> dict[str, Any] | None:
        raise NotImplementedError("PostgresRegistryBackend is not yet implemented.")

    def save(self, data: dict[str, Any]):
        raise NotImplementedError("PostgresRegistryBackend is not yet implemented.")

    def health_check(self) -> dict:
        return {"backend": self.backend_name, "status": "not_implemented"}


def create_backend(backend_type: str = "file", **kwargs) -> RegistryBackend:
    """Factory for RegistryBackend instances."""
    if backend_type == "file":
        return FileRegistryBackend(kwargs.get("path", ".icoder/registry.json"))
    if backend_type == "sqlite":
        return SQLiteRegistryBackend(kwargs.get("sqlite_path", ""))
    if backend_type == "postgres":
        return PostgresRegistryBackend(kwargs.get("postgres_dsn", ""))
    raise ValueError(f"Unknown registry backend: {backend_type}")
