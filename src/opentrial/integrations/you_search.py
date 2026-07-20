from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from opentrial.config import settings
from opentrial.integrations._http import read_url
from opentrial.schemas import EvidenceRecord

YOU_SEARCH_URL = "https://ydc-index.io/v1/search"


class YouSearchError(RuntimeError):
    """Raised when You.com cannot return usable search metadata."""


def get_you_search_context(
    query: str,
    indication: str = "",
    endpoint: str = "",
    n: int = 5,
    timeout: float = 10.0,
) -> list[EvidenceRecord]:
    payload = _search_you(query=query, n=n, timeout=timeout)
    return [
        _result_to_record(result, indication=indication or query, endpoint=endpoint)
        for result in _extract_results(payload)[:n]
        if isinstance(result, dict)
    ]


def _search_you(query: str, n: int, timeout: float) -> dict[str, Any]:
    params = {"query": query, "count": str(max(1, min(n, 10)))}
    request = Request(f"{YOU_SEARCH_URL}?{urlencode(params)}")
    if settings.you_api_key:
        request.add_header("X-API-Key", settings.you_api_key)

    try:
        return json.loads(read_url(urlopen, request, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise YouSearchError(f"You.com request failed: {exc}") from exc


def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    nested_results = payload.get("results")
    if isinstance(nested_results, dict):
        combined: list[dict[str, Any]] = []
        for key in ("web", "news"):
            value = nested_results.get(key)
            if isinstance(value, list):
                combined.extend(value)
        if combined:
            return combined

    for key in ("hits", "results", "web", "search_results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    if isinstance(payload.get("data"), list):
        return payload["data"]
    return []


def _result_to_record(
    result: dict[str, Any],
    indication: str,
    endpoint: str = "",
) -> EvidenceRecord:
    title = result.get("title") or result.get("name") or "You.com search result"
    url = result.get("url") or result.get("link") or "https://you.com/"
    snippet = result.get("snippet") or result.get("description") or result.get("text") or ""
    snippets = result.get("snippets")
    if not snippet and isinstance(snippets, list):
        snippet = " ".join(str(item) for item in snippets[:2])

    return EvidenceRecord(
        evidence_kind="web_context",
        source="You.com",
        title=title,
        effect=0.0,
        standard_error=0.0,
        n=0,
        endpoint=endpoint or "Web search context",
        indication=indication,
        year=date.today().year,
        url=url,
        notes=f"Web-search context only; {snippet[:220]}",
    )
