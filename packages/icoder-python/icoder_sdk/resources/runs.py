"""Unified Agent Run and launch-candidate Agent Hub resources."""

from __future__ import annotations

from collections.abc import Mapping
import json
import random
import threading
import time
from typing import Any, Iterator, Optional
from urllib.parse import quote

from ..client import iCoDerClient
from ..request_options import RequestOptions, iCoDerRequestCancelledError
from ..types import (
    AgentHubResponse,
    AgentHubTenantReadinessResponse,
    validate_agent_hub_response,
    validate_agent_hub_tenant_readiness_response,
)


class RunEventStreamError(RuntimeError):
    """Sanitized run-event transport error that never retains the signed URL."""

    def __init__(
        self,
        http_status: Optional[int] = None,
        *,
        retryable: bool = False,
        error_code: Optional[str] = None,
    ) -> None:
        suffix = f" (HTTP {http_status})" if http_status else ""
        super().__init__(f"iCoDer run event stream failed{suffix}")
        self.http_status = http_status
        self.retryable = retryable
        self.error_code = error_code


class RunEventRetentionError(RunEventStreamError):
    """A trace or resume cursor was removed by the server retention policy."""

    def __init__(
        self,
        *,
        error_code: str,
        retention_days: Optional[int] = None,
    ) -> None:
        super().__init__(410, retryable=False, error_code=error_code)
        self.retention_days = retention_days


class RunsResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def run(
        self,
        agent_id: str,
        body: dict[str, Any],
        *,
        idempotency_key: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        response = self._client.post(
            f"/api/v1/agents/{quote(agent_id, safe='')}/run",
            json=body,
            headers=headers,
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def run_text(
        self,
        agent_id: str,
        text: str,
        *,
        runtime_mode: Optional[str] = None,
        purpose_of_use: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        include_trace: bool = True,
        include_evidence: bool = True,
        documents: Optional[list[dict[str, Any]]] = None,
        upstream_results: Optional[list[dict[str, Any]]] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        return self.run(
            agent_id,
            {
                "input": {
                    "text": text,
                    "extra": {},
                    "documents": list(documents or []),
                    "upstream_results": list(upstream_results or []),
                },
                "runtime_mode": runtime_mode,
                "purpose_of_use": purpose_of_use,
                "include_trace": include_trace,
                "include_evidence": include_evidence,
            },
            idempotency_key=idempotency_key,
            request_options=request_options,
        )

    def get(
        self,
        run_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Return the authoritative lifecycle state for a run."""
        response = self._client.get(
            f"/api/v1/runs/{quote(run_id, safe='')}",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def cancel(
        self,
        run_id: str,
        reason: str = "",
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Request cancellation; callers must inspect the returned outcome."""
        response = self._client.post(
            f"/api/v1/runs/{quote(run_id, safe='')}/cancel",
            json={"reason": reason},
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def renew_trace_token(
        self,
        run_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Renew a run-bound trace authorization with the bearer identity."""
        response = self._client.post(
            f"/api/v1/runs/{quote(run_id, safe='')}/trace-token",
            request_options=request_options,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("trace_token"):
            raise RunEventStreamError()
        return payload

    def stream_events(
        self,
        run_id: str,
        trace_token: str,
        *,
        last_event_id: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield signed, PHI-safe run lifecycle event envelopes.

        ``trace_token`` is the ``token`` query value from the Agent Run
        ``trace_url``. Supplying it separately prevents the SDK from fetching
        an arbitrary URL returned by a server.
        """
        if not trace_token:
            raise ValueError("trace_token is required")
        if last_event_id and (
            len(last_event_id) > 128
            or any(char in last_event_id for char in ("\r", "\n", "\x00"))
        ):
            raise ValueError("last_event_id is malformed")
        path = f"/api/v1/runs/{quote(run_id, safe='')}/events"
        headers = {"Accept": "text/event-stream"}
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id
        headers, params, timeout, cancel_event = self._stream_request_options(
            request_options,
            domain_headers=headers,
            domain_params={"token": trace_token},
        )
        self._raise_if_stream_cancelled(cancel_event)
        with self._client.http.stream(
            "GET",
            path,
            params=params,
            headers=headers,
            timeout=timeout,
        ) as response:
            if response.status_code < 200 or response.status_code >= 300:
                error_code = None
                retention_days = None
                try:
                    chunks: list[bytes] = []
                    body_size = 0
                    for chunk in response.iter_bytes():
                        body_size += len(chunk)
                        if body_size > 64 * 1024:
                            chunks = []
                            break
                        chunks.append(chunk)
                    body = json.loads(b"".join(chunks)) if chunks else None
                    detail = body.get("detail") if isinstance(body, dict) else None
                    if isinstance(detail, dict):
                        candidate = detail.get("code")
                        if (
                            isinstance(candidate, str)
                            and 0 < len(candidate) <= 64
                            and all(c.isupper() or c.isdigit() or c == "_" for c in candidate)
                        ):
                            error_code = candidate
                        candidate_days = detail.get("retention_days")
                        if isinstance(candidate_days, int) and candidate_days > 0:
                            retention_days = candidate_days
                except (ValueError, TypeError):
                    # Never retain arbitrary response bodies; they may contain PHI.
                    pass
                if response.status_code == 410 and error_code in {
                    "SSE_CURSOR_EXPIRED", "SSE_TRACE_EXPIRED", "TRACE_EXPIRED",
                }:
                    raise RunEventRetentionError(
                        error_code=error_code,
                        retention_days=retention_days,
                    )
                raise RunEventStreamError(
                    response.status_code,
                    error_code=error_code,
                )
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("text/event-stream"):
                raise RunEventStreamError(response.status_code)
            data_lines: list[str] = []
            for line in response.iter_lines():
                self._raise_if_stream_cancelled(cancel_event)
                if not line:
                    if data_lines:
                        try:
                            payload = json.loads("\n".join(data_lines))
                        except json.JSONDecodeError as error:
                            raise RunEventStreamError(response.status_code) from error
                        if not isinstance(payload, dict):
                            raise RunEventStreamError(response.status_code)
                        yield payload
                    data_lines = []
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                try:
                    payload = json.loads("\n".join(data_lines))
                except json.JSONDecodeError as error:
                    raise RunEventStreamError(response.status_code) from error
                if not isinstance(payload, dict):
                    raise RunEventStreamError(response.status_code)
                yield payload

    def stream_events_resilient(
        self,
        run_id: str,
        trace_token: str,
        *,
        last_event_id: Optional[str] = None,
        max_attempts: int = 4,
        initial_delay: float = 0.25,
        max_delay: float = 4.0,
        jitter_ratio: float = 0.2,
        request_options: Optional[RequestOptions] = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield events with bounded reconnect, cursor resume and token renewal.

        Only transport failures and a stream that closes before the explicit
        ``stream.completed`` marker are retried.  HTTP 401 renews the signed
        trace token through the bearer-authenticated endpoint.  Cursor,
        tenancy, authorization and protocol errors remain visible immediately.
        """
        if not trace_token:
            raise ValueError("trace_token is required")
        if not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if initial_delay < 0 or max_delay < initial_delay:
            raise ValueError("retry delays are invalid")
        if jitter_ratio < 0 or jitter_ratio > 1:
            raise ValueError("jitter_ratio must be between 0 and 1")

        import httpx

        current_token = trace_token
        cursor = last_event_id
        for attempt in range(max_attempts):
            try:
                completed = False
                for event in self.stream_events(
                    run_id,
                    current_token,
                    last_event_id=cursor,
                    request_options=request_options,
                ):
                    meta = event.get("meta")
                    if isinstance(meta, dict) and meta.get("event_id"):
                        cursor = str(meta["event_id"])
                    completed = completed or event.get("name") == "stream.completed"
                    yield event
                if completed:
                    return
                raise RunEventStreamError(retryable=True)
            except RunEventStreamError as error:
                can_renew = error.http_status == 401
                if not can_renew and not error.retryable:
                    raise
                if attempt + 1 >= max_attempts:
                    raise
                if can_renew:
                    current_token = str(
                        self.renew_trace_token(
                            run_id,
                            request_options=request_options,
                        )["trace_token"]
                    )
            except httpx.TransportError:
                if attempt + 1 >= max_attempts:
                    raise

            delay = min(max_delay, initial_delay * (2 ** attempt))
            delay *= 1 + random.uniform(-jitter_ratio, jitter_ratio)
            if delay > 0:
                bounded_delay = max(0.0, min(max_delay, delay))
                cancel_event = request_options.cancel_event if request_options else None
                if cancel_event is not None:
                    if cancel_event.wait(bounded_delay):
                        raise iCoDerRequestCancelledError("iCoDer request was cancelled")
                else:
                    time.sleep(bounded_delay)

    def _stream_request_options(
        self,
        request_options: Optional[RequestOptions],
        *,
        domain_headers: dict[str, str],
        domain_params: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, Any], float, Optional[threading.Event]]:
        headers = dict(domain_headers)
        params = dict(domain_params)
        timeout = self._client.config.timeout
        cancel_event: Optional[threading.Event] = None
        if request_options is None:
            return headers, params, timeout, cancel_event
        if not isinstance(request_options, RequestOptions):
            raise TypeError("request_options must be a RequestOptions instance")
        if request_options.max_retries not in (None, 0):
            raise ValueError("run event streams require max_retries to be 0")
        value = request_options.timeout_in_seconds
        if value is not None:
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value <= 0
                or value > 3600
            ):
                raise ValueError(
                    "timeout_in_seconds must be greater than 0 and at most 3600"
                )
            timeout = float(value)
        self._client._merge_request_headers(headers, request_options.headers)
        if not isinstance(request_options.query_params, Mapping):
            raise TypeError("request option query_params must be a mapping")
        for name, query_value in request_options.query_params.items():
            self._client._validate_query_pair(name, query_value)
            if name in params:
                raise ValueError(
                    f"request option query parameter {name} conflicts with a resource parameter"
                )
            params[name] = query_value
        cancel_event = request_options.cancel_event
        if cancel_event is not None and not isinstance(cancel_event, threading.Event):
            raise TypeError("cancel_event must be a threading.Event")
        self._raise_if_stream_cancelled(cancel_event)
        return headers, params, timeout, cancel_event

    @staticmethod
    def _raise_if_stream_cancelled(cancel_event: Optional[threading.Event]) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise iCoDerRequestCancelledError("iCoDer request was cancelled")


class AgentHubResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def list(
        self,
        use_case: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> AgentHubResponse:
        response = self._client.get(
            "/api/icoder/agents/hub",
            params={"use_case": use_case} if use_case else None,
            request_options=request_options,
        )
        response.raise_for_status()
        return validate_agent_hub_response(response.json())

    def readiness(
        self, request_options: Optional[RequestOptions] = None,
    ) -> AgentHubTenantReadinessResponse:
        response = self._client.get(
            "/api/icoder/agents/hub/readiness",
            request_options=request_options,
        )
        response.raise_for_status()
        return validate_agent_hub_tenant_readiness_response(response.json())

    def get_card(
        self,
        agent_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/icoder/agents/{quote(agent_id, safe='')}/card",
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()
