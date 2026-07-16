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

CLINICALTRIALS_STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"


class ClinicalTrialsGovError(RuntimeError):
    """Raised when ClinicalTrials.gov cannot return usable study metadata."""


def get_trials_ct_gov(
    indication: str,
    n: int = 30,
    timeout: float = 10.0,
) -> list[EvidenceRecord]:
    """Fetch ClinicalTrials.gov study precedent as provenance records.

    ClinicalTrials.gov registry records usually describe protocols and enrollment,
    not clean treatment effect estimates. These records therefore use
    ``standard_error=0`` so ``build_prior`` excludes them from prior math until
    a result/effect-extraction layer is added.
    """

    payload = _fetch_studies(indication=indication, n=n, timeout=timeout)
    return [_study_to_record(study, indication) for study in payload.get("studies", [])]


def _fetch_studies(indication: str, n: int, timeout: float) -> dict[str, Any]:
    query = urlencode(
        {
            "query.term": indication,
            "pageSize": max(1, min(n, 100)),
            "format": "json",
        }
    )
    url = f"{CLINICALTRIALS_STUDIES_URL}?{query}"

    try:
        return json.loads(read_url(urlopen, url, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ClinicalTrialsGovError(f"ClinicalTrials.gov request failed: {exc}") from exc


def _study_to_record(study: dict[str, Any], indication: str) -> EvidenceRecord:
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    outcomes = protocol.get("outcomesModule", {})

    nct_id = identification.get("nctId", "")
    title = (
        identification.get("briefTitle")
        or identification.get("officialTitle")
        or nct_id
        or "ClinicalTrials.gov study"
    )
    enrollment = design.get("enrollmentInfo", {}).get("count") or 0
    year = _extract_year(status.get("startDateStruct", {}).get("date"))
    endpoint = _primary_endpoint(outcomes) or "Primary endpoint not listed"
    url = f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "https://clinicaltrials.gov/"

    return EvidenceRecord(
        evidence_kind="trial_precedent",
        source="ClinicalTrials.gov",
        title=title,
        effect=0.0,
        standard_error=0.0,
        n=int(enrollment) if isinstance(enrollment, int | float) else 0,
        endpoint=endpoint,
        indication=indication,
        year=year,
        url=url,
        notes="Registry precedent metadata only; not used in prior estimation yet.",
    )


def _primary_endpoint(outcomes: dict[str, Any]) -> str | None:
    primary_outcomes = outcomes.get("primaryOutcomes") or []
    if not primary_outcomes:
        return None
    first = primary_outcomes[0]
    return first.get("measure") or first.get("description")


def _extract_year(raw_date: str | None) -> int:
    if not raw_date:
        return date.today().year
    return safe_year(raw_date[:4])
