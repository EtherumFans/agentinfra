"""Typed, PHI-safe SDK exceptions."""

from __future__ import annotations

import re
from typing import Any, Optional

import httpx


_SAFE_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SAFE_REASON = re.compile(r"^[A-Z0-9_.:-]{1,128}$")


class iCoDerClientError(RuntimeError):
    """Base class for SDK failures."""


class iCoDerAPIError(iCoDerClientError):
    """Sanitized HTTP API failure without request/response retention."""

    def __init__(
        self,
        status_code: int,
        request_id: Optional[str] = None,
        details: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        super().__init__(f"iCoDer API request failed with HTTP {status_code}")
        self.status_code = status_code
        self.status = status_code
        self.request_id = request_id
        self.details = details or []
        self.body = {"details": self.details} if self.details else None
        self.retryable = status_code in {408, 429} or status_code >= 500


class BadRequestError(iCoDerAPIError):
    pass


class UnauthorizedError(iCoDerAPIError):
    pass


class ForbiddenError(iCoDerAPIError):
    pass


class NotFoundError(iCoDerAPIError):
    pass


class ConflictError(iCoDerAPIError):
    pass


class UnprocessableEntityError(iCoDerAPIError):
    pass


class InternalServerError(iCoDerAPIError):
    pass


class BadGatewayError(iCoDerAPIError):
    pass


class GatewayTimeoutError(iCoDerAPIError):
    pass


_STATUS_ERRORS: dict[int, type[iCoDerAPIError]] = {
    400: BadRequestError,
    401: UnauthorizedError,
    403: ForbiddenError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    500: InternalServerError,
    502: BadGatewayError,
    504: GatewayTimeoutError,
}


def _safe_detail(value: Any) -> Optional[dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {}
    raw_code = value.get("code", value.get("error_code", value.get("a2a_error_code")))
    if isinstance(raw_code, int) or (
        isinstance(raw_code, str) and _SAFE_CODE.fullmatch(raw_code)
    ):
        result["code"] = raw_code
    raw_reason = value.get("reason")
    if isinstance(raw_reason, str) and _SAFE_REASON.fullmatch(raw_reason):
        result["reason"] = raw_reason
    raw_field = value.get("field")
    if isinstance(raw_field, str) and _SAFE_CODE.fullmatch(raw_field):
        result["field"] = raw_field
    raw_type = value.get("type")
    if isinstance(raw_type, str) and _SAFE_CODE.fullmatch(raw_type):
        result["type"] = raw_type
    raw_location = value.get("loc", value.get("location"))
    if isinstance(raw_location, list) and len(raw_location) <= 16 and all(
        isinstance(item, int)
        or (isinstance(item, str) and len(item) <= 64 and _SAFE_CODE.fullmatch(item))
        for item in raw_location
    ):
        result["location"] = list(raw_location)
    return result or None


def _sanitized_details(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    candidates: list[Any] = [payload]
    error = payload.get("error")
    if isinstance(error, dict):
        candidates.append(error)
        data = error.get("data")
        if isinstance(data, dict):
            candidates.append(data)
        elif isinstance(data, list):
            candidates.extend(data[:32])
        details = error.get("details")
        if isinstance(details, list):
            candidates.extend(details[:32])
    detail = payload.get("detail")
    if isinstance(detail, list):
        candidates.extend(detail[:32])
    return [item for value in candidates if (item := _safe_detail(value)) is not None]


def api_error_from_response(response: httpx.Response) -> iCoDerAPIError:
    try:
        payload = response.json()
    except Exception:
        payload = None
    request_id = response.headers.get("x-request-id") or response.headers.get(
        "x-correlation-id"
    )
    if request_id and len(request_id) > 256:
        request_id = None
    error_type = _STATUS_ERRORS.get(response.status_code, iCoDerAPIError)
    return error_type(response.status_code, request_id, _sanitized_details(payload))
