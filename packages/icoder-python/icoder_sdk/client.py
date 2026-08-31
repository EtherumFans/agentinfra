"""iCoDer HTTP client with concurrency-safe authentication and bounded retries."""

from __future__ import annotations

from collections.abc import Mapping
from email.utils import parsedate_to_datetime
import re
import threading
import time
from types import MethodType
from typing import Callable, Optional
from urllib.parse import urlsplit

import httpx

from .types import iCoDerConfig
from .errors import api_error_from_response, iCoDerClientError
from .request_options import RequestOptions, iCoDerRequestCancelledError


class iCoDerAuthenticationError(iCoDerClientError):
    """Sanitized authentication failure without request bodies or credentials."""

    def __init__(self, status_code: Optional[int] = None, request_id: Optional[str] = None):
        message = (
            f"iCoDer authentication failed with HTTP {status_code}"
            if status_code
            else "iCoDer authentication failed"
        )
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


class iCoDerClient:
    """Low-level synchronous HTTP client for the iCoDer API."""

    _IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}
    _PROTECTED_REQUEST_HEADERS = {
        "authorization", "cookie", "host", "content-length", "tenant-name",
        "x-icoder-organization-id", "x-organization-id",
    }

    def __init__(self, config: iCoDerConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        if bool(config.client_id) != bool(config.client_secret):
            raise ValueError("client_id and client_secret must be configured together")
        for name in ("max_retries", "retry_initial_delay", "retry_max_delay"):
            value = getattr(config, name)
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if config.retry_max_delay < config.retry_initial_delay:
            raise ValueError("retry_max_delay must be greater than or equal to retry_initial_delay")
        if config.token_refresh_skew < 0:
            raise ValueError("token_refresh_skew must be non-negative")

        self.http = httpx.Client(
            base_url=self.base_url,
            timeout=config.timeout,
            headers={"Authorization": f"Bearer {config.access_token}"}
            if config.access_token
            else {},
        )
        self._on_token_refresh: Optional[Callable[[str, Optional[str]], None]] = None
        self._auth_lock = threading.Lock()
        self._token_expires_at = 0.0

        # Resource facade. Imports stay local to avoid module cycles while
        # preserving the pre-existing pattern of constructing resources by hand.
        from .resources.agents import AgentsResource, ExpertsResource
        from .resources.billing import BillingResource, UsageResource
        from .resources.facts import FactsResource
        from .resources.oauth import OAuthResource
        from .resources.runs import AgentHubResource, RunsResource
        from .resources.a2a import A2AResource
        from .resources.speech_to_text import SpeechToTextResource
        from .resources.streams import StreamsResource
        from .resources.textgen import TextGenResource
        from .resources.platform import PlatformResource
        from .resources.documents import DocumentsResource
        from .resources.templates import TemplatesResource
        from .resources.medical_coding import MedicalCodingResource
        from .resources.models import ModelsResource
        from .resources.drg_dip_risk_review import DrgDipRiskReviewResource
        from .resources.compliance import ComplianceResource
        from .resources.runtime import RuntimeResource
        from .resources.patient_context import PatientContextResource

        self.agents = AgentsResource(self)
        self.experts = ExpertsResource(self)
        self.billing = BillingResource(self)
        self.usage = UsageResource(self)
        self.facts = FactsResource(self)
        self.oauth = OAuthResource(self)
        self.runs = RunsResource(self)
        self.agent_hub = AgentHubResource(self)
        self.a2a = A2AResource(self)
        self.speech_to_text = SpeechToTextResource(self)
        self.streams = StreamsResource(self)
        self.textgen = TextGenResource(self)
        self.platform = PlatformResource(self)
        self.documents = DocumentsResource(self)
        self.templates = TemplatesResource(self)
        self.medical_coding = MedicalCodingResource(self)
        self.models = ModelsResource(self)
        self.drg_dip_risk_review = DrgDipRiskReviewResource(self)
        self.compliance = ComplianceResource(self)
        self.runtime = RuntimeResource(self)
        self.patient_context = PatientContextResource(self)

    def on_token_refresh(self, callback: Callable[[str, Optional[str]], None]):
        """Register a callback invoked after a managed token changes."""
        self._on_token_refresh = callback

    def authenticate(self, client_id: str, client_secret: str) -> dict:
        """Exchange client credentials without retaining the supplied secret."""
        return self._exchange_client_credentials(client_id, client_secret)

    def ensure_access_token(self) -> Optional[str]:
        """Ensure transports such as WebSockets receive a current bearer token."""
        if self.config.client_id and self.config.client_secret:
            return self._ensure_client_credentials_token()
        return self.config.access_token

    def _send_auth_request(self, path: str, **kwargs) -> httpx.Response:
        request = self.http.build_request("POST", path, **kwargs)
        request.headers.pop("authorization", None)
        return self.http.send(request)

    @staticmethod
    def _raise_auth_error(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        raise iCoDerAuthenticationError(
            response.status_code,
            response.headers.get("x-request-id"),
        )

    def _exchange_client_credentials(self, client_id: str, client_secret: str) -> dict:
        try:
            response = self._send_auth_request(
                "/api/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "api:read api:write",
                },
            )
            self._raise_auth_error(response)
            data = response.json()
            if not isinstance(data.get("access_token"), str) or not data["access_token"]:
                raise iCoDerAuthenticationError(response.status_code)
            return data
        except iCoDerAuthenticationError:
            raise
        except Exception:
            raise iCoDerAuthenticationError() from None

    def _ensure_client_credentials_token(self, force: bool = False) -> str:
        if not self.config.client_id or not self.config.client_secret:
            raise iCoDerAuthenticationError()
        with self._auth_lock:
            now = time.monotonic()
            if (
                not force
                and self.config.access_token
                and now + self.config.token_refresh_skew < self._token_expires_at
            ):
                return self.config.access_token
            data = self._exchange_client_credentials(
                self.config.client_id,
                self.config.client_secret,
            )
            self.config.access_token = data["access_token"]
            ttl = max(0.0, float(data.get("expires_in", 300)))
            effective_skew = min(self.config.token_refresh_skew, ttl / 2)
            self._token_expires_at = now + ttl - effective_skew
            self.http.headers["Authorization"] = f"Bearer {self.config.access_token}"
            if self._on_token_refresh:
                self._on_token_refresh(self.config.access_token, None)
            return self.config.access_token

    def _refresh_user_token_locked(self) -> bool:
        if not self.config.refresh_token:
            return False
        try:
            response = self._send_auth_request(
                "/api/auth/refresh",
                json={"refresh_token": self.config.refresh_token},
            )
            self._raise_auth_error(response)
            data = response.json()
            access_token = data.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise iCoDerAuthenticationError(response.status_code)
            self.config.access_token = access_token
            self.config.refresh_token = data.get("refresh_token", self.config.refresh_token)
            self.http.headers["Authorization"] = f"Bearer {self.config.access_token}"
            if self._on_token_refresh:
                self._on_token_refresh(self.config.access_token, self.config.refresh_token)
            return True
        except iCoDerAuthenticationError:
            raise
        except Exception:
            raise iCoDerAuthenticationError() from None

    def _refresh_after_401(self, stale_token: Optional[str]) -> bool:
        with self._auth_lock:
            if stale_token and self.config.access_token and self.config.access_token != stale_token:
                return True
            if self.config.client_id and self.config.client_secret:
                # The lock is already held, so perform the exchange inline.
                data = self._exchange_client_credentials(
                    self.config.client_id,
                    self.config.client_secret,
                )
                self.config.access_token = data["access_token"]
                ttl = max(0.0, float(data.get("expires_in", 300)))
                effective_skew = min(self.config.token_refresh_skew, ttl / 2)
                self._token_expires_at = time.monotonic() + ttl - effective_skew
                self.http.headers["Authorization"] = f"Bearer {self.config.access_token}"
                if self._on_token_refresh:
                    self._on_token_refresh(self.config.access_token, None)
                return True
            return self._refresh_user_token_locked()

    def _refresh_token(self) -> bool:
        """Backward-compatible explicit refresh operation."""
        with self._auth_lock:
            return self._refresh_user_token_locked()

    @staticmethod
    def _request_has_idempotency_key(headers: httpx.Headers) -> bool:
        return bool(headers.get("idempotency-key"))

    def _should_retry(self, method: str, response: httpx.Response, headers: httpx.Headers) -> bool:
        retryable_status = (
            response.status_code in {408, 429}
            or 500 <= response.status_code <= 599
        )
        safe_method = method in self._IDEMPOTENT_METHODS
        return retryable_status and (safe_method or self._request_has_idempotency_key(headers))

    def _retry_delay(self, response: httpx.Response, retry_index: int) -> float:
        header = response.headers.get("retry-after")
        if header:
            try:
                delay = max(0.0, float(header))
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(header)
                    delay = max(0.0, parsed.timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    delay = -1.0
            if delay >= 0:
                return min(self.config.retry_max_delay, delay)
        return min(
            self.config.retry_max_delay,
            self.config.retry_initial_delay * (2**retry_index),
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        request_options: Optional[RequestOptions] = None,
        **kwargs,
    ) -> httpx.Response:
        """Send a request with managed auth and idempotency-aware 408/429/5xx retries."""
        normalized_method = method.upper()
        self._validate_relative_path(path)
        if self.config.client_id and self.config.client_secret:
            self._ensure_client_credentials_token()

        request_kwargs = dict(kwargs)
        headers = httpx.Headers(request_kwargs.pop("headers", None))
        max_retries = self.config.max_retries
        cancel_event = None
        if request_options is not None:
            if not isinstance(request_options, RequestOptions):
                raise TypeError("request_options must be a RequestOptions instance")
            timeout = request_options.timeout_in_seconds
            if timeout is not None:
                if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) \
                        or timeout <= 0 or timeout > 3600:
                    raise ValueError(
                        "timeout_in_seconds must be greater than 0 and at most 3600"
                    )
                if "timeout" in request_kwargs:
                    raise ValueError("timeout conflicts with request_options.timeout_in_seconds")
                request_kwargs["timeout"] = float(timeout)
            if request_options.max_retries is not None:
                value = request_options.max_retries
                if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 10:
                    raise ValueError("max_retries must be an integer between 0 and 10")
                max_retries = value
            self._merge_request_headers(headers, request_options.headers)
            if not isinstance(request_options.query_params, Mapping):
                raise TypeError("request option query_params must be a mapping")
            params = dict(request_kwargs.pop("params", None) or {})
            for name, value in request_options.query_params.items():
                self._validate_query_pair(name, value)
                if name in params:
                    raise ValueError(
                        f"request option query parameter {name} conflicts with a resource parameter"
                    )
                params[name] = value
            if params:
                request_kwargs["params"] = params
            cancel_event = request_options.cancel_event
            if cancel_event is not None and not isinstance(cancel_event, threading.Event):
                raise TypeError("cancel_event must be a threading.Event")
        auth_retried = False
        retry_count = 0
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise iCoDerRequestCancelledError("iCoDer request was cancelled")
            request_token = self.config.access_token
            if self.config.access_token:
                headers["Authorization"] = f"Bearer {self.config.access_token}"
            response = self.http.request(
                normalized_method,
                path,
                headers=headers,
                **request_kwargs,
            )
            if response.status_code == 401 and not auth_retried:
                auth_retried = True
                if self._refresh_after_401(request_token):
                    continue
            if retry_count < max_retries and self._should_retry(
                normalized_method, response, headers
            ):
                delay = self._retry_delay(response, retry_count)
                retry_count += 1
                if delay and cancel_event is not None:
                    if cancel_event.wait(delay):
                        raise iCoDerRequestCancelledError("iCoDer request was cancelled")
                elif delay:
                    time.sleep(delay)
                continue
            def typed_raise_for_status(bound_response: httpx.Response) -> httpx.Response:
                if bound_response.status_code >= 400:
                    raise api_error_from_response(bound_response)
                return bound_response

            response.raise_for_status = MethodType(  # type: ignore[method-assign]
                typed_raise_for_status,
                response,
            )
            return response

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs) -> httpx.Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)

    def close(self):
        self.http.close()

    @staticmethod
    def _validate_relative_path(path: str) -> None:
        if not isinstance(path, str):
            raise TypeError("request path must be a string")
        parsed = urlsplit(path)
        if (
            not path.startswith("/")
            or path.startswith("//")
            or "\\" in path
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "request path must be an absolute-path reference on the configured origin"
            )

    @classmethod
    def _merge_request_headers(
        cls,
        headers: httpx.Headers,
        additions,
    ) -> None:
        if not isinstance(additions, Mapping):
            raise TypeError("request option headers must be a mapping")
        existing = {name.lower() for name in headers.keys()}
        for raw_name, raw_value in additions.items():
            if (
                not isinstance(raw_name, str)
                or not raw_name.strip()
                or len(raw_name) > 128
                or re.fullmatch(r"[A-Za-z0-9!#$%&'*+.^_`|~-]+", raw_name.strip()) is None
            ):
                raise ValueError("request option headers contain an invalid name")
            name = raw_name.strip()
            if name.lower() in cls._PROTECTED_REQUEST_HEADERS:
                raise ValueError(f"request option header {name} is controlled by the SDK")
            if name.lower() in existing:
                raise ValueError(f"request option header {name} conflicts with a resource header")
            if not isinstance(raw_value, str) or len(raw_value) > 4096 \
                    or "\r" in raw_value or "\n" in raw_value:
                raise ValueError(f"request option header {name} has an invalid value")
            headers[name] = raw_value
            existing.add(name.lower())

    @staticmethod
    def _validate_query_pair(name, value) -> None:
        if not isinstance(name, str) or not name.strip() or len(name) > 128 \
                or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError("request option query_params contain an invalid name")
        if not isinstance(value, str) or len(value) > 8192:
            raise ValueError(f"request option query parameter {name} has an invalid value")
