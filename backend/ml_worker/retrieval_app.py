"""Standalone Linux service for BGE-M3 + FAISS retrieval.

Run only in the dedicated ML image.  The main API image must not import this
module or install its native dependencies.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from icoder_runtime.providers.medical_coding.remote_retriever import (
    REMOTE_RETRIEVER_SCHEMA,
    SUPPORTED_CODE_SYSTEMS,
)


logger = logging.getLogger(__name__)
WORKER_VERSION = "1.0.0"
ASSET_MANIFEST_SCHEMA = "icoder.medcoder-assets/v1"
REQUIRED_ASSET_FILES = frozenset({
    "faiss.index",
    "metadata.pkl",
    "faiss_icd9cm3.index",
    "metadata_icd9cm3.pkl",
})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_asset_manifest(index_dir: str | Path, expected_version: str) -> None:
    """Verify immutable index/model provenance before importing native ML."""
    root = Path(index_dir).resolve()
    manifest_path = root / "asset_manifest.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("asset manifest unavailable") from exc
    if payload.get("schema_version") != ASSET_MANIFEST_SCHEMA:
        raise RuntimeError("asset manifest schema mismatch")
    if payload.get("index_version") != expected_version:
        raise RuntimeError("asset manifest index version mismatch")
    model = payload.get("embedding_model")
    expected_revision = os.environ.get("MEDCODER_BGE_REVISION", "").strip()
    if (
        not isinstance(model, dict)
        or model.get("repository") != "BAAI/bge-m3"
        or not expected_revision
        or model.get("revision") != expected_revision
        or model.get("dimension") != 1024
    ):
        raise RuntimeError("asset manifest model provenance mismatch")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != REQUIRED_ASSET_FILES:
        raise RuntimeError("asset manifest artifact set mismatch")
    for relative_name, metadata in artifacts.items():
        if not isinstance(metadata, dict):
            raise RuntimeError("asset manifest artifact metadata invalid")
        path = (root / relative_name).resolve()
        if path.parent != root or not path.is_file():
            raise RuntimeError("asset manifest artifact unavailable")
        expected_size = metadata.get("size_bytes")
        expected_digest = str(metadata.get("sha256") or "").casefold()
        if (
            not isinstance(expected_size, int)
            or expected_size <= 0
            or path.stat().st_size != expected_size
            or len(expected_digest) != 64
            or _sha256(path) != expected_digest
        ):
            raise RuntimeError("asset manifest artifact integrity failure")


class RetrieveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=512)
    top_k: int = Field(default=20, ge=1, le=50)
    expand_synonyms: bool = True
    code_system: Literal["ICD-10-CN", "ICD-9-CM-3-CN"] = "ICD-10-CN"

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must contain non-whitespace text")
        return normalized


class CandidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(default="", max_length=256)
    score: float = Field(ge=-1.0, le=1.0)
    chapter: str = Field(default="", max_length=256)
    source: Literal["retrieve"] = "retrieve"


class RetrieveResponse(BaseModel):
    schema_version: Literal["icoder.medcoder-retrieval/v1"] = REMOTE_RETRIEVER_SCHEMA
    worker_version: str = WORKER_VERSION
    index_version: str
    code_system: Literal["ICD-10-CN", "ICD-9-CM-3-CN"]
    candidates: list[CandidatePayload]


def _serialize_candidate(candidate: Any) -> CandidatePayload:
    if hasattr(candidate, "to_dict"):
        raw = candidate.to_dict()
    elif isinstance(candidate, dict):
        raw = candidate
    else:
        raise ValueError("unsupported candidate type")
    return CandidatePayload(
        code=str(raw.get("code") or ""),
        name=str(raw.get("name") or ""),
        score=float(raw.get("score")),
        chapter=str(raw.get("chapter") or ""),
        source="retrieve",
    )


def create_app(
    *,
    diagnosis_retriever: Any | None = None,
    procedure_retriever: Any | None = None,
    service_token: str | None = None,
    warmup: bool | None = None,
    index_version: str | None = None,
) -> FastAPI:
    """Create the worker app; injected retrievers keep tests native-free."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        token = service_token
        if token is None:
            token = os.environ.get("MEDCODER_RETRIEVER_TOKEN", "")
        token = (token or "").strip()
        app.state.service_token = token if 32 <= len(token) <= 512 else ""
        configured_index_version = index_version
        if configured_index_version is None:
            configured_index_version = os.environ.get("MEDCODER_INDEX_VERSION", "")
        configured_index_version = (configured_index_version or "").strip()
        app.state.index_version = configured_index_version
        app.state.configuration_errors = []
        if not app.state.service_token:
            app.state.configuration_errors.append("credential_invalid")
        app.state.index_version_configured = not (
            not configured_index_version
            or configured_index_version.casefold() == "unversioned"
            or len(configured_index_version) > 128
        )
        if not app.state.index_version_configured:
            app.state.configuration_errors.append("index_version_invalid")
        try:
            queue_timeout = float(
                os.environ.get("MEDCODER_WORKER_QUEUE_TIMEOUT_SECONDS", "5")
            )
        except ValueError as exc:
            raise RuntimeError("invalid MEDCODER_WORKER_QUEUE_TIMEOUT_SECONDS") from exc
        if not 0.1 <= queue_timeout <= 30.0:
            raise RuntimeError(
                "MEDCODER_WORKER_QUEUE_TIMEOUT_SECONDS must be between 0.1 and 30"
            )
        app.state.queue_timeout_seconds = queue_timeout
        app.state.retrieval_lock = asyncio.Lock()
        app.state.retrievers = {}
        app.state.readiness = {
            "ICD-10-CN": {"ready": False, "reason": "not_loaded"},
            "ICD-9-CM-3-CN": {"ready": False, "reason": "not_loaded"},
        }

        if app.state.configuration_errors:
            reason = ",".join(app.state.configuration_errors)
            app.state.readiness = {
                code_system: {"ready": False, "reason": reason}
                for code_system in SUPPORTED_CODE_SYSTEMS
            }
            yield
            app.state.retrievers = {}
            return

        using_real_native_retrievers = (
            diagnosis_retriever is None or procedure_retriever is None
        )
        if using_real_native_retrievers:
            index_dir = os.environ.get("MEDCODER_INDEX_DIR", "data/medcoder")
            try:
                await asyncio.to_thread(
                    verify_asset_manifest,
                    index_dir,
                    configured_index_version,
                )
            except Exception as exc:
                logger.error(
                    "retrieval asset verification failed error_type=%s",
                    type(exc).__name__,
                )
                app.state.readiness = {
                    code_system: {
                        "ready": False,
                        "reason": "asset_integrity_verification_failed",
                    }
                    for code_system in SUPPORTED_CODE_SYSTEMS
                }
                yield
                app.state.retrievers = {}
                return

        diag = diagnosis_retriever
        proc = procedure_retriever
        if diag is None or proc is None:
            from icoder_runtime.providers.medical_coding.medcoder_retriever import (
                MedCodERICD9CM3Retriever,
                MedCodERRetriever,
            )

            index_dir = os.environ.get("MEDCODER_INDEX_DIR", "data/medcoder")
            diag = diag or MedCodERRetriever(index_dir=index_dir)
            proc = proc or MedCodERICD9CM3Retriever(index_dir=index_dir)

        should_warm = warmup
        if should_warm is None:
            should_warm = os.environ.get("MEDCODER_WORKER_WARMUP", "0") == "1"
        warmup_queries = {
            "ICD-10-CN": "心力衰竭",
            "ICD-9-CM-3-CN": "胆囊切除术",
        }
        for code_system, retriever in (
            ("ICD-10-CN", diag),
            ("ICD-9-CM-3-CN", proc),
        ):
            try:
                await asyncio.to_thread(retriever.ensure_loaded)
                if should_warm:
                    # Loading the FAISS index alone does not initialize the
                    # sentence-transformer model.  A bounded one-result probe
                    # makes readiness mean the complete native path worked.
                    await asyncio.to_thread(
                        retriever.retrieve_sync,
                        warmup_queries[code_system],
                        1,
                        False,
                    )
                app.state.retrievers[code_system] = retriever
                app.state.readiness[code_system] = {"ready": True, "reason": ""}
            except Exception as exc:  # fail one code system independently
                logger.error(
                    "retriever startup failed code_system=%s error_type=%s",
                    code_system,
                    type(exc).__name__,
                )
                app.state.readiness[code_system] = {
                    "ready": False,
                    "reason": f"startup_{type(exc).__name__}",
                }
        yield
        app.state.retrievers = {}

    worker = FastAPI(
        title="iCoDer MedCodER Retrieval Worker",
        version=WORKER_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    async def require_token(
        authorization: str | None = Header(default=None),
    ) -> None:
        expected = str(getattr(worker.state, "service_token", "") or "")
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="retrieval service credential is not configured",
            )
        prefix = "Bearer "
        provided = authorization[len(prefix):] if authorization and authorization.startswith(prefix) else ""
        if not provided or not hmac.compare_digest(provided, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
            )

    @worker.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "alive",
            "schema_version": REMOTE_RETRIEVER_SCHEMA,
            "worker_version": WORKER_VERSION,
        }

    @worker.get("/readyz")
    async def readyz(response: Response) -> dict[str, Any]:
        readiness = dict(getattr(worker.state, "readiness", {}))
        configured = bool(getattr(worker.state, "service_token", ""))
        index_version_configured = bool(
            getattr(worker.state, "index_version_configured", False)
        )
        all_ready = configured and index_version_configured and all(
            bool(item.get("ready")) for item in readiness.values()
        )
        if not all_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ready" if all_ready else "degraded",
            "ready": all_ready,
            "credential_configured": configured,
            "index_version_configured": index_version_configured,
            "schema_version": REMOTE_RETRIEVER_SCHEMA,
            "worker_version": WORKER_VERSION,
            "index_version": getattr(worker.state, "index_version", ""),
            "code_systems": readiness,
        }

    @worker.post("/v1/retrieve", response_model=RetrieveResponse)
    async def retrieve(
        request: RetrieveRequest,
        _: None = Depends(require_token),
    ) -> RetrieveResponse:
        if request.code_system not in SUPPORTED_CODE_SYSTEMS:
            raise HTTPException(status_code=422, detail="unsupported code system")
        readiness = worker.state.readiness.get(request.code_system) or {}
        retriever = worker.state.retrievers.get(request.code_system)
        if not readiness.get("ready") or retriever is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="requested retrieval index is unavailable",
            )
        lock: asyncio.Lock = worker.state.retrieval_lock
        try:
            await asyncio.wait_for(
                lock.acquire(), timeout=worker.state.queue_timeout_seconds
            )
        except TimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="retrieval worker is busy",
            ) from exc
        try:
            candidates = await asyncio.to_thread(
                retriever.retrieve_sync,
                request.query,
                request.top_k,
                request.expand_synonyms,
            )
        except Exception as exc:
            logger.error(
                "retrieval failed code_system=%s error_type=%s",
                request.code_system,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="retrieval execution failed",
            ) from exc
        finally:
            lock.release()
        try:
            serialized = [_serialize_candidate(item) for item in candidates]
            if len(serialized) > request.top_k:
                serialized = serialized[: request.top_k]
            codes = [item.code for item in serialized]
            if len(codes) != len(set(codes)):
                raise ValueError("duplicate candidate code")
        except (TypeError, ValueError) as exc:
            logger.error(
                "retrieval serialization failed code_system=%s error_type=%s",
                request.code_system,
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="retrieval response validation failed",
            ) from exc
        return RetrieveResponse(
            index_version=worker.state.index_version,
            code_system=request.code_system,
            candidates=serialized,
        )

    return worker


app = create_app()


__all__ = [
    "ASSET_MANIFEST_SCHEMA",
    "WORKER_VERSION",
    "app",
    "create_app",
    "verify_asset_manifest",
]
