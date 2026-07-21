"""Rate Limiting middleware — protects API from abuse.

Supports two backends:
- Memory: per-app-state sliding window (default for dev + tests)
- Redis: distributed sliding window with sorted sets (production)

Hermeticity contract (Phase A1A Gate 4R.2):

The per-IP request-count state lives on ``request.app.state.rate_limiter_counts``.
It does NOT live at module scope. Every FastAPI app instance gets its
own counter dict, and every pytest that builds a fresh ``app`` via
the test fixtures gets a fresh counter dict for free. A function-scope
autouse fixture in ``backend/tests/conftest.py`` additionally wipes
the dict before each test, so test order cannot pollute test outcomes.

A module-level fallback dict is kept ONLY for code paths that touch
the middleware before app-state initialization (e.g. direct calls to
``get_rate_limit_stats`` from CLI tooling that has no app). The
middleware itself NEVER reads the fallback when ``request.app.state``
is available.
"""
import logging
import time
import os
from collections import defaultdict
from typing import Dict, List
from fastapi import Request, HTTPException
from app.config import settings

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
_DEV_MODE = settings.DEBUG or settings.APP_ENV == "development"
LOGIN_LIMIT = 1000 if _DEV_MODE else max(5, settings.RATE_LIMIT_PER_MINUTE // 6)
GENERAL_LIMIT = 10000 if _DEV_MODE else settings.RATE_LIMIT_PER_MINUTE

# Module-level fallback ONLY for code paths without an active FastAPI app
# (CLI tools, scripts). The middleware itself never reads this when
# request.app.state is available.
_fallback_counts: Dict[str, List[float]] = defaultdict(list)
_fallback_redis = None

_STATE_ATTR = "rate_limiter_counts"
_STATE_REDIS_ATTR = "rate_limiter_redis"


def _get_counts(request: Request) -> Dict[str, List[float]]:
    """Return the per-app-state counter dict, creating it on first access.

    Tests get a fresh dict automatically because the ``app`` fixture in
    conftest.py builds a new FastAPI instance per test.
    """
    state = getattr(request, "app", None)
    if state is None or not hasattr(state, "state"):
        return _fallback_counts
    if not hasattr(state.state, _STATE_ATTR):
        setattr(state.state, _STATE_ATTR, defaultdict(list))
    return getattr(state.state, _STATE_ATTR)


def _get_redis_for_request(request: Request):
    """Lazy Redis backend, bound to app.state so tests don't share it."""
    state = getattr(request, "app", None)
    if state is None or not hasattr(state, "state"):
        return _fallback_redis
    if not hasattr(state.state, _STATE_REDIS_ATTR):
        setattr(state.state, _STATE_REDIS_ATTR, _init_redis_or_false())
    redis_or_false = getattr(state.state, _STATE_REDIS_ATTR)
    return redis_or_false if redis_or_false else None


def _init_redis_or_false():
    """Lazy Redis init. Returns the client, or False if disabled / unavailable."""
    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        return False
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(redis_url, decode_responses=True)
        logger.info(f"Rate limiter: Redis backend ({redis_url})")
        return client
    except ImportError:
        logger.warning("redis not installed — using memory backend")
        return False
    except Exception as e:
        logger.warning(f"Redis connection failed ({e}) — using memory backend")
        return False


def reset_rate_limiter(request: Request) -> None:
    """Test-only: wipe per-IP counters bound to this request's app.

    Called by the autouse fixture in ``backend/tests/conftest.py``.
    Production code MUST NOT call this — it would defeat the rate limiter.
    """
    state = getattr(request, "app", None)
    if state is None or not hasattr(state, "state"):
        _fallback_counts.clear()
        return
    if hasattr(state.state, _STATE_ATTR):
        getattr(state.state, _STATE_ATTR).clear()
    if hasattr(state.state, _STATE_REDIS_ATTR):
        try:
            client = getattr(state.state, _STATE_REDIS_ATTR)
            if client:
                # Best-effort flush of this app's keys. Tests run without
                # Redis in practice, so this branch is rarely taken.
                import asyncio
                asyncio.get_event_loop().create_task(client.flushdb())
        except Exception:
            pass
        setattr(state.state, _STATE_REDIS_ATTR, False)


async def rate_limit_middleware(request: Request, call_next):
    """Sliding-window rate limiter. Uses Redis if available, else memory."""
    if request.url.path in ("/api/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"

    # Login endpoint: stricter limit
    limit = LOGIN_LIMIT if request.url.path == "/api/auth/login" else GENERAL_LIMIT

    r = _get_redis_for_request(request)
    if r:
        # Redis sliding window via sorted set
        now_ms = int(time.time() * 1000)
        key = f"ratelimit:{client_ip}"
        window_ms = WINDOW_SECONDS * 1000
        async with r.pipeline() as pipe:
            pipe.zremrangebyscore(key, 0, now_ms - window_ms)
            pipe.zcard(key)
            pipe.zadd(key, {str(now_ms): now_ms})
            pipe.expire(key, WINDOW_SECONDS * 2)
            _, count, _, _ = await pipe.execute()
        if count >= limit:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({limit}/min).")
    else:
        # Memory backend — per-app-state
        counts = _get_counts(request)
        now = time.time()
        counts[client_ip] = [t for t in counts[client_ip] if now - t < WINDOW_SECONDS]
        if len(counts[client_ip]) >= limit:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({limit}/min).")
        counts[client_ip].append(now)

    return await call_next(request)


def get_rate_limit_stats() -> dict:
    return {"rate_limit_per_min": settings.RATE_LIMIT_PER_MINUTE, "window_seconds": WINDOW_SECONDS, "login_limit": LOGIN_LIMIT}
