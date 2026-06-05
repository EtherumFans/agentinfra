"""Structured logging middleware — request logs + Prometheus metrics."""
import logging
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("icoder.access")

# Prometheus counters (in-process, export via /api/metrics)
_metrics: dict = {
    "requests": {},       # {method:path:status → count}
    "agent_runs": {},     # {agent_ref:status → count}
    "llm_calls": 0,
    "active_sessions": 0,
}

SENSITIVE_FIELDS = {"password", "token", "secret", "authorization", "api_key", "credential"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, duration, user."""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)

        path = request.url.path
        method = request.method
        status = response.status_code

        # Update metrics
        key = f"{method}:{path}:{status}"
        _metrics["requests"][key] = _metrics["requests"].get(key, 0) + 1

        # Structured log (skip health/static)
        if not path.startswith("/api/health"):
            logger.info(
                f"{method} {path} → {status} ({duration_ms}ms)",
                extra={"method": method, "path": path, "status": status, "duration_ms": duration_ms},
            )

        return response


def record_agent_run(agent_ref: str, status: str):
    """Record an agent run in metrics."""
    key = f"{agent_ref}:{status}"
    _metrics["agent_runs"][key] = _metrics["agent_runs"].get(key, 0) + 1


def record_llm_call():
    _metrics["llm_calls"] += 1


def get_metrics() -> dict:
    """Return current metrics snapshot."""
    return {
        "requests_total": sum(_metrics["requests"].values()),
        "requests_by_endpoint": dict(list(_metrics["requests"].items())[:20]),
        "agent_runs_total": sum(_metrics["agent_runs"].values()),
        "agent_runs": dict(list(_metrics["agent_runs"].items())[:20]),
        "llm_calls_total": _metrics["llm_calls"],
        "active_sessions": _metrics["active_sessions"],
    }
