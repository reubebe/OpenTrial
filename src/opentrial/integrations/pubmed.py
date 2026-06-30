from __future__ import annotations

import json
import re
from datetime import date
from typing import Any
from xml.etree import ElementTree
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from opentrial.config import settings
from opentrial.integrations._http import read_url
from opentrial.integrations._dates import safe_year
from opentrial.schemas import EvidenceRecord

EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedError(RuntimeError):
    """Raised when PubMed cannot return usable citation metadata."""


def get_pubmed_effects(
    condition: str,
    endpoint: str = "",
    n: int = 10,
    timeout: float = 10.0,
) -> list[EvidenceRecord]:
    """Fetch PubMed literature metadata and conservative effect estimates.

    PubMed records do not expose structured trial effect estimates, so extraction
    is intentionally narrow. Records only enter prior estimation when an abstract
    contains a simple endpoint effect and a nearby 95% CI.
    """

    term = _build_search_term(condition, endpoint)
    pmids = _search_pubmed(term=term, n=n, timeout=timeout)
    if not pmids:
        return []
    summaries = _summarize_pubmed(pmids=pmids, timeout=timeout)
    abstracts = _fetch_pubmed_abstracts(pmids=pmids, timeout=timeout)
    return [
        _summary_to_record(
            summary,
            condition=condition,
            endpoint=endpoint,
            abstract=abstracts.get(str(summary.get("uid") or ""), ""),
        )
        for summary in summaries
    ]


def _build_search_term(condition: str, intervention: str = "") -> str:
    parts = [condition.strip()]
    if intervention.strip():
        parts.append(intervention.strip())
    parts.append("(clinical trial[Publication Type] OR meta-analysis[Publication Type] OR randomized[Title/Abstract] OR systematic review[Title/Abstract])")
    return " AND ".join(part for part in parts if part)


def _search_pubmed(term: str, n: int, timeout: float) -> list[str]:
    payload = _get_json(
        "esearch.fcgi",
        {
            "db": "pubmed",
            "term": term,
            "retmax": str(max(1, min(n, 100))),
            "sort": "relevance",
            "retmode": "json",
        },
        timeout=timeout,
    )
    return payload.get("esearchresult", {}).get("idlist", [])


def _summarize_pubmed(pmids: list[str], timeout: float) -> list[dict[str, Any]]:
    payload = _get_json(
        "esummary.fcgi",
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        },
        timeout=timeout,
    )
    result = payload.get("result", {})
    return [result[pmid] for pmid in result.get("uids", []) if pmid in result]


def _fetch_pubmed_abstracts(pmids: list[str], timeout: float) -> dict[str, str]:
    root = _get_xml(
        "efetch.fcgi",
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        },
        timeout=timeout,
    )

    abstracts: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID")
        abstract_parts = [
            " ".join(part.itertext()).strip()
            for part in article.findall(".//Abstract/AbstractText")
        ]
        if pmid and abstract_parts:
            abstracts[pmid] = " ".join(part for part in abstract_parts if part)
    return abstracts


def _get_json(endpoint: str, params: dict[str, str], timeout: float) -> dict[str, Any]:
    query = urlencode(_with_ncbi_identity(params))
    url = f"{EUTILS_BASE_URL}/{endpoint}?{query}"

    try:
        return json.loads(read_url(urlopen, url, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PubMedError(f"PubMed request failed: {exc}") from exc


def _get_xml(endpoint: str, params: dict[str, str], timeout: float) -> ElementTree.Element:
    query = urlencode(_with_ncbi_identity(params))
    url = f"{EUTILS_BASE_URL}/{endpoint}?{query}"

    try:
        return ElementTree.fromstring(read_url(urlopen, url, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ElementTree.ParseError) as exc:
        raise PubMedError(f"PubMed request failed: {exc}") from exc


def _with_ncbi_identity(params: dict[str, str]) -> dict[str, str]:
    enriched = {"tool": "opentrial", **params}
    if settings.ncbi_email:
        enriched["email"] = settings.ncbi_email
    if settings.ncbi_api_key:
        enriched["api_key"] = settings.ncbi_api_key
    return enriched


def _summary_to_record(
    summary: dict[str, Any],
    condition: str,
    endpoint: str = "",
    abstract: str = "",
) -> EvidenceRecord:
    pmid = str(summary.get("uid") or "")
    title = summary.get("title") or f"PubMed article {pmid}"
    journal = summary.get("fulljournalname") or summary.get("source") or "PubMed"
    year = _extract_year(summary.get("pubdate") or summary.get("sortpubdate"))
    extracted = _extract_continuous_effect(abstract, endpoint)

    effect = extracted["effect"] if extracted else 0.0
    standard_error = extracted["standard_error"] if extracted else 0.0
    # Sample size is provenance metadata, not an effect, so extract it whenever the
    # abstract reports one -- even for citation-only records with no usable effect.
    # This is what lets PMID audit mode compare a publication's N against the
    # recommendation, and it can never push a record into the prior (the prior gate is
    # standard_error > 0, which n does not affect).
    sample_size = _extract_sample_size(" ".join(abstract.split())) if abstract else 0
    evidence_note = (
        f"extracted effect from abstract using endpoint heuristic: {extracted['basis']}."
        if extracted
        else "citation metadata only, pending manual effect-size extraction."
    )

    return EvidenceRecord(
        evidence_kind="effect_estimate" if extracted else "citation",
        source="PubMed",
        title=title,
        effect=effect,
        standard_error=standard_error,
        n=sample_size,
        endpoint=endpoint or "Literature citation metadata",
        indication=condition,
        year=year,
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "https://pubmed.ncbi.nlm.nih.gov/",
        notes=f"{journal}; {evidence_note}",
    )


# Units a continuous clinical endpoint might be reported in. Requiring an explicit
# unit is what keeps the extractor from mistaking a bare number (a year, a p-value)
# for a treatment effect.
_EFFECT_UNIT = (
    r"(?P<unit>%|percentage\s+points?|pp|mm\s?Hg|mg/d[lL]|mmol/[lL]|mmol/mol|"
    r"kg|points?|units?)"
)

# Words that signal a between-arm comparison rather than a baseline value.
_DIFF_WORD = (
    r"(?:mean\s+difference|difference|reduction|reduced|decrease[d]?|"
    r"increase[d]?|change|lower(?:ed|ing)?|improv(?:ed|ement))"
)

# Endpoint-string words too generic to anchor an effect on.
_ENDPOINT_STOPWORDS = {
    "change", "from", "baseline", "the", "of", "score", "mean", "reduction",
    "level", "levels", "week", "weeks", "month", "months", "response", "rate",
    "end", "and", "versus", "with", "value", "values", "over", "time",
}


def _endpoint_tokens(endpoint: str) -> list[str]:
    """Salient keywords from the endpoint string, used to anchor an effect to it."""

    tokens = re.split(r"[^a-z0-9]+", endpoint.lower())
    return [token for token in tokens if len(token) >= 3 and token not in _ENDPOINT_STOPWORDS]


def _extract_continuous_effect(abstract: str, endpoint: str = "") -> dict[str, float | int | str] | None:
    """Conservatively extract a continuous treatment effect for ``endpoint``.

    Works for any continuous endpoint (HbA1c %, blood pressure mmHg, weight kg, ...),
    not just HbA1c. It only returns a value when the abstract clearly states a
    between-arm difference for the endpoint *and* a nearby 95% CI -- the CI is what
    yields a standard error and lets the record enter prior estimation. Anything less
    certain stays context-only, because a wrong effect is worse than a missing one.
    """

    text = " ".join(abstract.split())
    if not text:
        return None

    tokens = _endpoint_tokens(endpoint)
    if not tokens:
        return None  # without endpoint keywords we cannot anchor the effect honestly

    effect_match = _find_endpoint_effect(text, tokens)
    if not effect_match:
        return None

    effect = abs(float(effect_match.group("effect")))
    if effect <= 0 or effect > 1000:
        return None

    window = text[max(0, effect_match.start() - 160) : effect_match.end() + 220]
    ci_match = re.search(
        r"95\s*%\s*(?:confidence interval|ci)?[^-\d]{0,30}"
        r"(?P<lower>-?\d+(?:\.\d+)?)\s*(?:to|,|;)\s*"
        r"(?P<upper>-?\d+(?:\.\d+)?)",
        window,
        flags=re.IGNORECASE,
    )
    if not ci_match:
        return None

    lower = float(ci_match.group("lower"))
    upper = float(ci_match.group("upper"))
    standard_error = abs(upper - lower) / (2 * 1.96)
    if standard_error <= 0:
        return None

    unit = " ".join(effect_match.group("unit").split())
    return {
        "effect": effect,
        "standard_error": standard_error,
        "n": _extract_sample_size(text),
        "basis": f"{effect:.3f} {unit} with 95% CI {lower:.3f} to {upper:.3f}",
    }


def _find_endpoint_effect(text: str, tokens: list[str]) -> re.Match[str] | None:
    """Find a numeric effect (with a unit) reported as a difference for the endpoint."""

    token_alt = "(?:" + "|".join(re.escape(token) for token in tokens) + ")"
    number = r"(?P<effect>-?\d+(?:\.\d+)?)\s*" + _EFFECT_UNIT + r"\b"
    patterns = [
        # endpoint ... difference word ... number+unit
        token_alt + r".{0,120}?" + _DIFF_WORD + r".{0,80}?" + number,
        # difference word ... endpoint ... number+unit
        _DIFF_WORD + r".{0,120}?" + token_alt + r".{0,80}?" + number,
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match
    return None


def _extract_sample_size(text: str) -> int:
    sample_size_patterns = [
        r"\b(?:n|N)\s*=\s*(?P<n>\d{2,6})\b",
        r"\b(?P<n>\d{2,6})\s+(?:patients|participants|subjects)\b",
    ]
    for pattern in sample_size_patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group("n"))
    return 0


def _extract_year(raw_date: str | None) -> int:
    if not raw_date:
        return date.today().year
    return safe_year(raw_date[:4])
