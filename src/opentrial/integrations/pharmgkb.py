from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from opentrial.integrations._http import read_url
from opentrial.schemas import EvidenceRecord

PHARMGKB_BASE_URL = "https://api.pharmgkb.org/v1"


class PharmGKBError(RuntimeError):
    """Raised when PharmGKB cannot return usable pharmacogenomics metadata."""


def get_pharmgkb_drug_gene(
    drug_or_gene: str,
    n: int = 10,
    timeout: float = 10.0,
) -> list[EvidenceRecord]:
    """Fetch PharmGKB clinical annotations for a drug or gene."""

    records = _clinical_annotations_by_drug(drug_or_gene, n=n, timeout=timeout)
    if records:
        return records
    return _clinical_annotations_by_gene(drug_or_gene, n=n, timeout=timeout)


def _clinical_annotations_by_drug(
    drug: str,
    n: int,
    timeout: float,
) -> list[EvidenceRecord]:
    payload = _get_json(
        "/data/clinicalAnnotation",
        {"relatedChemicals.name": drug, "view": "base"},
        timeout=timeout,
    )
    return [_annotation_to_record(item) for item in payload.get("data", [])[:n]]


def _clinical_annotations_by_gene(
    gene: str,
    n: int,
    timeout: float,
) -> list[EvidenceRecord]:
    payload = _get_json(
        "/data/clinicalAnnotation",
        {"location.genes.symbol": gene, "view": "base"},
        timeout=timeout,
    )
    return [_annotation_to_record(item) for item in payload.get("data", [])[:n]]


def _get_json(path: str, params: dict[str, str], timeout: float) -> dict[str, Any]:
    url = f"{PHARMGKB_BASE_URL}{path}?{urlencode(params)}"
    try:
        return json.loads(read_url(urlopen, url, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PharmGKBError(f"PharmGKB request failed: {exc}") from exc


def _annotation_to_record(annotation: dict[str, Any]) -> EvidenceRecord:
    accession = annotation.get("accessionId") or str(annotation.get("id") or "")
    title = annotation.get("name") or f"PharmGKB clinical annotation {accession}"
    level = (annotation.get("levelOfEvidence") or {}).get("term") or "unknown"
    genes = _names_from_location(annotation.get("location") or {})
    chemicals = _names(annotation.get("relatedChemicals"))
    diseases = _names(annotation.get("relatedDiseases"))

    return EvidenceRecord(
        evidence_kind="pharmacogenomics",
        source="PharmGKB",
        title=title,
        effect=0.0,
        standard_error=0.0,
        n=0,
        endpoint="Pharmacogenomics context",
        indication=", ".join(diseases) or "PharmGKB clinical annotation",
        year=date.today().year,
        url=(
            f"https://www.pharmgkb.org/clinicalAnnotation/{accession}"
            if accession
            else "https://www.pharmgkb.org/"
        ),
        notes=(
            f"Level of evidence: {level}; "
            f"genes: {', '.join(genes) or 'not listed'}; "
            f"chemicals: {', '.join(chemicals) or 'not listed'}."
        ),
    )


def _names(items: list[dict[str, Any]] | None) -> list[str]:
    return [str(item.get("name")) for item in items or [] if item.get("name")]


def _names_from_location(location: dict[str, Any]) -> list[str]:
    genes = location.get("genes") or []
    return [
        str(gene.get("symbol") or gene.get("name"))
        for gene in genes
        if gene.get("symbol") or gene.get("name")
    ]
