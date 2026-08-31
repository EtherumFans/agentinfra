"""Native-free semantic-memory embedding contract fixture."""
from __future__ import annotations

import hashlib
import math
import os
import re
import sys

from fastapi import FastAPI, Header, HTTPException

from app.services.connector_memory_semantic import (
    MEMORY_EMBEDDING_REQUEST_CONTRACT,
    MEMORY_EMBEDDING_RESPONSE_CONTRACT,
)


app = FastAPI(title="iCoDer semantic Memory embedding fixture")
_token = os.environ.get("MEMORY_SEMANTIC_FIXTURE_TOKEN", "fixture-token")
_calls = 0
_saw_sensitive_phone = False
_last_request_keys: list[str] = []
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def _vector(text: str) -> list[float]:
    vector = [0.0] * 16
    lowered = text.casefold()
    concepts = (
        (("血糖", "糖尿病", "二甲双胍", "metformin", "diabetes"), 0),
        (("心衰", "心力衰竭", "heart failure"), 1),
        (("骨折", "fracture"), 2),
    )
    matched = False
    for terms, index in concepts:
        if any(term in lowered for term in terms):
            vector[index] = 1.0
            matched = True
    if not matched:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        for index in range(16):
            vector[index] = (digest[index] / 255.0) - 0.5
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    native = any(
        name == "torch" or name.startswith("sentence_transformers")
        or name.startswith("faiss") or name.startswith("pyarrow")
        for name in sys.modules
    )
    return {
        "ready": True,
        "contract": MEMORY_EMBEDDING_RESPONSE_CONTRACT,
        "native_modules_loaded": native,
    }


@app.get("/stats")
async def stats() -> dict[str, object]:
    return {
        "calls": _calls,
        "saw_sensitive_phone": _saw_sensitive_phone,
        "last_request_keys": list(_last_request_keys),
    }


@app.post("/v1/embed")
async def embed(
    payload: dict,
    authorization: str = Header(default=""),
) -> dict[str, object]:
    global _calls, _saw_sensitive_phone, _last_request_keys
    if authorization != f"Bearer {_token}":
        raise HTTPException(status_code=401, detail="unauthorized")
    texts = payload.get("texts")
    if (
        payload.get("contract") != MEMORY_EMBEDDING_REQUEST_CONTRACT
        or payload.get("normalize") is not True
        or not isinstance(texts, list)
        or len(texts) != 1
        or not isinstance(texts[0], str)
        or not texts[0]
    ):
        raise HTTPException(status_code=422, detail="contract invalid")
    _calls += 1
    _saw_sensitive_phone = _saw_sensitive_phone or bool(_PHONE_RE.search(texts[0]))
    _last_request_keys = sorted(payload)
    return {
        "contract": MEMORY_EMBEDDING_RESPONSE_CONTRACT,
        "model": "contract-multilingual-clinical",
        "model_version": "fixture-2026-08",
        "dimensions": 16,
        "embeddings": [_vector(texts[0])],
    }
