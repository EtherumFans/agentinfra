"""Bounded per-request overrides for the synchronous iCoDer client."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event
from typing import Mapping, Optional


@dataclass(frozen=True)
class RequestOptions:
    timeout_in_seconds: Optional[float] = None
    max_retries: Optional[int] = None
    cancel_event: Optional[Event] = None
    headers: Mapping[str, str] = field(default_factory=dict)
    query_params: Mapping[str, str] = field(default_factory=dict)


class iCoDerRequestCancelledError(TimeoutError):
    """A caller-owned cancellation event stopped a request or retry delay."""

