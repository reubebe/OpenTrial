from __future__ import annotations

import json
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from opentrial.integrations._http import read_url
from opentrial.schemas import EvidenceRecord

OPEN_TARGETS_GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"


class OpenTargetsError(RuntimeError):
    """Raised when Open Targets cannot return usable disease-target metadata."""


def get_disease_target_context(
    disease: str,
    n: int = 10,
    timeout: float = 10.0,
) -> list[EvidenceRecord]:
    """Fetch top Open Targets disease-target associations as context records."""

    disease_hit = _resolve_disease(disease=disease, timeout=timeout)
    if not disease_hit:
        return []
    payload = _fetch_associated_targets(
        disease_id=disease_hit["id"],
        n=n,
        timeout=timeout,
    )
    disease_obj = payload.get("data", {}).get("disease")
    if not disease_obj:
        return []
    rows = disease_obj.get("associatedTargets", {}).get("rows", [])
    return [_target_to_record(row, disease_obj) for row in rows]


def _resolve_disease(disease: str, timeout: float) -> dict[str, Any] | None:
    query = """
    query SearchDisease($queryString: String!) {
      search(queryString: $queryString, entityNames: ["disease"], page: {index: 0, size: 1}) {
        hits { id name entity description score }
      }
    }
    """
    payload = _graphql(query, {"queryString": disease}, timeout=timeout)
    hits = payload.get("data", {}).get("search", {}).get("hits", [])
    return hits[0] if hits else None


def _fetch_associated_targets(
    disease_id: str,
    n: int,
    timeout: float,
) -> dict[str, Any]:
    query = """
    query DiseaseTargets($efoId: String!, $size: Int!) {
      disease(efoId: $efoId) {
        id
        name
        associatedTargets(page: {index: 0, size: $size}) {
          rows {
            score
            target { id approvedSymbol approvedName }
          }
        }
      }
    }
    """
    return _graphql(
        query,
        {"efoId": disease_id, "size": max(1, min(n, 100))},
        timeout=timeout,
    )


def _graphql(query: str, variables: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = Request(
        OPEN_TARGETS_GRAPHQL_URL,
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        payload = json.loads(read_url(urlopen, request, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OpenTargetsError(f"Open Targets request failed: {exc}") from exc

    if payload.get("errors"):
        raise OpenTargetsError(f"Open Targets GraphQL errors: {payload['errors']}")
    return payload


def _target_to_record(row: dict[str, Any], disease: dict[str, Any]) -> EvidenceRecord:
    target = row.get("target") or {}
    symbol = target.get("approvedSymbol") or target.get("id") or "unknown target"
    score = float(row.get("score") or 0.0)
    disease_name = disease.get("name") or disease.get("id") or "disease"

    return EvidenceRecord(
        evidence_kind="target_biology",
        source="Open Targets",
        title=f"{symbol} association with {disease_name}",
        # The Open Targets association score is a biology-relevance signal, not a
        # treatment effect, so it stays out of the effect column (and the prior).
        # It is preserved in notes for provenance.
        effect=0.0,
        standard_error=0.0,
        n=0,
        endpoint="Disease-target biology context",
        indication=disease_name,
        year=date.today().year,
        url=(
            f"https://platform.opentargets.org/target/{target.get('id')}/associations"
            if target.get("id")
            else "https://platform.opentargets.org/"
        ),
        notes=(
            f"Association score {score:.3f}; "
            f"{target.get('approvedName') or 'target name unavailable'}."
        ),
    )
