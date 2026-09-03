"""Fail clearly if the pinned FastAPI/Starlette pair cannot construct an app."""

from __future__ import annotations

try:
    from fastapi import FastAPI

    FastAPI()
except Exception as exc:  # pragma: no cover - collection-time environment guard
    raise RuntimeError(
        "Pinned fastapi/starlette versions cannot construct FastAPI()"
    ) from exc
