from __future__ import annotations

from opentrial.config import settings
from opentrial.schemas import IntegrationStatus


def integration_statuses() -> list[IntegrationStatus]:
    return [
        IntegrationStatus(
            key="clinicaltrials",
            name="ClinicalTrials.gov",
            purpose="US trial precedent and protocol metadata.",
            connected=settings.public_apis_enabled,
        ),
        IntegrationStatus(
            key="pubmed",
            name="PubMed E-utilities",
            purpose="Published effect estimates and review evidence.",
            connected=settings.pubmed_enabled,
        ),
        IntegrationStatus(
            key="openfda",
            name="openFDA FAERS",
            purpose="Post-market safety signal context.",
            connected=settings.public_apis_enabled,
        ),
        IntegrationStatus(
            key="dailymed",
            name="DailyMed",
            purpose="Structured label context for dosing and adverse events.",
            connected=settings.public_apis_enabled,
        ),
        IntegrationStatus(
            key="gemini",
            name="Gemini",
            purpose="Report orchestration and cited synthesis.",
            connected=settings.gemini_enabled,
        ),
    ]
