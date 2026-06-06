"""Rate Limiting middleware — protects API from abuse.

Supports two backends:
- Memory: single-process sliding window (default for dev)
- Redis: distributed sliding window with sorted sets (production)
"""
import logging
import time
import os
from collections import defaultdict
from fastapi import Request, HTTPException
from app.config import settings

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
_DEV_MODE = settings.DEBUG or settings.APP_ENV == "development"
LOGIN_LIMIT = 1000 if _DEV_MODE else max(5, settings.RATE_LIMIT_PER_MINUTE // 6)
GENERAL_LIMIT = 10000 if _DEV_MODE else settings.RATE_LIMIT_PER_MINUTE

# Per-IP request tracking (memory backend)
_request_counts: dict[str, list[float]] = defaultdict(list)

# Redis backend (lazy init)
_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            try:
                import redis.asyncio as aioredis
                _redis = aioredis.from_url(redis_url, decode_responses=True)
                logger.info(f"Rate limiter: Redis backend ({redis_url})")
            except ImportError:
                logger.warning("redis not installed — using memory backend")
                _redis = False
            except Exception as e:
                logger.warning(f"Redis connection failed ({e}) — using memory backend")
                _redis = False
        else:
            _redis = False
    return _redis if _redis else None


async def rate_limit_middleware(request: Request, call_next):
    """Sliding-window rate limiter. Uses Redis if available, else memory."""
    if request.url.path in ("/api/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.client.host if request.client else "unknown"

    # Login endpoint: stricter limit
    limit = LOGIN_LIMIT if request.url.path == "/api/auth/login" else GENERAL_LIMIT

    r = _get_redis()
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
        # Memory backend
        now = time.time()
        _request_counts[client_ip] = [t for t in _request_counts[client_ip] if now - t < WINDOW_SECONDS]
        if len(_request_counts[client_ip]) >= limit:
            raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({limit}/min).")
        _request_counts[client_ip].append(now)

    return await call_next(request)


def get_rate_limit_stats() -> dict:
    return {"rate_limit_per_min": settings.RATE_LIMIT_PER_MINUTE, "window_seconds": WINDOW_SECONDS, "login_limit": LOGIN_LIMIT}
