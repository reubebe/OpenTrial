from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from opentrial.config import settings
from opentrial.integrations._http import read_url
from opentrial.integrations._dates import safe_year
from opentrial.schemas import EvidenceRecord

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = ",".join(
    [
        "paperId",
        "title",
        "abstract",
        "year",
        "venue",
        "url",
        "externalIds",
        "citationCount",
        "authors",
    ]
)


class SemanticScholarError(RuntimeError):
    """Raised when Semantic Scholar cannot return usable paper metadata."""


def get_semantic_scholar_papers(
    condition: str,
    endpoint: str = "",
    n: int = 10,
    timeout: float = 10.0,
) -> list[EvidenceRecord]:
    query = " ".join(part for part in [condition.strip(), endpoint.strip()] if part)
    payload = _search_papers(query=query, n=n, timeout=timeout)
    return [_paper_to_record(paper, condition, endpoint) for paper in payload.get("data", [])]


def _search_papers(query: str, n: int, timeout: float) -> dict[str, Any]:
    params = {
        "query": query,
        "limit": str(max(1, min(n, 100))),
        "fields": SEMANTIC_SCHOLAR_FIELDS,
    }
    request = Request(f"{SEMANTIC_SCHOLAR_SEARCH_URL}?{urlencode(params)}")
    if settings.semantic_scholar_api_key:
        request.add_header("x-api-key", settings.semantic_scholar_api_key)

    try:
        return json.loads(read_url(urlopen, request, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise SemanticScholarError(f"Semantic Scholar request failed: {exc}") from exc


def _paper_to_record(
    paper: dict[str, Any],
    condition: str,
    endpoint: str = "",
) -> EvidenceRecord:
    paper_id = str(paper.get("paperId") or "")
    external_ids = paper.get("externalIds") or {}
    doi = external_ids.get("DOI")
    citation_count = paper.get("citationCount") or 0
    venue = paper.get("venue") or "Semantic Scholar"
    authors = ", ".join(author.get("name", "") for author in paper.get("authors", [])[:3])
    author_note = f"; authors: {authors}" if authors else ""
    doi_note = f"; DOI: {doi}" if doi else ""
    url = paper.get("url") or (
        f"https://www.semanticscholar.org/paper/{paper_id}"
        if paper_id
        else "https://www.semanticscholar.org/"
    )

    return EvidenceRecord(
        evidence_kind="citation",
        source="Semantic Scholar",
        title=paper.get("title") or f"Semantic Scholar paper {paper_id}",
        effect=0.0,
        standard_error=0.0,
        n=0,
        endpoint=endpoint or "Literature enrichment metadata",
        indication=condition,
        year=safe_year(paper.get("year")),
        url=url,
        notes=f"{venue}; citations: {citation_count}{doi_note}{author_note}.",
    )
