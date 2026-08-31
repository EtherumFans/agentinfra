"""A2A v0.3 Context plus v1 synchronous/asynchronous Task resources."""

from __future__ import annotations

from collections.abc import Mapping
import json
import threading
import time
from typing import Any, Iterator, Optional, Union
from urllib.parse import parse_qsl, quote, urlsplit
from uuid import uuid4

from ..client import iCoDerClient
from ..pagination import CursorPager
from ..request_options import RequestOptions, iCoDerRequestCancelledError


class A2AProtocolError(RuntimeError):
    """Protocol error that deliberately does not retain response details/body."""

    def __init__(
        self,
        jsonrpc_code: int,
        a2a_error_code: Optional[str] = None,
        http_status: Optional[int] = None,
    ) -> None:
        label = a2a_error_code or str(jsonrpc_code)
        super().__init__(f"iCoDer A2A request failed ({label})")
        self.jsonrpc_code = jsonrpc_code
        self.a2a_error_code = a2a_error_code
        self.http_status = http_status


class A2ATransportError(RuntimeError):
    """HTTP error that deliberately does not retain request/response objects."""

    def __init__(self, http_status: Optional[int] = None) -> None:
        suffix = f" (HTTP {http_status})" if http_status else ""
        super().__init__(f"iCoDer A2A transport failed{suffix}")
        self.http_status = http_status


def _raise_transport_error(status_code: int) -> None:
    if status_code < 200 or status_code >= 300:
        raise A2ATransportError(status_code)


def _raise_protocol_error(payload: Any, status_code: int) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return
    error = payload["error"]
    code = error.get("code")
    if not isinstance(code, int):
        return
    data = error.get("data")
    business_code = data.get("a2a_error_code") if isinstance(data, dict) else None
    # A2A v1 uses google.rpc.Status details / JSON-RPC Any details rather
    # than the v0.3 business-code object. Extract only the stable reason and
    # deliberately discard all descriptions and raw response content.
    details = data if isinstance(data, list) else error.get("details")
    if not isinstance(business_code, str) and isinstance(details, list):
        for detail in details:
            if isinstance(detail, dict) and isinstance(detail.get("reason"), str):
                business_code = detail["reason"]
                break
    raise A2AProtocolError(
        code,
        business_code if isinstance(business_code, str) else None,
        status_code,
    )


class A2AResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def message_send(
        self,
        agent_id: str,
        parts: Union[str, list[dict[str, Any]]],
        *,
        context_id: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        normalized_parts = (
            [{"kind": "text", "text": parts}] if isinstance(parts, str) else parts
        )
        message: dict[str, Any] = {
            "role": "user",
            "parts": normalized_parts,
            "messageId": message_id or f"msg-{uuid4()}",
        }
        if context_id:
            message["contextId"] = context_id
        if metadata:
            message["metadata"] = metadata
        response = self._client.post(
            f"/api/icoder/agents/{quote(agent_id, safe='')}/v1/message:send",
            headers={"A2A-Protocol-Version": "0.3"},
            json={
                "jsonrpc": "2.0",
                "id": f"rpc-{uuid4()}",
                "method": "message/send",
                "params": {"message": message},
            },
            request_options=request_options,
        )
        try:
            payload = response.json()
        except ValueError:
            _raise_transport_error(response.status_code)
            raise RuntimeError("iCoDer returned a non-JSON A2A response")
        _raise_protocol_error(payload, response.status_code)
        _raise_transport_error(response.status_code)
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise RuntimeError("iCoDer returned an incomplete A2A response")
        return result

    def message_stream(
        self,
        agent_id: str,
        parts: Union[str, list[dict[str, Any]]],
        *,
        context_id: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        request_options: Optional[RequestOptions] = None,
    ):
        """Yield raw SSE ``data`` payloads from authenticated A2A streaming."""
        normalized_parts = (
            [{"kind": "text", "text": parts}] if isinstance(parts, str) else parts
        )
        message: dict[str, Any] = {
            "role": "user",
            "parts": normalized_parts,
            "messageId": message_id or f"msg-{uuid4()}",
        }
        if context_id:
            message["contextId"] = context_id
        if metadata:
            message["metadata"] = metadata
        body = {
            "jsonrpc": "2.0",
            "id": f"rpc-{uuid4()}",
            "method": "message/stream",
            "params": {"message": message},
        }
        path = (
            f"/api/icoder/agents/{quote(agent_id, safe='')}/v1/message:stream"
        )
        headers, params, timeout, cancel_event = self._stream_request_options(
            request_options,
            domain_headers={
                "A2A-Protocol-Version": "0.3",
                "Accept": "text/event-stream",
            },
        )
        for attempt in range(2):
            self._raise_if_stream_cancelled(cancel_event)
            with self._client.http.stream(
                "POST",
                path,
                headers=headers,
                params=params or None,
                json=body,
                timeout=timeout,
            ) as response:
                if (
                    response.status_code == 401
                    and attempt == 0
                    and self._client._refresh_token()
                ):
                    continue
                _raise_transport_error(response.status_code)
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("text/event-stream"):
                    raise A2ATransportError(response.status_code)
                for line in response.iter_lines():
                    self._raise_if_stream_cancelled(cancel_event)
                    if line.startswith("data:"):
                        yield line[5:].lstrip()
                return

    def get_context(
        self,
        agent_id: str,
        context_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/icoder/agents/{quote(agent_id, safe='')}/v1/contexts/"
            f"{quote(context_id, safe='')}",
            headers={"A2A-Protocol-Version": "0.3"},
            params={"limit": limit, "offset": offset},
            request_options=request_options,
        )
        try:
            payload = response.json()
        except ValueError:
            _raise_transport_error(response.status_code)
            raise RuntimeError("iCoDer returned a non-JSON Context response")
        _raise_protocol_error(payload, response.status_code)
        _raise_transport_error(response.status_code)
        if not isinstance(payload, dict):
            raise RuntimeError("iCoDer returned an incomplete Context response")
        return payload

    def delete_context(
        self,
        context_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.delete(
            f"/api/icoder/contexts/{quote(context_id, safe='')}",
            headers={"A2A-Protocol-Version": "0.3"},
            request_options=request_options,
        )
        try:
            payload = response.json()
        except ValueError:
            _raise_transport_error(response.status_code)
            raise RuntimeError("iCoDer returned a non-JSON A2A delete response")
        _raise_protocol_error(payload, response.status_code)
        _raise_transport_error(response.status_code)
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise RuntimeError("iCoDer returned an incomplete A2A delete response")
        return result

    @staticmethod
    def _v1_headers() -> dict[str, str]:
        return {"A2A-Version": "1.0"}

    @staticmethod
    def _v1_message(
        parts: Union[str, list[dict[str, Any]]],
        *,
        context_id: Optional[str],
        task_id: Optional[str],
        message_id: Optional[str],
        metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_parts = (
            [{"text": parts, "mediaType": "text/plain"}]
            if isinstance(parts, str)
            else parts
        )
        message: dict[str, Any] = {
            "role": "ROLE_USER",
            "parts": normalized_parts,
            "messageId": message_id or f"msg-{uuid4()}",
        }
        if context_id:
            message["contextId"] = context_id
        if task_id:
            message["taskId"] = task_id
        if metadata:
            message["metadata"] = metadata
        return message

    def message_send_v1(
        self,
        agent_id: str,
        parts: Union[str, list[dict[str, Any]]],
        *,
        context_id: Optional[str] = None,
        task_id: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        return_immediately: bool = False,
        accepted_output_modes: Optional[list[str]] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Send an A2A v1 Message; optionally return a durable submitted Task."""

        configuration: dict[str, Any] = {
            "returnImmediately": return_immediately,
        }
        if accepted_output_modes:
            configuration["acceptedOutputModes"] = accepted_output_modes
        response = self._client.post(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/message:send",
            headers=self._v1_headers(),
            json={
                "message": self._v1_message(
                    parts,
                    context_id=context_id,
                    task_id=task_id,
                    message_id=message_id,
                    metadata=metadata,
                ),
                "configuration": configuration,
            },
            request_options=request_options,
        )
        try:
            payload = response.json()
        except ValueError:
            _raise_transport_error(response.status_code)
            raise RuntimeError("iCoDer returned a non-JSON A2A v1 response")
        _raise_protocol_error(payload, response.status_code)
        _raise_transport_error(response.status_code)
        if not isinstance(payload, dict) or not (
            isinstance(payload.get("message"), dict)
            or isinstance(payload.get("task"), dict)
        ):
            raise RuntimeError("iCoDer returned an incomplete A2A v1 response")
        return payload

    def message_stream_v1(
        self,
        agent_id: str,
        parts: Union[str, list[dict[str, Any]]],
        *,
        context_id: Optional[str] = None,
        task_id: Optional[str] = None,
        message_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        return_immediately: bool = False,
        accepted_output_modes: Optional[list[str]] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> Iterator[dict[str, Any]]:
        """Start a durable v1 Task and yield decoded standard SSE updates."""

        configuration: dict[str, Any] = {
            "returnImmediately": return_immediately,
        }
        if accepted_output_modes:
            configuration["acceptedOutputModes"] = accepted_output_modes
        path = (
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/message:stream"
        )
        body = {
            "message": self._v1_message(
                parts,
                context_id=context_id,
                task_id=task_id,
                message_id=message_id,
                metadata=metadata,
            ),
            "configuration": configuration,
        }
        headers, params, timeout, cancel_event = self._stream_request_options(
            request_options,
            domain_headers={**self._v1_headers(), "Accept": "text/event-stream"},
        )
        for attempt in range(2):
            self._raise_if_stream_cancelled(cancel_event)
            with self._client.http.stream(
                "POST",
                path,
                headers=headers,
                params=params or None,
                json=body,
                timeout=timeout,
            ) as response:
                if (
                    response.status_code == 401
                    and attempt == 0
                    and self._client._refresh_token()
                ):
                    continue
                if not 200 <= response.status_code < 300:
                    try:
                        _raise_protocol_error(response.json(), response.status_code)
                    except ValueError:
                        pass
                    _raise_transport_error(response.status_code)
                if not response.headers.get("content-type", "").startswith(
                    "text/event-stream"
                ):
                    raise A2ATransportError(response.status_code)
                data_lines: list[str] = []
                event_id = ""
                event_type = "message"
                for line in response.iter_lines():
                    self._raise_if_stream_cancelled(cancel_event)
                    if not line:
                        if data_lines:
                            try:
                                payload = json.loads("\n".join(data_lines))
                            except json.JSONDecodeError as exc:
                                raise A2ATransportError(response.status_code) from exc
                            if not isinstance(payload, dict):
                                raise A2ATransportError(response.status_code)
                            payload.setdefault("eventId", event_id)
                            payload.setdefault("eventType", event_type)
                            yield payload
                        data_lines = []
                        event_id = ""
                        event_type = "message"
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif line.startswith("id:"):
                        event_id = line[3:].lstrip()
                    elif line.startswith("event:"):
                        event_type = line[6:].lstrip()
                if data_lines:
                    try:
                        payload = json.loads("\n".join(data_lines))
                    except json.JSONDecodeError as exc:
                        raise A2ATransportError(response.status_code) from exc
                    if not isinstance(payload, dict):
                        raise A2ATransportError(response.status_code)
                    payload.setdefault("eventId", event_id)
                    payload.setdefault("eventType", event_type)
                    yield payload
                return

    def get_task_v1(
        self,
        agent_id: str,
        task_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}",
            headers=self._v1_headers(),
            request_options=request_options,
        )
        return self._v1_object_response(response, "Task")

    def list_tasks_v1(
        self,
        agent_id: str,
        *,
        context_id: Optional[str] = None,
        status: Optional[str] = None,
        page_size: int = 50,
        page_token: Optional[str] = None,
        status_timestamp_after: Optional[str] = None,
        include_artifacts: bool = False,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "pageSize": page_size,
            "includeArtifacts": include_artifacts,
        }
        if context_id:
            params["contextId"] = context_id
        if status:
            params["status"] = status
        if page_token:
            params["pageToken"] = page_token
        if status_timestamp_after:
            params["statusTimestampAfter"] = status_timestamp_after
        response = self._client.get(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/tasks",
            headers=self._v1_headers(),
            params=params,
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Task list")
        if not isinstance(payload.get("tasks"), list):
            raise RuntimeError("iCoDer returned an incomplete A2A v1 Task list")
        return payload

    def iterate_tasks_v1(
        self,
        agent_id: str,
        *,
        context_id: Optional[str] = None,
        status: Optional[str] = None,
        page_size: int = 50,
        initial_page_token: Optional[str] = None,
        status_timestamp_after: Optional[str] = None,
        include_artifacts: bool = False,
        max_pages: int = 10000,
        request_options: Optional[RequestOptions] = None,
    ) -> CursorPager[dict[str, Any], dict[str, Any]]:
        """Lazily iterate Tasks and fail closed on cursor loops."""
        return CursorPager(
            lambda page_token: self.list_tasks_v1(
                agent_id,
                context_id=context_id,
                status=status,
                page_size=page_size,
                page_token=page_token,
                status_timestamp_after=status_timestamp_after,
                include_artifacts=include_artifacts,
                request_options=request_options,
            ),
            lambda page: page["tasks"],
            lambda page: page.get("nextPageToken"),
            initial_page_token=initial_page_token,
            max_pages=max_pages,
        )

    def cancel_task_v1(
        self,
        agent_id: str,
        task_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}:cancel",
            headers=self._v1_headers(),
            json={},
            request_options=request_options,
        )
        return self._v1_object_response(response, "Task")

    def wait_task_v1(
        self,
        agent_id: str,
        task_id: str,
        *,
        timeout: float = 60.0,
        poll_interval: float = 0.25,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Poll until a Task is terminal or yields a resumable interruption."""

        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("timeout and poll_interval must be positive")
        settled = {
            "TASK_STATE_COMPLETED",
            "TASK_STATE_FAILED",
            "TASK_STATE_CANCELED",
            "TASK_STATE_REJECTED",
            "TASK_STATE_INPUT_REQUIRED",
            "TASK_STATE_AUTH_REQUIRED",
        }
        deadline = time.monotonic() + timeout
        while True:
            task = self.get_task_v1(agent_id, task_id, request_options)
            status = task.get("status") if isinstance(task.get("status"), dict) else {}
            if status.get("state") in settled:
                return task
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"A2A v1 Task {task_id!r} did not reach a settled state")
            time.sleep(min(poll_interval, remaining))

    def subscribe_task_v1(
        self,
        agent_id: str,
        task_id: str,
        *,
        after_sequence: int = 0,
        last_event_id: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield decoded durable Task events and support Last-Event-ID resume."""

        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        path = (
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}:subscribe"
        )
        headers = {
            **self._v1_headers(),
            "Accept": "text/event-stream",
        }
        if last_event_id:
            headers["Last-Event-ID"] = last_event_id
        headers, params, timeout, cancel_event = self._stream_request_options(
            request_options,
            domain_headers=headers,
            domain_params={"afterSequence": after_sequence},
        )
        for attempt in range(2):
            self._raise_if_stream_cancelled(cancel_event)
            with self._client.http.stream(
                "GET",
                path,
                headers=headers,
                params=params,
                timeout=timeout,
            ) as response:
                if (
                    response.status_code == 401
                    and attempt == 0
                    and self._client._refresh_token()
                ):
                    continue
                if not 200 <= response.status_code < 300:
                    try:
                        _raise_protocol_error(response.json(), response.status_code)
                    except ValueError:
                        pass
                    _raise_transport_error(response.status_code)
                if not response.headers.get("content-type", "").startswith(
                    "text/event-stream"
                ):
                    raise A2ATransportError(response.status_code)
                data_lines: list[str] = []
                event_id = ""
                event_type = "message"
                for line in response.iter_lines():
                    self._raise_if_stream_cancelled(cancel_event)
                    if not line:
                        if data_lines:
                            try:
                                payload = json.loads("\n".join(data_lines))
                            except json.JSONDecodeError as exc:
                                raise A2ATransportError(response.status_code) from exc
                            if not isinstance(payload, dict):
                                raise A2ATransportError(response.status_code)
                            payload.setdefault("eventId", event_id)
                            payload.setdefault("eventType", event_type)
                            yield payload
                        data_lines = []
                        event_id = ""
                        event_type = "message"
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                    elif line.startswith("id:"):
                        event_id = line[3:].lstrip()
                    elif line.startswith("event:"):
                        event_type = line[6:].lstrip()
                if data_lines:
                    try:
                        payload = json.loads("\n".join(data_lines))
                    except json.JSONDecodeError as exc:
                        raise A2ATransportError(response.status_code) from exc
                    if not isinstance(payload, dict):
                        raise A2ATransportError(response.status_code)
                    payload.setdefault("eventId", event_id)
                    payload.setdefault("eventType", event_type)
                    yield payload
                return

    def export_context_traces(
        self,
        context_id: str,
        *,
        page_size: int = 50,
        page_token: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Export a Context's newest-first OpenInference-shaped trace page."""
        if page_size < 1 or page_size > 200:
            raise ValueError("page_size must be between 1 and 200")
        params: dict[str, Any] = {"pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        response = self._client.get(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/trace",
            headers=self._v1_headers(),
            params=params,
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "trace page")
        if not isinstance(payload.get("traces"), list):
            raise RuntimeError("iCoDer returned an incomplete Agentic trace page")
        return payload

    def iterate_context_traces(
        self,
        context_id: str,
        *,
        page_size: int = 50,
        initial_page_token: Optional[str] = None,
        max_pages: int = 10000,
        request_options: Optional[RequestOptions] = None,
    ) -> CursorPager[dict[str, Any], dict[str, Any]]:
        return CursorPager(
            lambda page_token: self.export_context_traces(
                context_id,
                page_size=page_size,
                page_token=page_token,
                request_options=request_options,
            ),
            lambda page: page["traces"],
            lambda page: page.get("nextPageToken"),
            initial_page_token=initial_page_token,
            max_pages=max_pages,
        )

    def list_contexts_v2(
        self,
        *,
        agent_id: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        page_size: int = 50,
        page_token: Optional[str] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """List first-class Agentic v2 Context resources for this tenant."""
        if page_size < 1 or page_size > 200:
            raise ValueError("page_size must be between 1 and 200")
        params: dict[str, Any] = {"pageSize": page_size}
        if agent_id:
            params["agentId"] = agent_id
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        if page_token:
            params["pageToken"] = page_token
        response = self._client.get(
            "/api/v2/agentic/contexts",
            headers=self._v1_headers(),
            params=params,
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Context page")
        if not isinstance(payload.get("contexts"), list):
            raise RuntimeError("iCoDer returned an incomplete Agentic Context page")
        return payload

    def iterate_contexts_v2(
        self,
        *,
        agent_id: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        page_size: int = 50,
        initial_page_token: Optional[str] = None,
        max_pages: int = 10000,
        request_options: Optional[RequestOptions] = None,
    ) -> CursorPager[dict[str, Any], dict[str, Any]]:
        return CursorPager(
            lambda page_token: self.list_contexts_v2(
                agent_id=agent_id,
                from_time=from_time,
                to_time=to_time,
                page_size=page_size,
                page_token=page_token,
                request_options=request_options,
            ),
            lambda page: page["contexts"],
            lambda page: page.get("nextPageToken"),
            initial_page_token=initial_page_token,
            max_pages=max_pages,
        )

    def get_context_v2(
        self,
        context_id: str,
        *,
        history_length: Optional[int] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if history_length is not None:
            if history_length < 0 or history_length > 100:
                raise ValueError("history_length must be between 0 and 100")
            params["historyLength"] = history_length
        response = self._client.get(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}",
            headers=self._v1_headers(),
            params=params,
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Context")
        if not isinstance(payload.get("tasks"), list):
            raise RuntimeError("iCoDer returned an incomplete Agentic Context")
        return payload

    def delete_context_v2(
        self,
        context_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        response = self._client.delete(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}",
            headers=self._v1_headers(),
            request_options=request_options,
        )
        _raise_transport_error(response.status_code)

    def list_context_tasks_v2(
        self,
        context_id: str,
        *,
        page_size: int = 50,
        page_token: Optional[str] = None,
        history_length: int = 0,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        if page_size < 1 or page_size > 200:
            raise ValueError("page_size must be between 1 and 200")
        if history_length < 0 or history_length > 100:
            raise ValueError("history_length must be between 0 and 100")
        params: dict[str, Any] = {
            "pageSize": page_size,
            "historyLength": history_length,
        }
        if page_token:
            params["pageToken"] = page_token
        response = self._client.get(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/tasks",
            headers=self._v1_headers(),
            params=params,
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Context Task page")
        if not isinstance(payload.get("tasks"), list):
            raise RuntimeError("iCoDer returned an incomplete Context Task page")
        return payload

    def iterate_context_tasks_v2(
        self,
        context_id: str,
        *,
        page_size: int = 50,
        initial_page_token: Optional[str] = None,
        history_length: int = 0,
        max_pages: int = 10000,
        request_options: Optional[RequestOptions] = None,
    ) -> CursorPager[dict[str, Any], dict[str, Any]]:
        return CursorPager(
            lambda page_token: self.list_context_tasks_v2(
                context_id,
                page_size=page_size,
                page_token=page_token,
                history_length=history_length,
                request_options=request_options,
            ),
            lambda page: page["tasks"],
            lambda page: page.get("nextPageToken"),
            initial_page_token=initial_page_token,
            max_pages=max_pages,
        )

    def get_context_task_v2(
        self,
        context_id: str,
        task_id: str,
        *,
        history_length: Optional[int] = None,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if history_length is not None:
            if history_length < 0 or history_length > 100:
                raise ValueError("history_length must be between 0 and 100")
            params["historyLength"] = history_length
        response = self._client.get(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}",
            headers=self._v1_headers(),
            params=params,
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Context Task")
        if not isinstance(payload.get("status"), dict):
            raise RuntimeError("iCoDer returned an incomplete Context Task")
        return payload

    def get_task_artifact_v2(
        self,
        context_id: str,
        task_id: str,
        artifact_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}/artifacts/{quote(artifact_id, safe='')}",
            headers=self._v1_headers(),
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Task Artifact")
        if not isinstance(payload.get("parts"), list):
            raise RuntimeError("iCoDer returned an incomplete Task Artifact")
        return payload

    @staticmethod
    def _artifact_object_root(
        context_id: str, task_id: str, artifact_id: str
    ) -> str:
        return (
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}/artifacts/{quote(artifact_id, safe='')}/objects"
        )

    def upload_task_artifact_object_v2(
        self,
        context_id: str,
        task_id: str,
        artifact_id: str,
        *,
        raw: str,
        filename: str,
        media_type: str,
        data_classification: str = "deidentified",
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            self._artifact_object_root(context_id, task_id, artifact_id),
            headers=self._v1_headers(),
            json={
                "raw": raw,
                "filename": filename,
                "mediaType": media_type,
                "dataClassification": data_classification,
            },
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Artifact object")
        if not isinstance(payload.get("objectId"), str):
            raise RuntimeError("iCoDer returned an incomplete Artifact object")
        return payload

    def list_task_artifact_objects_v2(
        self,
        context_id: str,
        task_id: str,
        artifact_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            self._artifact_object_root(context_id, task_id, artifact_id),
            headers=self._v1_headers(),
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Artifact object page")
        if not isinstance(payload.get("objects"), list):
            raise RuntimeError("iCoDer returned an incomplete Artifact object page")
        return payload

    def authorize_task_artifact_object_download_v2(
        self,
        context_id: str,
        task_id: str,
        artifact_id: str,
        object_id: str,
        *,
        purpose_of_use: str,
        expires_in_seconds: int = 60,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        if purpose_of_use not in {
            "treatment", "payment", "healthcare_operations"
        }:
            raise ValueError(
                "purpose_of_use must be treatment, payment, or healthcare_operations"
            )
        if expires_in_seconds < 1 or expires_in_seconds > 300:
            raise ValueError("expires_in_seconds must be between 1 and 300")
        response = self._client.post(
            f"{self._artifact_object_root(context_id, task_id, artifact_id)}/"
            f"{quote(object_id, safe='')}:authorize-download",
            headers=self._v1_headers(),
            json={
                "purposeOfUse": purpose_of_use,
                "expiresInSeconds": expires_in_seconds,
            },
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Artifact download authorization")
        part = payload.get("part")
        if not isinstance(part, dict) or not isinstance(part.get("url"), str):
            raise RuntimeError(
                "iCoDer returned an incomplete Artifact download authorization"
            )
        return payload

    def download_authorized_artifact_object_v2(
        self,
        authorization: dict[str, Any],
        request_options: Optional[RequestOptions] = None,
    ) -> bytes:
        """Consume once with this client's Bearer identity; never retry."""
        part = authorization.get("part") if isinstance(authorization, dict) else None
        url = part.get("url") if isinstance(part, dict) else None
        if not isinstance(url, str) or not url:
            raise ValueError("authorization must contain part.url")
        target = urlsplit(url)
        base = urlsplit(self._client.base_url)
        if target.scheme or target.netloc:
            target_port = target.port or (443 if target.scheme.lower() == "https" else 80)
            base_port = base.port or (443 if base.scheme.lower() == "https" else 80)
            if (
                target.scheme.lower() != base.scheme.lower()
                or (target.hostname or "").lower() != (base.hostname or "").lower()
                or target_port != base_port
                or target.username is not None
                or target.password is not None
            ):
                raise ValueError("artifact download URL must stay on the configured origin")
        if (
            target.fragment
            or not target.path.startswith(
                "/api/v2/agentic/artifact-objects/download/"
            )
        ):
            raise ValueError("artifact download URL has an invalid managed path")
        query = parse_qsl(
            target.query,
            keep_blank_values=True,
            max_num_fields=16,
        )
        if request_options is not None and request_options.max_retries not in (None, 0):
            raise ValueError("single-use artifact downloads require max_retries to be 0")
        effective_options = RequestOptions(
            timeout_in_seconds=request_options.timeout_in_seconds
            if request_options else None,
            max_retries=0,
            cancel_event=request_options.cancel_event if request_options else None,
            headers=request_options.headers if request_options else {},
            query_params=request_options.query_params if request_options else {},
        )
        response = self._client.get(
            target.path,
            params=query or None,
            request_options=effective_options,
        )
        _raise_transport_error(response.status_code)
        return bytes(response.content)

    def delete_task_artifact_object_v2(
        self,
        context_id: str,
        task_id: str,
        artifact_id: str,
        object_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        response = self._client.delete(
            f"{self._artifact_object_root(context_id, task_id, artifact_id)}/"
            f"{quote(object_id, safe='')}",
            headers=self._v1_headers(),
            request_options=request_options,
        )
        _raise_transport_error(response.status_code)

    def get_agent_usage(
        self,
        agent_id: str,
        *,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        granularity: str = "day",
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Return daily invocation and unique-Context usage for one Agent."""
        if granularity not in {"minute", "hour", "day", "week"}:
            raise ValueError("granularity must be minute, hour, day, or week")
        params: dict[str, Any] = {"granularity": granularity}
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        response = self._client.get(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/usage",
            headers=self._v1_headers(),
            params=params,
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Agent usage")
        if (
            payload.get("granularity") != "day"
            or not isinstance(payload.get("totals"), dict)
            or not isinstance(payload.get("buckets"), list)
        ):
            raise RuntimeError("iCoDer returned an incomplete Agent usage response")
        return payload

    def get_agent_card(
        self,
        agent_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Return the authenticated tenant Agent's current A2A 1.0 card."""
        response = self._client.get(
            f"/api/v2/agentic/agents/{quote(agent_id, safe='')}/"
            ".well-known/agent-card.json",
            headers=self._v1_headers(),
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "Agent Card")
        if (
            not isinstance(payload.get("supportedInterfaces"), list)
            or not isinstance(payload.get("skills"), list)
            or not isinstance(payload.get("capabilities"), dict)
        ):
            raise RuntimeError("iCoDer returned an incomplete Agent Card")
        return payload

    def submit_task_feedback(
        self,
        context_id: str,
        task_id: str,
        feedback: dict[str, Any],
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}/feedback",
            headers=self._v1_headers(),
            json=feedback,
            request_options=request_options,
        )
        return self._v1_object_response(response, "feedback")

    def list_task_feedback(
        self,
        context_id: str,
        task_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}/feedback",
            headers=self._v1_headers(),
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "feedback list")
        if not isinstance(payload.get("feedbacks"), list):
            raise RuntimeError("iCoDer returned an incomplete Agentic feedback list")
        return payload

    def delete_task_feedback(
        self,
        context_id: str,
        task_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        response = self._client.delete(
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}/feedback",
            headers=self._v1_headers(),
            request_options=request_options,
        )
        _raise_transport_error(response.status_code)

    def authorize_feedback_for_training(
        self,
        context_id: str,
        task_id: str,
        feedback_id: str,
        authorization: dict[str, Any],
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        """Owner/admin authorization for metadata-only quality improvement."""
        response = self._client.put(
            self._feedback_training_authorization_path(
                context_id, task_id, feedback_id,
            ),
            headers=self._v1_headers(),
            json=authorization,
            request_options=request_options,
        )
        payload = self._v1_object_response(response, "feedback training authorization")
        if (
            not isinstance(payload.get("trainingAuthorized"), bool)
            or payload.get("dataScope") != "feedback_metadata_only"
        ):
            raise RuntimeError(
                "iCoDer returned an incomplete feedback training authorization"
            )
        return payload

    def get_feedback_training_authorization(
        self,
        context_id: str,
        task_id: str,
        feedback_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> dict[str, Any]:
        response = self._client.get(
            self._feedback_training_authorization_path(
                context_id, task_id, feedback_id,
            ),
            headers=self._v1_headers(),
            request_options=request_options,
        )
        return self._v1_object_response(
            response, "feedback training authorization",
        )

    def revoke_feedback_training_authorization(
        self,
        context_id: str,
        task_id: str,
        feedback_id: str,
        request_options: Optional[RequestOptions] = None,
    ) -> None:
        response = self._client.delete(
            self._feedback_training_authorization_path(
                context_id, task_id, feedback_id,
            ),
            headers=self._v1_headers(),
            request_options=request_options,
        )
        _raise_transport_error(response.status_code)

    @staticmethod
    def _feedback_training_authorization_path(
        context_id: str,
        task_id: str,
        feedback_id: str,
    ) -> str:
        return (
            f"/api/v2/agentic/contexts/{quote(context_id, safe='')}/tasks/"
            f"{quote(task_id, safe='')}/feedback/{quote(feedback_id, safe='')}/"
            "training-authorization"
        )

    @staticmethod
    def _v1_object_response(response: Any, label: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            _raise_transport_error(response.status_code)
            raise RuntimeError(f"iCoDer returned a non-JSON A2A v1 {label} response")
        _raise_protocol_error(payload, response.status_code)
        _raise_transport_error(response.status_code)
        if not isinstance(payload, dict):
            raise RuntimeError(f"iCoDer returned an incomplete A2A v1 {label} response")
        return payload

    def _stream_request_options(
        self,
        request_options: Optional[RequestOptions],
        *,
        domain_headers: dict[str, str],
        domain_params: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, str], dict[str, Any], float, Optional[threading.Event]]:
        """Validate bounded controls for a non-replayed streaming request."""
        headers = dict(domain_headers)
        params = dict(domain_params or {})
        timeout = self._client.config.timeout
        cancel_event: Optional[threading.Event] = None
        if request_options is None:
            return headers, params, timeout, cancel_event
        if not isinstance(request_options, RequestOptions):
            raise TypeError("request_options must be a RequestOptions instance")
        if request_options.max_retries not in (None, 0):
            raise ValueError("streaming requests require max_retries to be 0")
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
