from __future__ import annotations

from opentrial.config import settings
from opentrial.schemas import IntegrationStatus


def _live_status() -> str:
    return "connected" if settings.public_apis_enabled else "disabled"


def integration_statuses() -> list[IntegrationStatus]:
    return [
        IntegrationStatus(
            key="clinicaltrials",
            name="ClinicalTrials.gov",
            purpose="US trial precedent and protocol metadata.",
            connected=settings.public_apis_enabled,
            status=_live_status(),
            sdk="urllib | ClinicalTrials.gov v2 REST",
        ),
        IntegrationStatus(
            key="pubmed",
            name="PubMed E-utilities",
            purpose="Published literature metadata; email/API key optional for NCBI etiquette and rate limits.",
            connected=settings.pubmed_enabled,
            status=_live_status(),
            sdk="urllib | NCBI E-utilities",
        ),
        IntegrationStatus(
            key="openfda",
            name="openFDA FAERS",
            purpose="Post-market safety signal context.",
            connected=settings.public_apis_enabled,
            status=_live_status(),
            sdk="urllib | openFDA REST",
        ),
        IntegrationStatus(
            key="dailymed",
            name="DailyMed",
            purpose="Structured label context for dosing and adverse events.",
            connected=settings.public_apis_enabled,
            status=_live_status(),
            sdk="urllib | DailyMed REST",
        ),
        IntegrationStatus(
            key="opentargets",
            name="Open Targets",
            purpose="Disease-target biology associations and translational context.",
            connected=settings.public_apis_enabled,
            status=_live_status(),
            sdk="urllib | Open Targets GraphQL",
        ),
        IntegrationStatus(
            key="pharmgkb",
            name="PharmGKB",
            purpose="Drug-gene clinical annotation and pharmacogenomics context.",
            connected=settings.public_apis_enabled,
            status=_live_status(),
            sdk="urllib | PharmGKB REST",
        ),
        IntegrationStatus(
            key="semantic_scholar",
            name="Semantic Scholar",
            purpose="Academic citation enrichment and related literature metadata.",
            connected=settings.semantic_scholar_enabled,
            status="connected" if settings.semantic_scholar_enabled else "missing key",
            sdk="urllib | Semantic Scholar Graph API",
        ),
        IntegrationStatus(
            key="you",
            name="You.com",
            purpose="Broad web context for exploratory provenance.",
            connected=settings.you_enabled,
            status="connected" if settings.you_enabled else "missing key",
            sdk="urllib | You.com Search API",
        ),
        IntegrationStatus(
            key="gemini",
            name="Gemini",
            purpose="Report orchestration and cited synthesis.",
            connected=settings.gemini_enabled,
            status="connected" if settings.gemini_enabled else "missing key",
            sdk="urllib | Gemini generateContent REST",
        ),
    ]
