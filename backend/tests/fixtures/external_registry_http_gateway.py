"""Native-free real-HTTP fixture for the external Registry gateway contract."""
from __future__ import annotations

import os

from fastapi import FastAPI, Header, HTTPException

from app.services.connector_external_registry import (
    GATEWAY_REQUEST_CONTRACT,
    GATEWAY_RESPONSE_CONTRACT,
)


app = FastAPI(title="iCoDer external Registry contract fixture")
_token = os.environ.get("EXTERNAL_REGISTRY_FIXTURE_TOKEN", "fixture-token")
_counts = {"drugbank": 0, "posos": 0, "web-search": 0}


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    return {"ready": True, "contract": GATEWAY_RESPONSE_CONTRACT}


@app.get("/stats")
async def stats() -> dict[str, dict[str, int]]:
    return {"counts": dict(_counts)}


@app.post("/gateway/{provider}")
async def query_gateway(
    provider: str,
    payload: dict,
    authorization: str = Header(default=""),
) -> dict:
    if authorization != f"Bearer {_token}":
        raise HTTPException(status_code=401, detail="unauthorized")
    expected_operation = {
        "drugbank": "lookup", "posos": "guide", "web-search": "search",
    }.get(provider)
    if expected_operation is None:
        raise HTTPException(status_code=404, detail="provider not found")
    if (
        payload.get("contract") != GATEWAY_REQUEST_CONTRACT
        or payload.get("provider") != provider
        or payload.get("operation") != expected_operation
        or payload.get("region") not in {"CN", "EU", "US"}
        or not isinstance(payload.get("query"), str)
        or not isinstance(payload.get("max_results"), int)
    ):
        raise HTTPException(status_code=422, detail="contract invalid")
    _counts[provider] += 1
    results = {
        "drugbank": [{
            "drugbank_id": "DB00945",
            "name": "Aspirin",
            "description": "Contract fixture medicine",
            "indication": "Contract fixture indication",
            "interactions": [{
                "drug": "Warfarin",
                "severity": "major",
                "description": "Contract fixture interaction",
                "source_url": "https://go.drugbank.com/drugs/DB00945",
            }],
            "source_url": "https://go.drugbank.com/drugs/DB00945",
        }],
        "posos": [{
            "medication": "Metformin",
            "summary": "Contract fixture medication guidance",
            "contraindications": ["Contract fixture contraindication"],
            "interactions": ["Contract fixture interaction"],
            "citations": [{
                "title": "Contract fixture source",
                "url": "https://reference.example/medication",
            }],
        }],
        "web-search": [{
            "title": "Contract fixture clinical guidance",
            "url": "https://health.example/guidance",
            "snippet": "Contract fixture search result",
            "source": "Contract fixture authority",
            "published": "2026-08-22",
        }],
    }[provider]
    return {
        "contract": GATEWAY_RESPONSE_CONTRACT,
        "provider": provider,
        "total_available": len(results),
        "results": results[: payload["max_results"]],
    }
