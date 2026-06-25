"""IndexNavigatorExpert — iCoDer Runtime expert for Stage 2 of MedCodER.

For each disease_fact / procedure_fact from Stage 1, retrieve top-K
ICD candidate codes from the BGE-M3 + FAISS retriever. This is the
candidate-set producer; the actual ranking happens in Stage 4
(``code_reconciler_expert``).

Phase 2 / D2 — 4 atomic experts. Layered: the
:class:`CodingExpert` orchestrates 5 stages; this expert is the
"Stage 2 retrieve" building block.

Public contract
---------------
Same as :class:`CodingExpert` — sync ``__call__(invocation) -> dict``
for the Phase 1 Delegator, async ``invoke_async(facts, ctx) -> dict``
for the Phase 2 native path.

Error handling
--------------
Generic exceptions are translated to :class:`ExpertInvocationError`
with ``stage="retrieving"`` so the Delegator's retry / backoff layer
sees a uniform error type. Retriever-not-loaded is treated as a
graceful degradation: the call returns empty candidates rather than
raising — the upstream Aggregator decides whether to fall back to
prompt-only mode.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.icoder.agent_runtime.orchestrator.delegator import (
    ExpertInvocation,
    ExpertInvocationError,
)

if TYPE_CHECKING:
    from icoder_runtime.providers.medical_coding.medcoder_retriever import (
        MedCodERRetriever,
    )

logger = logging.getLogger(__name__)


class IndexNavigatorExpert:
    """Stage 2 retriever: disease text → top-K ICD candidate codes.

    Output schema (matches ``agent_pack.json#output_contract.candidates``):
        {
          "diagnosis_candidates": [
            {"fact": str, "candidates": [
                {"code": str, "name": str, "score": float,
                 "chapter": str, "match_type": "vector"}]
            }
          ],
          "procedure_candidates": [
            {"fact": str, "candidates": [
                {"code": str, "name": str, "score": float,
                 "chapter": str, "match_type": "vector"}]
            }
          ],
          "retriever_status": "ok" | "degraded" | "missing",
          "expert_id": "index-navigator",
        }
    """

    EXPERT_ID: str = "index-navigator"
    EXPERT_NAME: str = "Index Navigator (MedCodER Stage 2)"

    def __init__(
        self,
        retriever: "MedCodERRetriever | None" = None,
        *,
        default_top_k: int = 20,
        synonym_expansion: bool = True,
    ) -> None:
        """Construct the expert.

        ``retriever`` is injected so tests can pass a stub. When None,
        ``invoke_async`` returns ``retriever_status="missing"`` with
        empty candidate lists — same as what production would see on
        a fresh deployment with no FAISS index.
        """
        self._retriever = retriever
        self._default_top_k = default_top_k
        self._synonym_expansion = synonym_expansion

    # ── Phase 1 sync interface (Delegator still sync) ─────────────

    def invoke_sync(self, invocation: ExpertInvocation) -> dict:
        """Phase 1 entry — Delegator calls this with ``ExpertInvocation``.

        ``invocation.subtask_input`` is the JSON-serialized ``{"diagnosis_facts": [...],
        "procedure_facts": [...]}`` from Stage 1. ``invocation.context``
        may carry ``top_k`` (override) or ``expand_synonyms`` (override).
        """
        import json
        ctx = invocation.context or {}
        try:
            payload = json.loads(invocation.subtask_input) if invocation.subtask_input else {}
        except (ValueError, TypeError):
            payload = {}
        return self._run_sync(payload, ctx)

    __call__ = invoke_sync

    # ── Phase 2 async interface (native) ──────────────────────────

    async def invoke_async(
        self,
        facts: dict[str, list[dict]] | None = None,
        ctx: dict | None = None,
    ) -> dict:
        """Native async entry. Phase 2 will wire it directly.

        ``facts`` is the structured output of
        :class:`EvidenceExtractorExpert`: keys ``diagnosis_facts`` and
        ``procedure_facts`` (each a list of dicts with at least
        ``"fact"``/``"evidence_text"``).
        """
        facts = facts or {}
        ctx = ctx or {}
        try:
            return await self._navigate(facts, ctx)
        except ExpertInvocationError:
            raise
        except Exception as exc:  # translate to ExpertInvocationError
            logger.exception("IndexNavigatorExpert: navigation failed")
            raise ExpertInvocationError(
                f"IndexNavigatorExpert: navigation failed "
                f"[{type(exc).__name__}]: {exc}",
                stage="retrieving",
            ) from exc

    # ── helpers ───────────────────────────────────────────────────

    def _run_sync(self, facts: dict, ctx: dict) -> dict:
        async def _invoke() -> dict:
            return await self.invoke_async(facts, ctx)
        return asyncio.run(_invoke())

    async def _navigate(self, facts: dict, ctx: dict) -> dict:
        retriever = self._retriever
        if retriever is None:
            return self._empty_result("missing")

        # Health probe — non-raising
        try:
            retriever.ensure_loaded()
        except Exception as exc:  # noqa: BLE001
            logger.warning("IndexNavigatorExpert: ensure_loaded failed: %s", exc)
            return self._empty_result("degraded")
        if not retriever.is_loaded() or retriever._index is None:
            return self._empty_result("degraded")

        top_k = int(ctx.get("top_k") or self._default_top_k)
        expand = bool(ctx.get("expand_synonyms", self._synonym_expansion))

        dx_candidates, px_candidates = await asyncio.gather(
            self._retrieve_facts(
                facts.get("diagnosis_facts", []),
                top_k,
                expand,
            ),
            self._retrieve_facts(
                facts.get("procedure_facts", []),
                top_k,
                expand,
            ),
        )

        return {
            "diagnosis_candidates": dx_candidates,
            "procedure_candidates": px_candidates,
            "retriever_status": "ok",
            "expert_id": self.EXPERT_ID,
        }

    async def _retrieve_facts(
        self,
        facts: list[dict],
        top_k: int,
        expand_synonyms: bool,
    ) -> list[dict]:
        """Run the retriever for each fact in parallel.

        Per-fact results are returned in input order. The retriever
        itself is sync-async wrapped, so a small asyncio.gather fan-out
        is the simplest way to keep wall-time ~max(per-fact) without
        serializing.
        """
        if not facts:
            return []

        async def _one(fact: dict) -> dict:
            text = (fact.get("fact") or fact.get("evidence_text") or "").strip()
            if not text:
                return {"fact": text, "candidates": []}
            try:
                cands = await self._retriever.retrieve_async(
                    text, top_k=top_k, expand_synonyms=expand_synonyms,
                )
            except Exception as exc:  # noqa: BLE001 — per-fact fallback
                logger.warning(
                    "IndexNavigatorExpert: retrieve failed for fact %r: %s",
                    text[:30], exc,
                )
                return {"fact": text, "candidates": []}
            return {
                "fact": text,
                "candidates": [
                    {
                        "code": c.code,
                        "name": c.name,
                        "score": float(c.score),
                        "chapter": c.chapter,
                        "match_type": "vector",
                    }
                    for c in cands
                ],
            }

        return list(await asyncio.gather(*[_one(f) for f in facts]))

    @staticmethod
    def _empty_result(status: str) -> dict:
        return {
            "diagnosis_candidates": [],
            "procedure_candidates": [],
            "retriever_status": status,
            "expert_id": "index-navigator",
        }


__all__ = ["IndexNavigatorExpert"]
