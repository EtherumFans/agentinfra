"""ContextStatus lifecycle enum (SPEC §4.1, §5)."""

from __future__ import annotations

from enum import Enum


class ContextStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"