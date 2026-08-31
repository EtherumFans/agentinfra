"""Governed public Registry providers with fixed-host outbound contracts."""
from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol

from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload
from app.services.connector_executor import ConnectorExecutionError, ConnectorInvocation


PUBMED_HOST = "eutils.ncbi.nlm.nih.gov"
PUBMED_ESEARCH_URL = f"https://{PUBMED_HOST}/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = f"https://{PUBMED_HOST}/entrez/eutils/esummary.fcgi"
CLINICAL_TRIALS_HOST = "clinicaltrials.gov"
CLINICAL_TRIALS_URL = f"https://{CLINICAL_TRIALS_HOST}/api/v2/studies"
CLINICAL_TRIALS_FIELDS = (
    "NCTId,BriefTitle,OverallStatus,Phase,StudyType,Condition,InterventionName"
)
PUBLIC_REGISTRY_KEYS = frozenset({"pubmed", "clinical-trials"})
MAX_QUERY_CHARS = 500
MAX_RESULTS = 20
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RegistryJSONTransport(Protocol):
    async def get_json(
        self,
        *,
        base_url: str,
        expected_host: str,
        params: dict[str, str | int],
        connect_timeout_seconds: float = 5.0,
        total_timeout_seconds: float = 15.0,
        max_response_bytes: int = 512 * 1024,
    ) -> dict[str, Any]: ...


class _RateGate:
    def __init__(
        self,
        interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._interval = max(0.0, interval_seconds)
        self._clock = clock
        self._sleeper = sleeper
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self._interval - self._clock()
            if delay > 0:
                await self._sleeper(delay)
            self._last = self._clock()


def _text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:maximum]


def _string_list(value: object, *, maximum_items: int, maximum_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value[:maximum_items]:
        text = _text(item, maximum_chars)
        if text:
            output.append(text)
    return output


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class GovernedPublicRegistryProvider:
    """Read-only PubMed and ClinicalTrials.gov provider.

    Queries must already be classified as deidentified and must not trigger
    the runtime's PHI detector. Hosts, paths, parameters and returned fields
    are server-owned; Agents cannot provide URLs or headers.
    """

    def __init__(
        self,
        transport: RegistryJSONTransport,
        *,
        ncbi_contact_email: str | None = None,
        ncbi_rate_interval_seconds: float = 0.34,
        clinical_trials_rate_interval_seconds: float = 0.2,
        host_authorizer: Callable[[str], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._transport = transport
        self._ncbi_email = (
            ncbi_contact_email
            if ncbi_contact_email is not None
            else os.environ.get("ICODER_NCBI_CONTACT_EMAIL", "")
        ).strip()
        self._host_authorizer = host_authorizer or (lambda _host: True)
        self._ncbi_gate = _RateGate(
            ncbi_rate_interval_seconds, clock=clock, sleeper=sleeper,
        )
        self._clinical_trials_gate = _RateGate(
            clinical_trials_rate_interval_seconds, clock=clock, sleeper=sleeper,
        )

    async def __call__(
        self,
        registry_key: str,
        invocation: ConnectorInvocation,
    ) -> dict[str, Any]:
        query, max_results = self._validate_invocation(invocation)
        if registry_key == "pubmed":
            return await self._search_pubmed(query, max_results)
        if registry_key == "clinical-trials":
            return await self._search_clinical_trials(query, max_results)
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_ENTRY_UNAVAILABLE")

    @staticmethod
    def _validate_invocation(invocation: ConnectorInvocation) -> tuple[str, int]:
        if invocation.operation != "search":
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_OPERATION_NOT_ALLOWED")
        arguments = invocation.arguments
        if not isinstance(arguments, dict) or set(arguments) - {"query", "max_results"}:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        query = arguments.get("query")
        max_results = arguments.get("max_results", 10)
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > MAX_QUERY_CHARS
            or any(char in query for char in "\r\n\x00")
            or not isinstance(max_results, int)
            or isinstance(max_results, bool)
            or not 1 <= max_results <= MAX_RESULTS
        ):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        if invocation.data_classification != "deidentified":
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED"
            )
        try:
            redaction = redact_payload(query)
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_DEIDENTIFICATION_CHECK_FAILED"
            ) from exc
        if redaction.redaction_applied or "<REDACTED:" in query.upper():
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED"
            )
        return query.strip(), max_results

    async def _search_pubmed(self, query: str, max_results: int) -> dict[str, Any]:
        if self._host_authorizer(PUBMED_HOST) is not True:
            raise ConnectorExecutionError("CONNECTOR_EGRESS_NOT_APPROVED")
        if (
            not self._ncbi_email
            or len(self._ncbi_email) > 254
            or _EMAIL_RE.fullmatch(self._ncbi_email) is None
        ):
            raise ConnectorExecutionError(
                "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED"
            )
        common = {
            "db": "pubmed",
            "retmode": "json",
            "tool": "iCoDer_Agent_Hub",
            "email": self._ncbi_email,
        }
        await self._ncbi_gate.wait()
        search = await self._transport.get_json(
            base_url=PUBMED_ESEARCH_URL,
            expected_host=PUBMED_HOST,
            params={
                **common,
                "term": query,
                "retmax": max_results,
                "sort": "relevance",
            },
            max_response_bytes=256 * 1024,
        )
        search_result = _object(search.get("esearchresult"))
        raw_ids = search_result.get("idlist")
        raw_count = search_result.get("count", "0")
        if not isinstance(raw_ids, list) or not isinstance(raw_count, (str, int)):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        pmids = [item for item in raw_ids if isinstance(item, str) and item.isdigit()]
        if len(pmids) != len(raw_ids) or len(pmids) > max_results:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        try:
            total_available = int(raw_count)
        except (TypeError, ValueError) as exc:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID") from exc
        if not 0 <= total_available <= 1_000_000_000:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        if not pmids:
            return self._pubmed_output(query, total_available, [])

        await self._ncbi_gate.wait()
        summary = await self._transport.get_json(
            base_url=PUBMED_ESUMMARY_URL,
            expected_host=PUBMED_HOST,
            params={**common, "id": ",".join(pmids)},
            max_response_bytes=512 * 1024,
        )
        result = _object(summary.get("result"))
        uids = result.get("uids")
        if not isinstance(uids, list) or any(uid not in pmids for uid in uids):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        articles: list[dict[str, Any]] = []
        for uid in uids:
            entry = _object(result.get(uid))
            raw_authors = entry.get("authors")
            authors = []
            if isinstance(raw_authors, list):
                authors = [
                    _text(_object(author).get("name"), 160)
                    for author in raw_authors[:8]
                    if _text(_object(author).get("name"), 160)
                ]
            articles.append({
                "pmid": uid,
                "title": _text(entry.get("title"), 1000),
                "journal": _text(
                    entry.get("fulljournalname") or entry.get("source"), 300,
                ),
                "published": _text(entry.get("pubdate"), 64),
                "authors": authors,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
            })
        return self._pubmed_output(query, total_available, articles)

    @staticmethod
    def _pubmed_output(
        query: str,
        total_available: int,
        articles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "provider": "NCBI PubMed",
            "query": query,
            "total_available": total_available,
            "returned": len(articles),
            "articles": articles,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "authoritative": False,
            "clinical_use": "literature_reference_clinician_review_required",
            "disclaimer": (
                "Reference metadata only; verify the source record and applicable "
                "clinical guidance before use."
            ),
            "source_endpoint": PUBMED_ESEARCH_URL,
        }

    async def _search_clinical_trials(
        self, query: str, max_results: int,
    ) -> dict[str, Any]:
        if self._host_authorizer(CLINICAL_TRIALS_HOST) is not True:
            raise ConnectorExecutionError("CONNECTOR_EGRESS_NOT_APPROVED")
        await self._clinical_trials_gate.wait()
        response = await self._transport.get_json(
            base_url=CLINICAL_TRIALS_URL,
            expected_host=CLINICAL_TRIALS_HOST,
            params={
                "query.term": query,
                "countTotal": "true",
                "pageSize": max_results,
                "format": "json",
                "fields": CLINICAL_TRIALS_FIELDS,
            },
            max_response_bytes=1024 * 1024,
        )
        studies = response.get("studies")
        total_count = response.get("totalCount", 0)
        if not isinstance(studies, list) or len(studies) > max_results:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        if not isinstance(total_count, int) or isinstance(total_count, bool) or total_count < 0:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
        trials: list[dict[str, Any]] = []
        for study in studies:
            if not isinstance(study, dict):
                raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
            protocol = _object(study.get("protocolSection"))
            identification = _object(protocol.get("identificationModule"))
            status = _object(protocol.get("statusModule"))
            design = _object(protocol.get("designModule"))
            conditions = _object(protocol.get("conditionsModule"))
            arms = _object(protocol.get("armsInterventionsModule"))
            nct_id = _text(identification.get("nctId"), 32)
            if not re.fullmatch(r"NCT\d{8}", nct_id):
                raise ConnectorExecutionError("CONNECTOR_REGISTRY_RESPONSE_INVALID")
            interventions = []
            raw_interventions = arms.get("interventions")
            if isinstance(raw_interventions, list):
                interventions = [
                    _text(_object(item).get("name"), 300)
                    for item in raw_interventions[:12]
                    if _text(_object(item).get("name"), 300)
                ]
            trials.append({
                "nct_id": nct_id,
                "title": _text(identification.get("briefTitle"), 1000),
                "overall_status": _text(status.get("overallStatus"), 64),
                "phases": _string_list(
                    design.get("phases"), maximum_items=8, maximum_chars=64,
                ),
                "study_type": _text(design.get("studyType"), 64),
                "conditions": _string_list(
                    conditions.get("conditions"),
                    maximum_items=20,
                    maximum_chars=300,
                ),
                "interventions": interventions,
                "url": f"https://clinicaltrials.gov/study/{nct_id}",
            })
        return {
            "provider": "ClinicalTrials.gov",
            "query": query,
            "total_available": total_count,
            "returned": len(trials),
            "trials": trials,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "authoritative": False,
            "clinical_use": "registry_listing_not_endorsement_clinician_review_required",
            "disclaimer": (
                "A registry listing is not government approval or evidence that an "
                "intervention is safe or effective; discuss risks and benefits with "
                "a qualified healthcare professional."
            ),
            "source_endpoint": CLINICAL_TRIALS_URL,
        }

    def status(self) -> dict[str, Any]:
        pubmed_egress = self._host_authorizer(PUBMED_HOST) is True
        clinical_trials_egress = (
            self._host_authorizer(CLINICAL_TRIALS_HOST) is True
        )
        contact_configured = bool(
            self._ncbi_email and _EMAIL_RE.fullmatch(self._ncbi_email)
        )
        return {
            "keys": sorted(PUBLIC_REGISTRY_KEYS),
            "pubmed_configured": contact_configured and pubmed_egress,
            "pubmed_contact_configured": contact_configured,
            "pubmed_egress_approved": pubmed_egress,
            "clinical_trials_configured": clinical_trials_egress,
            "clinical_trials_egress_approved": clinical_trials_egress,
            "deidentified_queries_only": True,
            "fixed_hosts": [CLINICAL_TRIALS_HOST, PUBMED_HOST],
            "live_external_verified": False,
        }


__all__ = [
    "CLINICAL_TRIALS_HOST",
    "CLINICAL_TRIALS_FIELDS",
    "CLINICAL_TRIALS_URL",
    "GovernedPublicRegistryProvider",
    "MAX_QUERY_CHARS",
    "MAX_RESULTS",
    "PUBMED_ESEARCH_URL",
    "PUBMED_ESUMMARY_URL",
    "PUBMED_HOST",
    "PUBLIC_REGISTRY_KEYS",
    "RegistryJSONTransport",
]
