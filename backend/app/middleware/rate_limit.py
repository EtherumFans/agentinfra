"""Rate Limiting middleware — protects API from abuse.

iCoDer equivalent: production rate limiting for API endpoints.
Difficulty: SMALL — standard middleware pattern with configurable limits.
"""
import time
from collections import defaultdict
from fastapi import Request, HTTPException

# Default: 100 requests per minute per IP
RATE_LIMIT = 100
WINDOW_SECONDS = 60

# Per-IP request tracking
_request_counts: dict[str, list[float]] = defaultdict(list)


async def rate_limit_middleware(request: Request, call_next):
    """Simple sliding-window rate limiter middleware."""
    # Skip health check and static files
    if request.url.path in ("/api/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    # Clean old entries
    _request_counts[client_ip] = [t for t in _request_counts[client_ip] if now - t < WINDOW_SECONDS]

    # Check limit
    if len(_request_counts[client_ip]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    _request_counts[client_ip].append(now)
    return await call_next(request)


def get_rate_limit_stats() -> dict:
    """Get current rate limit statistics."""
    now = time.time()
    stats = {}
    for ip, times in _request_counts.items():
        recent = [t for t in times if now - t < WINDOW_SECONDS]
        if recent:
            stats[ip] = len(recent)
    return {"rate_limit": RATE_LIMIT, "window_seconds": WINDOW_SECONDS, "clients": stats}
