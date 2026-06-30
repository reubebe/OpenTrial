from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from opentrial.integrations._dates import safe_year
from opentrial.integrations._http import read_url
from opentrial.schemas import EvidenceRecord

DAILYMED_SPLS_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"


class DailyMedError(RuntimeError):
    """Raised when DailyMed cannot return usable label metadata."""


def get_dailymed_full_label(
    drug_name: str,
    n: int = 5,
    timeout: float = 10.0,
) -> list[EvidenceRecord]:
    payload = _search_labels(drug_name=drug_name, n=n, timeout=timeout)
    return [_label_to_record(label, drug_name) for label in payload.get("data", [])]


def _search_labels(drug_name: str, n: int, timeout: float) -> dict[str, Any]:
    params = {
        "drug_name": drug_name,
        "pagesize": str(max(1, min(n, 100))),
        "page": "1",
    }
    url = f"{DAILYMED_SPLS_URL}?{urlencode(params)}"

    try:
        return json.loads(read_url(urlopen, url, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DailyMedError(f"DailyMed request failed: {exc}") from exc


def _label_to_record(label: dict[str, Any], drug_name: str) -> EvidenceRecord:
    setid = str(label.get("setid") or "")

    return EvidenceRecord(
        evidence_kind="label",
        source="DailyMed",
        title=label.get("title") or f"DailyMed label for {drug_name}",
        effect=0.0,
        standard_error=0.0,
        n=0,
        endpoint="Structured product label context",
        indication=drug_name,
        year=_extract_year(label.get("published_date")),
        url=(
            f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"
            if setid
            else "https://dailymed.nlm.nih.gov/dailymed/"
        ),
        notes=f"DailyMed SPL version {label.get('spl_version') or 'unknown'}.",
    )


def _extract_year(raw_date: str | None) -> int:
    if not raw_date:
        return date.today().year
    parts = raw_date.replace(",", "").split()
    for part in reversed(parts):
        if part.isdigit() and len(part) == 4:
            return safe_year(part)
    return date.today().year
