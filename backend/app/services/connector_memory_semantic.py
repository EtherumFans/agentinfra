"""Governed remote embedding contract for persistent Memory retrieval.

The API process never imports sentence-transformers, Torch, FAISS or PyArrow.
An approved same-region service embeds already deidentified text and returns a
bounded normalized vector. Vectors are encrypted with the Memory row; tenant,
user, patient and consent identifiers are never sent to the embedding service.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload
from app.services.connector_executor import ConnectorExecutionError


MEMORY_EMBEDDING_REQUEST_CONTRACT = "icoder.memory-embedding.request/v1"
MEMORY_EMBEDDING_RESPONSE_CONTRACT = "icoder.memory-embedding.response/v1"
MIN_DIMENSIONS = 16
MAX_DIMENSIONS = 4096
MAX_TEXT_CHARS = 2000


class MemoryEmbeddingTransport(Protocol):
    async def post_json(
        self,
        *,
        base_url: str,
        expected_host: str,
        headers: dict[str, str],
        body: dict[str, Any],
        connect_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 15.0,
        max_response_bytes: int = 512 * 1024,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class MemoryEmbedding:
    vector: tuple[float, ...]
    model: str
    model_version: str
    dimensions: int


class GovernedMemoryEmbeddingProvider:
    """Call one fixed embedding endpoint with a strict, secret-free contract."""

    def __init__(
        self,
        transport: MemoryEmbeddingTransport,
        *,
        credential_resolver: Callable[[str], str | None],
        host_authorizer: Callable[[str], bool] | None = None,
        endpoint: str | None = None,
        allow_loopback_http_for_testing: bool = False,
    ) -> None:
        self._transport = transport
        self._credential_resolver = credential_resolver
        self._host_authorizer = host_authorizer or (lambda _host: True)
        self._endpoint = (
            endpoint
            if endpoint is not None
            else os.environ.get("ICODER_MEMORY_SEMANTIC_URL", "")
        ).strip()
        self._allow_loopback_http_for_testing = bool(
            allow_loopback_http_for_testing
        )

    async def embed(self, text: str) -> MemoryEmbedding:
        if not isinstance(text, str) or "\x00" in text:
            raise ConnectorExecutionError("CONNECTOR_MEMORY_SEMANTIC_INPUT_INVALID")
        normalized_text = " ".join(text.split())
        if not normalized_text or len(normalized_text) > MAX_TEXT_CHARS:
            raise ConnectorExecutionError("CONNECTOR_MEMORY_SEMANTIC_INPUT_INVALID")
        try:
            redaction = redact_payload(normalized_text)
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_SEMANTIC_DEIDENTIFICATION_FAILED"
            ) from exc
        if redaction.redaction_applied:
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_SEMANTIC_DEIDENTIFICATION_REQUIRED"
            )
        endpoint, host = self._validated_endpoint()
        if self._host_authorizer(host) is not True:
            raise ConnectorExecutionError("CONNECTOR_EGRESS_NOT_APPROVED")
        token = self._credential()
        response = await self._transport.post_json(
            base_url=endpoint,
            expected_host=host,
            headers={"Authorization": f"Bearer {token}"},
            body={
                "contract": MEMORY_EMBEDDING_REQUEST_CONTRACT,
                "texts": [normalized_text],
                "normalize": True,
            },
            total_timeout_seconds=15.0,
            max_response_bytes=256 * 1024,
        )
        return self._validate_response(response)

    def _validated_endpoint(self) -> tuple[str, str]:
        if not self._endpoint:
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_SEMANTIC_NOT_CONFIGURED"
            )
        try:
            parsed = urlsplit(self._endpoint)
            host = (parsed.hostname or "").rstrip(".").casefold()
            port = parsed.port
        except ValueError as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_SEMANTIC_NOT_CONFIGURED"
            ) from exc
        loopback_test = (
            self._allow_loopback_http_for_testing
            and parsed.scheme.casefold() == "http"
            and host in {"127.0.0.1", "localhost", "::1"}
            and port is not None
            and 1024 <= port <= 65535
        )
        if (
            not host
            or (parsed.scheme.casefold() != "https" and not loopback_test)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (not loopback_test and port not in (None, 443))
        ):
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_SEMANTIC_NOT_CONFIGURED"
            )
        return self._endpoint, host

    def _credential(self) -> str:
        try:
            token = self._credential_resolver("memory_semantic")
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_SEMANTIC_NOT_CONFIGURED"
            ) from exc
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 8192
            or any(char in token for char in "\r\n\x00")
        ):
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_SEMANTIC_NOT_CONFIGURED"
            )
        return token

    @staticmethod
    def _validate_response(response: dict[str, Any]) -> MemoryEmbedding:
        if set(response) - {
            "contract", "model", "model_version", "dimensions", "embeddings",
        }:
            raise ConnectorExecutionError("CONNECTOR_MEMORY_SEMANTIC_RESPONSE_INVALID")
        model = response.get("model")
        version = response.get("model_version")
        dimensions = response.get("dimensions")
        embeddings = response.get("embeddings")
        if (
            response.get("contract") != MEMORY_EMBEDDING_RESPONSE_CONTRACT
            or not isinstance(model, str)
            or not 1 <= len(model.strip()) <= 128
            or not isinstance(version, str)
            or not 1 <= len(version.strip()) <= 128
            or not isinstance(dimensions, int)
            or isinstance(dimensions, bool)
            or not MIN_DIMENSIONS <= dimensions <= MAX_DIMENSIONS
            or not isinstance(embeddings, list)
            or len(embeddings) != 1
            or not isinstance(embeddings[0], list)
            or len(embeddings[0]) != dimensions
        ):
            raise ConnectorExecutionError("CONNECTOR_MEMORY_SEMANTIC_RESPONSE_INVALID")
        vector: list[float] = []
        for value in embeddings[0]:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or abs(float(value)) > 1_000_000
            ):
                raise ConnectorExecutionError(
                    "CONNECTOR_MEMORY_SEMANTIC_RESPONSE_INVALID"
                )
            vector.append(float(value))
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isfinite(norm) or norm <= 1e-12:
            raise ConnectorExecutionError("CONNECTOR_MEMORY_SEMANTIC_RESPONSE_INVALID")
        normalized = tuple(value / norm for value in vector)
        return MemoryEmbedding(
            vector=normalized,
            model=model.strip(),
            model_version=version.strip(),
            dimensions=dimensions,
        )

    def status(self) -> dict[str, Any]:
        endpoint_configured = False
        host = ""
        try:
            _, host = self._validated_endpoint()
            endpoint_configured = True
        except ConnectorExecutionError:
            pass
        try:
            credential_configured = bool(
                self._credential_resolver("memory_semantic")
            )
        except Exception:
            credential_configured = False
        egress_approved = bool(host and self._host_authorizer(host) is True)
        return {
            "configured": bool(
                endpoint_configured and credential_configured and egress_approved
            ),
            "endpoint_configured": endpoint_configured,
            "credential_configured": credential_configured,
            "egress_approved": egress_approved,
            "request_contract": MEMORY_EMBEDDING_REQUEST_CONTRACT,
            "response_contract": MEMORY_EMBEDDING_RESPONSE_CONTRACT,
            "identifiers_sent": False,
            "deidentified_text_only": True,
            "native_ml_in_api_process": False,
            "live_external_verified": False,
        }


__all__ = [
    "GovernedMemoryEmbeddingProvider",
    "MEMORY_EMBEDDING_REQUEST_CONTRACT",
    "MEMORY_EMBEDDING_RESPONSE_CONTRACT",
    "MemoryEmbedding",
]
