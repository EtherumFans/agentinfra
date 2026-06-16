"""Coding-knowledge lookup endpoints — Corti's coding-expert (Search / Verify /
Guidelines / Explore) exposed standalone, over ICD-10-CN + ICD-9-CM-3.

These are pure deterministic *reference* lookups over the code catalog — NOT model
inference. No run is created, nothing is written back. They let a coder research a
code's instructional notes, official guideline, hierarchy and 易错 differentiation
without running a full record.

  GET /api/coding/search?q=<term>&limit=<n>   -> ranked catalog hits
  GET /api/coding/code/{code}                 -> verify + guideline + explore + alternatives
"""
from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..experts.coding_expert import CodingExpert
from ..experts.registry import default_expert_registry
from ..runtime.executor import AgentExecutor
from ..runtime.gateway import CredentialMissing, LLMGateway, ProviderError
from ..runtime.registry import default_registry
from ..runtime.runner import PHIRedactor
from .auth import require_auth

router = APIRouter(prefix="/api/coding", tags=["coding-lookup"])

_experts = default_expert_registry()
_agents = default_registry()

# The atomic fact-extraction agent runs the /extract surface by default.
DEFAULT_EXTRACT_AGENT = "icoder/diagnostic-entity-extractor-agent"


def _expert() -> CodingExpert:
    return cast(CodingExpert, _experts.get(CodingExpert.id))


@router.get("/search")
def search_codes(q: str = Query(..., min_length=1),
                 limit: int = Query(20, ge=1, le=50),
                 auth: dict = Depends(require_auth)):
    expert = _expert()
    term = q.strip()
    if not term:  # whitespace-only would otherwise substring-match every code
        return {"query": q, "hits": []}
    hits = expert.search(term)[:limit]
    out = []
    for h in hits:
        v = expert.verify(h["code"])
        out.append({
            "code": h["code"],
            "display": h["display"],
            "system": h["system"],
            "score": round(h["score"], 3),
            "high_risk": bool(v and v["high_risk"]),
            "code_type": v["code_type"] if v else None,
        })
    return {"query": q, "hits": out}


class ExtractRequest(BaseModel):
    text: str
    agent_id: str = DEFAULT_EXTRACT_AGENT


def _entities_from(red_text: str, items: list[tuple[str, str]], expert: CodingExpert) -> list[dict]:
    """Shared downstream of both extraction paths: anchor each (term, evidence_quote) to
    char spans server-side and classify by deterministic retrieval. Offsets are ALWAYS
    computed here via find_evidences — never taken from the model. Category is the top
    catalog match's code_type (诊断/手术操作), an entity *category*, not a billing code."""
    entities = []
    for term, quote in items:
        evs = expert.find_evidences(red_text, quote)
        hits = expert.search(term)
        category = None
        if hits:
            v = expert.verify(hits[0]["code"])
            category = v["code_type"] if v else None
        entities.append({"term": term, "category": category, "evidences": evs})
    # Reading order: by first evidence offset.
    entities.sort(key=lambda e: e["evidences"][0].start if e["evidences"] else 10**9)
    return entities


@router.post("/extract")
def extract_facts(body: ExtractRequest, auth: dict = Depends(require_auth)):
    """Fact Extraction — the iCoDer analog of Corti's Fact Extraction, on-prem and
    coding-aware. Returns *facts*, not billing codes, and no compliance gate — a clean
    structured-abstraction surface upstream of coding.

    Two paths, identical output shape:
    - With an external LLM configured (chat-capable provider): the Corti-style tool-calling
      executor drives the 医疗事实抽取 Agent — PHI is redacted server-side first, the model
      researches terms via coding-expert tools and submits facts via submit_findings.
    - With no key: deterministic local extraction (lexicon scan) so the slice stays runnable
      offline / in tests. Either way entity category comes from deterministic retrieval, never
      a fabricated prediction, and char offsets are anchored server-side."""
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text is required")
    expert = _expert()
    gateway = LLMGateway.from_env(expert.lexicon())
    provider = gateway.provider

    if hasattr(provider, "chat"):
        agent = _agents.get(body.agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail="unknown agent")
        try:
            result = AgentExecutor(provider).run(agent, body.text)
        except ProviderError as exc:
            # endpoint unreachable / non-2xx — surface plainly (no key leaked), never 500.
            raise HTTPException(status_code=503,
                                detail={"code": "llm_unavailable", "message": str(exc)})
        red_text = result.redaction_text
        phi = result.phi
        items = [
            (e.get("term", ""), e.get("evidence_quote", ""))
            for e in ((result.findings or {}).get("entities") or [])
            if isinstance(e, dict)
        ]
    else:
        red_text, phi = PHIRedactor().redact_typed(body.text)
        try:
            extractions = gateway.extract(red_text)
        except CredentialMissing as exc:
            raise HTTPException(status_code=503,
                                detail={"code": "llm_credential_missing", "message": str(exc)})
        items = [(ex.term, ex.evidence_text) for ex in extractions]

    entities = _entities_from(red_text, items, expert)
    return {
        "provider": provider.name,
        "redaction": {
            "spans": sum(p["count"] for p in phi),
            "by_type": phi,
            "text": red_text,
        },
        "entities": entities,
    }


@router.get("/code/{code}")
def code_detail(code: str, auth: dict = Depends(require_auth)):
    expert = _expert()
    v = expert.verify(code)
    if not v:
        raise HTTPException(status_code=404, detail="unknown code")
    g = expert.guidelines(code) or {}
    ex = expert.explore(code) or {}

    def rel(c: str | None) -> dict | None:
        # enrich a related code with its display + membership, so the UI can render
        # a navigable hierarchy (member codes are clickable, category codes are not)
        if not c:
            return None
        rv = expert.verify(c)
        return {"code": c, "display": rv["display"] if rv else None, "member": rv is not None}

    return {
        "code": v["code"],
        "display": v["display"],
        "system": v["system"],
        "code_type": v["code_type"],
        "high_risk": v["high_risk"],
        "notes": v["notes"],  # list[CodeNote]; FastAPI jsonable_encoder serializes nested models
        "guideline": g.get("guideline", ""),
        "parent": rel(ex.get("parent")),
        "siblings": [rel(c) for c in ex.get("siblings", [])],
        "children": [rel(c) for c in ex.get("children", [])],
        "alternatives": expert.alternatives(code),  # list[Alternative]
    }
