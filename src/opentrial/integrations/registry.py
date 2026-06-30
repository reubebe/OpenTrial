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
        ),
        IntegrationStatus(
            key="pubmed",
            name="PubMed E-utilities",
            purpose="Published literature metadata; email/API key optional for NCBI etiquette and rate limits.",
            connected=settings.pubmed_enabled,
            status=_live_status(),
        ),
        IntegrationStatus(
            key="openfda",
            name="openFDA FAERS",
            purpose="Post-market safety signal context.",
            connected=settings.public_apis_enabled,
            status=_live_status(),
        ),
        IntegrationStatus(
            key="dailymed",
            name="DailyMed",
            purpose="Structured label context for dosing and adverse events.",
            connected=settings.public_apis_enabled,
            status=_live_status(),
        ),
        IntegrationStatus(
            key="gemini",
            name="Gemini",
            purpose="Optional report narrative synthesis.",
            connected=settings.gemini_enabled,
            status="connected" if settings.gemini_enabled else "missing key",
        ),
    ]
