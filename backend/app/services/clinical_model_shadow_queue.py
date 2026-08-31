"""PHI-free wake-up adapters for the durable clinical shadow job queue.

The relational job table is always authoritative.  Adapters only reduce poll
latency and are intentionally allowed to lose or duplicate notifications: a
worker still claims through the database fence before doing any work.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit


_JOB_ID = re.compile(r"^[0-9a-fA-F-]{36}$")
_CHANNEL = "icoder:clinical-shadow-job:wakeup:v1"


class ShadowQueueConfigurationError(RuntimeError):
    pass


class ShadowQueueAdapter(Protocol):
    name: str

    async def notify(self, job_id: str) -> bool: ...

    async def wait(self, timeout_seconds: float) -> bool: ...

    async def close(self) -> None: ...


def _validated_job_id(job_id: str) -> str:
    value = job_id.strip()
    if _JOB_ID.fullmatch(value) is None:
        raise ValueError("SHADOW_QUEUE_JOB_ID_INVALID")
    return value


@dataclass(slots=True)
class DatabasePollingShadowQueue:
    """Portable fallback; durable work is discovered by indexed DB polling."""

    name: str = "database"

    async def notify(self, job_id: str) -> bool:
        _validated_job_id(job_id)
        return True

    async def wait(self, timeout_seconds: float) -> bool:
        await asyncio.sleep(max(0.05, min(float(timeout_seconds), 60.0)))
        return False

    async def close(self) -> None:
        return None


class RedisSignalShadowQueue:
    """Redis list wake-up signal with database polling as durable fallback."""

    name = "redis_signal"

    def __init__(self, redis_url: str, *, allow_insecure: bool = False) -> None:
        parsed = urlsplit(redis_url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ShadowQueueConfigurationError("SHADOW_QUEUE_REDIS_URL_INVALID")
        if parsed.scheme != "rediss" and not allow_insecure:
            raise ShadowQueueConfigurationError("SHADOW_QUEUE_REDIS_TLS_REQUIRED")
        try:
            import redis.asyncio as redis_async
        except ImportError as exc:  # pragma: no cover - deployment dependency gate
            raise ShadowQueueConfigurationError(
                "SHADOW_QUEUE_REDIS_DEPENDENCY_MISSING"
            ) from exc
        self._client = redis_async.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
            health_check_interval=30,
        )

    async def notify(self, job_id: str) -> bool:
        value = _validated_job_id(job_id)
        payload = json.dumps(
            {"schema_version": "icoder.shadow-queue-signal/v1", "job_id": value},
            separators=(",", ":"),
            sort_keys=True,
        )
        await self._client.lpush(_CHANNEL, payload)
        await self._client.ltrim(_CHANNEL, 0, 9999)
        return True

    async def wait(self, timeout_seconds: float) -> bool:
        timeout = max(1, min(int(timeout_seconds), 60))
        item = await self._client.brpop(_CHANNEL, timeout=timeout)
        if item is None:
            return False
        try:
            payload = json.loads(item[1])
            _validated_job_id(str(payload.get("job_id", "")))
            return payload.get("schema_version") == "icoder.shadow-queue-signal/v1"
        except (TypeError, ValueError, json.JSONDecodeError):
            return False

    async def close(self) -> None:
        await self._client.aclose()


def build_shadow_queue_adapter(
    *,
    backend: str,
    redis_url: str = "",
    allow_insecure_redis: bool = False,
) -> ShadowQueueAdapter:
    selected = backend.strip().casefold()
    if selected == "database":
        return DatabasePollingShadowQueue()
    if selected == "redis_signal":
        if not redis_url.strip():
            raise ShadowQueueConfigurationError("SHADOW_QUEUE_REDIS_URL_REQUIRED")
        return RedisSignalShadowQueue(
            redis_url.strip(), allow_insecure=allow_insecure_redis,
        )
    raise ShadowQueueConfigurationError("SHADOW_QUEUE_BACKEND_INVALID")


__all__ = [
    "DatabasePollingShadowQueue",
    "RedisSignalShadowQueue",
    "ShadowQueueAdapter",
    "ShadowQueueConfigurationError",
    "build_shadow_queue_adapter",
]
