from __future__ import annotations

from opentrial.schemas import EvidenceRecord


def t2d_hba1c_evidence() -> list[EvidenceRecord]:
    """Small deterministic evidence pack for the first T2D/HbA1c demo."""

    return [
        EvidenceRecord(
            source="ClinicalTrials.gov",
            title="SGLT2 inhibitor add-on therapy in adults with type 2 diabetes",
            effect=0.48,
            standard_error=0.12,
            n=256,
            endpoint="HbA1c change from baseline",
            indication="Type 2 Diabetes",
            year=2019,
            url="https://clinicaltrials.gov/",
            notes="Synthetic normalized precedent record for offline MVP demo.",
        ),
        EvidenceRecord(
            source="ClinicalTrials.gov",
            title="GLP-1 receptor agonist versus placebo for glycemic control",
            effect=0.62,
            standard_error=0.15,
            n=188,
            endpoint="HbA1c change from baseline",
            indication="Type 2 Diabetes",
            year=2020,
            url="https://clinicaltrials.gov/",
            notes="Synthetic normalized precedent record for offline MVP demo.",
        ),
        EvidenceRecord(
            source="PubMed",
            title="Meta-analysis of incretin-based therapy on HbA1c reduction",
            effect=0.55,
            standard_error=0.10,
            n=1140,
            endpoint="HbA1c change from baseline",
            indication="Type 2 Diabetes",
            year=2021,
            url="https://pubmed.ncbi.nlm.nih.gov/",
            notes="Synthetic literature effect estimate for offline MVP demo.",
        ),
        EvidenceRecord(
            source="PubMed",
            title="Systematic review of SGLT2 inhibitor glycemic efficacy",
            effect=0.43,
            standard_error=0.09,
            n=980,
            endpoint="HbA1c change from baseline",
            indication="Type 2 Diabetes",
            year=2022,
            url="https://pubmed.ncbi.nlm.nih.gov/",
            notes="Synthetic literature effect estimate for offline MVP demo.",
        ),
    ]
