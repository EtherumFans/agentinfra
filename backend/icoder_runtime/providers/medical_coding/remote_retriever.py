"""HTTP client for the isolated MedCodER BGE/FAISS retrieval service.

This module is deliberately free of Torch, sentence-transformers, FAISS and
PyArrow imports.  The API process can therefore use semantic retrieval while
the native model stack remains in a separately built/scanned Linux worker.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from official_agents.medical_coding.schema import CandidateCode


REMOTE_RETRIEVER_SCHEMA = "icoder.medcoder-retrieval/v1"
SUPPORTED_CODE_SYSTEMS = frozenset({"ICD-10-CN", "ICD-9-CM-3-CN"})


class RemoteRetrieverError(RuntimeError):
    """Stable fail-closed error raised for transport or contract failures."""


@dataclass(frozen=True)
class RemoteRetrieverHealth:
    ready: bool
    reason: str
    code_system: str
    worker_version: str = ""
    index_version: str = ""


class RemoteMedCodERRetriever:
    """Retriever-compatible client backed by an isolated HTTP worker."""

    def __init__(
        self,
        base_url: str,
        *,
        code_system: str = "ICD-10-CN",
        token: str = "",
        timeout_seconds: float = 15.0,
        allow_http: bool | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.code_system = str(code_system or "").upper()
        self.token = (token or "").strip()
        self.timeout_seconds = float(timeout_seconds)
        self._transport = transport
        self._validate_configuration(allow_http)

    @classmethod
    def from_env(cls, *, code_system: str) -> "RemoteMedCodERRetriever":
        timeout_raw = os.environ.get("MEDCODER_RETRIEVER_TIMEOUT_SECONDS", "15")
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise RemoteRetrieverError(
                "invalid MEDCODER_RETRIEVER_TIMEOUT_SECONDS"
            ) from exc
        return cls(
            os.environ.get("MEDCODER_RETRIEVER_URL", ""),
            code_system=code_system,
            token=os.environ.get("MEDCODER_RETRIEVER_TOKEN", ""),
            timeout_seconds=timeout,
            allow_http=os.environ.get("MEDCODER_RETRIEVER_ALLOW_HTTP") == "1",
        )

    def _validate_configuration(self, allow_http: bool | None) -> None:
        if self.code_system not in SUPPORTED_CODE_SYSTEMS:
            raise RemoteRetrieverError("unsupported code system")
        if not (0.1 <= self.timeout_seconds <= 120.0):
            raise RemoteRetrieverError("retriever timeout must be between 0.1 and 120 seconds")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise RemoteRetrieverError("retriever URL must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise RemoteRetrieverError("retriever URL must not contain credentials, query or fragment")
        local_hosts = {"127.0.0.1", "localhost", "::1"}
        http_allowed = bool(allow_http) or parsed.hostname in local_hosts
        if parsed.scheme != "https" and not http_allowed:
            raise RemoteRetrieverError(
                "plain HTTP retriever URL requires MEDCODER_RETRIEVER_ALLOW_HTTP=1"
            )
        if not 32 <= len(self.token) <= 512:
            raise RemoteRetrieverError(
                "MEDCODER_RETRIEVER_TOKEN must contain 32 to 512 characters"
            )

    async def retrieve_async(
        self,
        disease: str,
        top_k: int | None = None,
        expand_synonyms: bool = True,
    ) -> list[CandidateCode]:
        text = (disease or "").strip()
        if not text:
            return []
        if len(text) > 512:
            raise RemoteRetrieverError("retrieval query exceeds 512 characters")
        k = 20 if top_k is None else int(top_k)
        if not 1 <= k <= 50:
            raise RemoteRetrieverError("top_k must be between 1 and 50")
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/v1/retrieve",
                    headers=headers,
                    json={
                        "query": text,
                        "top_k": k,
                        "expand_synonyms": bool(expand_synonyms),
                        "code_system": self.code_system,
                    },
                )
        except httpx.TimeoutException as exc:
            raise RemoteRetrieverError("remote retriever timeout") from exc
        except httpx.HTTPError as exc:
            raise RemoteRetrieverError("remote retriever transport failure") from exc
        if response.status_code != 200:
            raise RemoteRetrieverError(
                f"remote retriever unavailable (HTTP {response.status_code})"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise RemoteRetrieverError("remote retriever returned invalid JSON") from exc
        return self._validate_response(payload, expected_limit=k)

    async def health_async(self) -> RemoteRetrieverHealth:
        """Probe worker readiness without exposing the service token."""
        try:
            async with httpx.AsyncClient(
                timeout=min(self.timeout_seconds, 10.0),
                transport=self._transport,
            ) as client:
                response = await client.get(f"{self.base_url}/readyz")
        except httpx.TimeoutException:
            return RemoteRetrieverHealth(
                ready=False, reason="remote_retriever_timeout",
                code_system=self.code_system,
            )
        except httpx.HTTPError:
            return RemoteRetrieverHealth(
                ready=False, reason="remote_retriever_transport_failure",
                code_system=self.code_system,
            )
        if response.status_code != 200:
            return RemoteRetrieverHealth(
                ready=False, reason=f"remote_retriever_http_{response.status_code}",
                code_system=self.code_system,
            )
        try:
            payload = response.json()
        except ValueError:
            return RemoteRetrieverHealth(
                ready=False, reason="remote_retriever_invalid_json",
                code_system=self.code_system,
            )
        if not isinstance(payload, dict) or payload.get("schema_version") != REMOTE_RETRIEVER_SCHEMA:
            return RemoteRetrieverHealth(
                ready=False, reason="remote_retriever_schema_mismatch",
                code_system=self.code_system,
            )
        systems = payload.get("code_systems")
        system_health = systems.get(self.code_system) if isinstance(systems, dict) else None
        ready = bool(
            payload.get("ready") is True
            and isinstance(system_health, dict)
            and system_health.get("ready") is True
        )
        reason = ""
        if not ready:
            if isinstance(system_health, dict):
                reason = str(system_health.get("reason") or "remote_retriever_not_ready")
            else:
                reason = "remote_retriever_not_ready"
        return RemoteRetrieverHealth(
            ready=ready,
            reason=reason,
            code_system=self.code_system,
            worker_version=str(payload.get("worker_version") or ""),
            index_version=str(payload.get("index_version") or ""),
        )

    def retrieve_sync(
        self,
        disease: str,
        top_k: int | None = None,
        expand_synonyms: bool = True,
    ) -> list[CandidateCode]:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.retrieve_async(disease, top_k, expand_synonyms)
            )
        raise RemoteRetrieverError(
            "retrieve_sync cannot run inside an active event loop; use retrieve_async"
        )

    def _validate_response(
        self, payload: Any, *, expected_limit: int
    ) -> list[CandidateCode]:
        if not isinstance(payload, dict):
            raise RemoteRetrieverError("remote retriever response must be an object")
        if payload.get("schema_version") != REMOTE_RETRIEVER_SCHEMA:
            raise RemoteRetrieverError("remote retriever schema mismatch")
        for version_field in ("worker_version", "index_version"):
            version = payload.get(version_field)
            if not isinstance(version, str) or not version.strip() or len(version) > 128:
                raise RemoteRetrieverError(
                    f"remote retriever {version_field} is invalid"
                )
        if str(payload.get("code_system") or "").upper() != self.code_system:
            raise RemoteRetrieverError("remote retriever code-system mismatch")
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list) or len(raw_candidates) > expected_limit:
            raise RemoteRetrieverError("remote retriever candidates violate result limit")
        candidates: list[CandidateCode] = []
        seen: set[str] = set()
        for item in raw_candidates:
            if not isinstance(item, dict):
                raise RemoteRetrieverError("remote candidate must be an object")
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or "").strip()
            chapter = str(item.get("chapter") or "").strip()
            try:
                score = float(item.get("score"))
            except (TypeError, ValueError) as exc:
                raise RemoteRetrieverError("remote candidate score is invalid") from exc
            if (
                not code
                or len(code) > 32
                or len(name) > 256
                or len(chapter) > 256
                or not math.isfinite(score)
                or not -1.0 <= score <= 1.0
                or code in seen
            ):
                raise RemoteRetrieverError("remote candidate contract violation")
            seen.add(code)
            candidates.append(CandidateCode(
                code=code,
                name=name,
                score=score,
                chapter=chapter,
                source="retrieve",
            ))
        return candidates


__all__ = [
    "REMOTE_RETRIEVER_SCHEMA",
    "RemoteMedCodERRetriever",
    "RemoteRetrieverError",
    "RemoteRetrieverHealth",
    "SUPPORTED_CODE_SYSTEMS",
]
