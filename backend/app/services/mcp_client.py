"""MCP Client — real external service connectors for Experts.

iCoDer Agentic Framework equivalent: MCP Server calls from Experts.
Currently supports:
- PubMed E-utilities (free, no API key required)
- Extensible to DrugBank, ClinicalTrials.gov, POSOS, Web Search
"""
import json
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# Base URLs for supported MCP services
MCP_ENDPOINTS = {
    "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
    "clinical_trials": "https://clinicaltrials.gov/api/v2",
    "drugbank": None,  # Requires API key
    "posos": None,  # Requires API key
    "web_search": None,  # Requires Brave/Bing API key
}

MCP_SOURCE_NAMES = {
    "pubmed": "PubMed",
    "clinical_trials": "ClinicalTrials.gov",
    "drugbank": "DrugBank",
    "posos": "Posos",
    "web_search": "Web Search",
}


class McpClient:
    """Real MCP server client for connecting Experts to external services."""

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=30.0)

    async def call(self, service: str, tool: str, params: dict) -> dict:
        """Call an MCP service tool and return structured results."""
        handler = getattr(self, f"_handle_{service}", None)
        if handler:
            try:
                return await handler(tool, params)
            except Exception as e:
                logger.error(f"MCP call failed for {service}/{tool}: {e}")
                # Several transport exceptions (notably ReadTimeout on some
                # httpx versions) stringify to an empty value.  Returning an
                # empty ``error`` makes an unavailable connector look like an
                # ambiguous success to API and Agent callers.  Keep the public
                # failure secret-free while always exposing a useful reason.
                error_message = str(e).strip() or type(e).__name__
                return {
                    "error": error_message,
                    "source": MCP_SOURCE_NAMES.get(service, service),
                    "tool": tool,
                }
        return {"error": f"Unknown MCP service: {service}", "source": service}

    async def _handle_pubmed(self, tool: str, params: dict) -> dict:
        """PubMed E-utilities API calls.

        Tools:
        - search: Search PubMed for articles
        - fetch: Fetch article details by PMID
        """
        query = params.get("query", "")
        max_results = min(params.get("max_results", 5), 10)

        if tool == "search" or tool == "query":
            # ESearch: find PMIDs
            search_url = f"{MCP_ENDPOINTS['pubmed']}/esearch.fcgi"
            resp = await self._client.get(search_url, params={
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance",
            })
            data = resp.json()
            id_list = data.get("esearchresult", {}).get("idlist", [])

            if not id_list:
                return {"source": "PubMed", "query": query, "results": [], "total": 0}

            # EFetch: get article details
            fetch_url = f"{MCP_ENDPOINTS['pubmed']}/efetch.fcgi"
            resp2 = await self._client.get(fetch_url, params={
                "db": "pubmed",
                "id": ",".join(id_list),
                "rettype": "abstract",
                "retmode": "xml",
            })
            articles = self._parse_pubmed_xml(resp2.text, id_list)

            return {
                "source": "PubMed",
                "query": query,
                "total": int(data.get("esearchresult", {}).get("count", 0)),
                "results": articles,
            }

        return {"error": f"Unknown PubMed tool: {tool}", "source": "PubMed"}

    def _parse_pubmed_xml(self, xml_text: str, id_list: list[str]) -> list[dict]:
        """Parse PubMed EFetch XML into structured article data."""
        articles = []
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(xml_text)
            for article in root.findall(".//PubmedArticle"):
                pmid_elem = article.find(".//PMID")
                pmid = pmid_elem.text if pmid_elem is not None else ""

                title_elem = article.find(".//ArticleTitle")
                title = title_elem.text or "" if title_elem is not None else ""

                abstract_parts = []
                for ab in article.findall(".//AbstractText"):
                    label = ab.get("Label", "")
                    text = ab.text or ""
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
                abstract = " ".join(abstract_parts)

                journal_elem = article.find(".//Journal/Title")
                journal = journal_elem.text if journal_elem is not None else ""

                year_elem = article.find(".//PubDate/Year")
                year = year_elem.text if year_elem is not None else ""

                authors = []
                for auth in article.findall(".//Author"):
                    last = auth.find("LastName")
                    init = auth.find("Initials")
                    if last is not None:
                        name = last.text or ""
                        if init is not None and init.text:
                            name += f" {init.text}"
                        authors.append(name)

                articles.append({
                    "pmid": pmid,
                    "title": title[:200] if title else "",
                    "abstract": abstract[:500] if abstract else "",
                    "journal": journal,
                    "year": year,
                    "authors": authors[:5],
                })
        except Exception as e:
            logger.warning(f"PubMed XML parse error: {e}")

        # Fill in missing PMIDs
        found_pmids = {a["pmid"] for a in articles}
        for pid in id_list:
            if pid not in found_pmids:
                articles.append({"pmid": pid, "title": "", "abstract": ""})

        return articles[: len(id_list)]

    async def _handle_clinical_trials(self, tool: str, params: dict) -> dict:
        """ClinicalTrials.gov API calls."""
        query = params.get("query", "")
        if tool == "search":
            resp = await self._client.get(
                f"{MCP_ENDPOINTS['clinical_trials']}/studies",
                params={
                    "query.term": query,
                    "pageSize": min(params.get("max_results", 5), 10),
                    "format": "json",
                }
            )
            data = resp.json()
            studies = []
            for s in data.get("studies", []):
                proto = s.get("protocolSection", {})
                ident = proto.get("identificationModule", {})
                status = proto.get("statusModule", {})
                studies.append({
                    "nct_id": ident.get("nctId", ""),
                    "title": ident.get("briefTitle", ""),
                    "status": status.get("overallStatus", ""),
                    "phase": " / ".join(proto.get("designModule", {}).get("phases", [])),
                })
            return {"source": "ClinicalTrials.gov", "query": query, "results": studies}
        return {"error": f"Unknown ClinicalTrials tool: {tool}"}

    async def close(self):
        await self._client.aclose()


mcp_client = McpClient()
