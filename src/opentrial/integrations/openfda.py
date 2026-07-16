from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from opentrial.integrations._http import read_url
from opentrial.schemas import EvidenceRecord

OPENFDA_DRUG_EVENT_URL = "https://api.fda.gov/drug/event.json"


class OpenFDAError(RuntimeError):
    """Raised when openFDA cannot return usable safety metadata."""


def get_safety_signals(
    drug_or_class: str,
    n: int = 10,
    timeout: float = 10.0,
) -> list[EvidenceRecord]:
    payload = _count_reactions(drug_or_class=drug_or_class, n=n, timeout=timeout)
    return [
        _reaction_to_record(result, drug_or_class)
        for result in payload.get("results", [])
    ]


def _count_reactions(drug_or_class: str, n: int, timeout: float) -> dict[str, Any]:
    params = {
        "search": f'patient.drug.medicinalproduct:"{drug_or_class}"',
        "count": "patient.reaction.reactionmeddrapt.exact",
        "limit": str(max(1, min(n, 100))),
    }
    url = f"{OPENFDA_DRUG_EVENT_URL}?{urlencode(params)}"

    try:
        return json.loads(read_url(urlopen, url, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OpenFDAError(f"openFDA request failed: {exc}") from exc


def _reaction_to_record(result: dict[str, Any], drug_or_class: str) -> EvidenceRecord:
    reaction = str(result.get("term") or "Reported adverse event")
    count = int(result.get("count") or 0)

    return EvidenceRecord(
        evidence_kind="safety",
        source="openFDA FAERS",
        title=f"{reaction} reports for {drug_or_class}",
        effect=0.0,
        standard_error=0.0,
        n=count,
        endpoint="Post-market safety signal context",
        indication=drug_or_class,
        year=date.today().year,
        url="https://open.fda.gov/apis/drug/event/",
        notes=(
            "FAERS count only; spontaneous reports cannot establish incidence "
            "or causality."
        ),
    )
