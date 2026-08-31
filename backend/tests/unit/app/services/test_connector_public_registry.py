from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.connector_executor import ConnectorExecutionError, ConnectorInvocation
from app.services.connector_public_registry import (
    CLINICAL_TRIALS_FIELDS,
    CLINICAL_TRIALS_URL,
    GovernedPublicRegistryProvider,
    PUBMED_ESEARCH_URL,
    PUBMED_ESUMMARY_URL,
)


def _invocation(
    query: str = "ST elevation myocardial infarction",
    *,
    classification: str = "deidentified",
    arguments: dict | None = None,
) -> ConnectorInvocation:
    return ConnectorInvocation(
        organization_id="org-test",
        agent_id="agt-test",
        connector_id="con-test",
        operation="search",
        arguments=arguments or {"query": query, "max_results": 5},
        run_id="run-test",
        data_classification=classification,
        purpose_of_use="treatment",
    )


class _FakeTransport:
    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    async def get_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses[kwargs["base_url"]]


@pytest.mark.asyncio
async def test_pubmed_provider_uses_fixed_pipeline_and_projects_bounded_output():
    transport = _FakeTransport({
        PUBMED_ESEARCH_URL: {
            "esearchresult": {"count": "125", "idlist": ["123", "456"]},
        },
        PUBMED_ESUMMARY_URL: {
            "result": {
                "uids": ["123", "456"],
                "123": {
                    "title": "Trial one",
                    "fulljournalname": "Journal A",
                    "pubdate": "2025 Jan",
                    "authors": [{"name": "Author A"}],
                },
                "456": {
                    "title": "Trial two",
                    "source": "J B",
                    "pubdate": "2024",
                    "authors": [],
                },
            },
        },
    })
    provider = GovernedPublicRegistryProvider(
        transport,
        ncbi_contact_email="ops@example.org",
        ncbi_rate_interval_seconds=0,
    )

    result = await provider("pubmed", _invocation())

    assert result["provider"] == "NCBI PubMed"
    assert result["total_available"] == 125
    assert result["returned"] == 2
    assert result["articles"][0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/123/"
    assert result["authoritative"] is False
    assert [call["base_url"] for call in transport.calls] == [
        PUBMED_ESEARCH_URL,
        PUBMED_ESUMMARY_URL,
    ]
    assert transport.calls[0]["expected_host"] == "eutils.ncbi.nlm.nih.gov"
    assert transport.calls[0]["params"]["db"] == "pubmed"
    assert transport.calls[0]["params"]["tool"] == "iCoDer_Agent_Hub"
    assert transport.calls[1]["params"]["id"] == "123,456"


@pytest.mark.asyncio
async def test_clinical_trials_provider_projects_only_review_fields():
    transport = _FakeTransport({
        CLINICAL_TRIALS_URL: {
            "totalCount": 9,
            "studies": [{
                "protocolSection": {
                    "identificationModule": {
                        "nctId": "NCT01234567",
                        "briefTitle": "Example study",
                    },
                    "statusModule": {"overallStatus": "RECRUITING"},
                    "designModule": {
                        "phases": ["PHASE2"],
                        "studyType": "INTERVENTIONAL",
                    },
                    "conditionsModule": {"conditions": ["Hypertension"]},
                    "armsInterventionsModule": {
                        "interventions": [{"name": "Example drug"}],
                    },
                },
                "derivedSection": {"ignored": "not projected"},
            }],
        },
    })
    provider = GovernedPublicRegistryProvider(
        transport,
        ncbi_contact_email="ops@example.org",
        clinical_trials_rate_interval_seconds=0,
    )

    result = await provider("clinical-trials", _invocation("hypertension"))

    assert result["provider"] == "ClinicalTrials.gov"
    assert result["returned"] == 1
    assert result["trials"][0] == {
        "nct_id": "NCT01234567",
        "title": "Example study",
        "overall_status": "RECRUITING",
        "phases": ["PHASE2"],
        "study_type": "INTERVENTIONAL",
        "conditions": ["Hypertension"],
        "interventions": ["Example drug"],
        "url": "https://clinicaltrials.gov/study/NCT01234567",
    }
    assert transport.calls[0]["params"] == {
        "query.term": "hypertension",
        "countTotal": "true",
        "pageSize": 5,
        "format": "json",
        "fields": CLINICAL_TRIALS_FIELDS,
    }
    assert transport.calls[0]["max_response_bytes"] == 1024 * 1024


@pytest.mark.asyncio
async def test_public_registry_requires_deidentified_phi_free_minimal_query():
    transport = _FakeTransport({})
    provider = GovernedPublicRegistryProvider(
        transport,
        ncbi_contact_email="ops@example.org",
        ncbi_rate_interval_seconds=0,
    )

    cases = [
        replace(_invocation(), data_classification="non_phi"),
        _invocation("患者张三高血压相关研究"),
        _invocation(arguments={"query": "asthma", "url": "https://evil.example"}),
        _invocation(arguments={"query": "asthma", "max_results": 21}),
    ]
    expected = [
        "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED",
        "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED",
        "CONNECTOR_REGISTRY_ARGUMENTS_INVALID",
        "CONNECTOR_REGISTRY_ARGUMENTS_INVALID",
    ]
    for invocation, code in zip(cases, expected, strict=True):
        with pytest.raises(ConnectorExecutionError) as raised:
            await provider("pubmed", invocation)
        assert raised.value.code == code
    assert transport.calls == []


@pytest.mark.asyncio
async def test_pubmed_contact_and_upstream_shape_fail_closed():
    missing_contact_transport = _FakeTransport({})
    missing_contact = GovernedPublicRegistryProvider(
        missing_contact_transport,
        ncbi_contact_email="",
        ncbi_rate_interval_seconds=0,
    )
    with pytest.raises(ConnectorExecutionError) as not_configured:
        await missing_contact("pubmed", _invocation())
    assert not_configured.value.code == "CONNECTOR_REGISTRY_PROVIDER_NOT_CONFIGURED"
    assert missing_contact_transport.calls == []

    malformed_transport = _FakeTransport({
        PUBMED_ESEARCH_URL: {
            "esearchresult": {"count": "one", "idlist": ["123"]},
        },
    })
    malformed = GovernedPublicRegistryProvider(
        malformed_transport,
        ncbi_contact_email="ops@example.org",
        ncbi_rate_interval_seconds=0,
    )
    with pytest.raises(ConnectorExecutionError) as invalid:
        await malformed("pubmed", _invocation())
    assert invalid.value.code == "CONNECTOR_REGISTRY_RESPONSE_INVALID"


@pytest.mark.asyncio
async def test_public_registry_requires_runtime_exact_host_approval():
    transport = _FakeTransport({})
    provider = GovernedPublicRegistryProvider(
        transport,
        ncbi_contact_email="ops@example.org",
        host_authorizer=lambda _host: False,
        ncbi_rate_interval_seconds=0,
        clinical_trials_rate_interval_seconds=0,
    )
    for key in ("pubmed", "clinical-trials"):
        with pytest.raises(ConnectorExecutionError) as denied:
            await provider(key, _invocation())
        assert denied.value.code == "CONNECTOR_EGRESS_NOT_APPROVED"
    assert transport.calls == []
    status = provider.status()
    assert status["pubmed_configured"] is False
    assert status["clinical_trials_configured"] is False


def test_public_registry_status_is_secret_free_and_truthful():
    provider = GovernedPublicRegistryProvider(
        _FakeTransport({}),
        ncbi_contact_email="ops@example.org",
    )
    status = provider.status()
    assert status["pubmed_configured"] is True
    assert status["clinical_trials_configured"] is True
    assert status["deidentified_queries_only"] is True
    assert "ops@example.org" not in repr(status)
