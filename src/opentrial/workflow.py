"""Orchestration layer: turn a design + source selection into a full report.

This module owns *what happens when you click Generate*, with no UI dependency. It
gathers evidence from the selected sources (degrading gracefully, recording a per-source
outcome), builds the evidence-derived prior, simulates the operating characteristics, picks
a recommended sample size, optionally adds a Gemini narrative, and renders the report.

Keeping this out of ``app.py`` means the Streamlit page is pure UI, and the whole pipeline
can be unit-tested, scripted, or reused for JSON export.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from opentrial.compute.mc import simulate_operating_characteristics
from opentrial.compute.priors import build_prior
from opentrial.compute.simulation import recommend_sample_size, simulate_design_grid
from opentrial.config import logger, settings
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.integrations.clinicaltrials import get_trials_ct_gov
from opentrial.integrations.dailymed import get_dailymed_full_label
from opentrial.integrations.gemini import generate_report_narrative
from opentrial.integrations.openfda import get_safety_signals
from opentrial.integrations.pubmed import get_pubmed_effects
from opentrial.report.markdown import render_markdown_report
from opentrial.schemas import (
    DesignPoint,
    EvidenceRecord,
    PriorSummary,
    SourceOutcome,
    TrialDesignInput,
)

# Evidence-source names, shared by the UI and the workflow so the picker, the sidebar
# Integrations panel, and the per-source outcomes all use one spelling.
SRC_DEMO = "Seeded demo (T2D / HbA1c, offline)"
SRC_CTGOV = "ClinicalTrials.gov"
SRC_PUBMED = "PubMed"
SRC_OPENFDA = "openFDA (safety)"
SRC_DAILYMED = "DailyMed (labels)"

EVIDENCE_SOURCES = [
    SRC_DEMO,
    SRC_CTGOV,
    SRC_PUBMED,
    SRC_OPENFDA,
    SRC_DAILYMED,
]


@dataclass
class DesignResult:
    """Everything a UI or a script needs to present a finished design report."""

    design: TrialDesignInput
    evidence: list[EvidenceRecord]
    prior: PriorSummary
    grid: list[DesignPoint]
    recommendation: DesignPoint | None
    report: str
    narrative: str = ""
    outcomes: list[SourceOutcome] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_export_dict(self) -> dict:
        """Return a stable, machine-readable report payload."""

        return {
            "design": self.design.model_dump(),
            "prior": self.prior.model_dump(),
            "recommendation": (
                self.recommendation.model_dump() if self.recommendation else None
            ),
            "grid": [point.model_dump() for point in self.grid],
            "evidence": [record.model_dump() for record in self.evidence],
            "source_outcomes": [outcome.model_dump() for outcome in self.outcomes],
            "warnings": list(self.warnings),
            "narrative": self.narrative,
            "report_markdown": self.report,
        }

    def to_json(self) -> str:
        """Serialize the full design result for reproducibility."""

        return json.dumps(self.to_export_dict(), indent=2, sort_keys=True)


def _failed_outcome(name: str, exc: Exception) -> SourceOutcome:
    """Log a source failure (full traceback) and return a ``failed`` outcome.

    The traceback goes to the logs for observability; the user-facing message stays a
    short summary unless debug mode is on, in which case the exception type is included.
    """

    logger.exception("Evidence source %r failed", name)
    message = f"{type(exc).__name__}: {exc}" if settings.debug else str(exc)
    return SourceOutcome(name=name, status="failed", n_records=0, message=message)


def _live_fetchers(
    design: TrialDesignInput, drug_or_class: str
) -> dict[str, Callable[[], list[EvidenceRecord]]]:
    """Map each live source name to a zero-argument fetch callable."""

    return {
        SRC_CTGOV: lambda: get_trials_ct_gov(design.indication, n=10),
        SRC_PUBMED: lambda: get_pubmed_effects(design.indication, design.endpoint, n=10),
        SRC_OPENFDA: lambda: get_safety_signals(drug_or_class, n=10),
        SRC_DAILYMED: lambda: get_dailymed_full_label(drug_or_class, n=5),
    }


def gather_evidence(
    design: TrialDesignInput,
    drug_or_class: str,
    selected: list[str] | set[str],
) -> tuple[list[EvidenceRecord], list[SourceOutcome]]:
    """Collect evidence from the selected sources, never raising on a single failure.

    Returns the combined evidence and a per-source outcome list. A source that errors
    becomes a ``failed`` outcome (with the message) instead of crashing the whole run --
    one flaky API can never take down the report.
    """

    chosen = set(selected)
    evidence: list[EvidenceRecord] = []
    outcomes: list[SourceOutcome] = []

    if SRC_DEMO in chosen:
        demo = list(t2d_hba1c_evidence())
        evidence.extend(demo)
        outcomes.append(SourceOutcome(name=SRC_DEMO, status="ok", n_records=len(demo)))

    for name, fetch in _live_fetchers(design, drug_or_class).items():
        if name not in chosen:
            continue
        try:
            records = list(fetch())
        except Exception as exc:  # noqa: BLE001 - one source must never crash the run
            outcomes.append(_failed_outcome(name, exc))
            continue
        evidence.extend(records)
        outcomes.append(
            SourceOutcome(
                name=name,
                status="ok" if records else "empty",
                n_records=len(records),
            )
        )

    return evidence, outcomes


def run_design(
    design: TrialDesignInput,
    drug_or_class: str,
    selected: list[str] | set[str],
    use_gemini_narrative: bool = False,
    use_mc_operating_characteristics: bool = False,
) -> DesignResult:
    """Run the full pipeline: gather -> prior -> simulate -> recommend -> render."""

    warnings: list[str] = []
    evidence, outcomes = gather_evidence(design, drug_or_class, selected)
    for outcome in outcomes:
        if outcome.status == "failed":
            warnings.append(f"{outcome.name} unavailable, continuing without it. {outcome.message}")

    prior = build_prior(evidence)

    if use_mc_operating_characteristics:
        grid = simulate_operating_characteristics(design, prior)
    else:
        grid = simulate_design_grid(design, prior)
    recommendation = recommend_sample_size(grid, design.desired_power)

    narrative = ""
    if use_gemini_narrative:
        try:
            narrative = generate_report_narrative(design, evidence, prior)
        except Exception as exc:  # noqa: BLE001 - narrative is optional, never fatal
            warnings.append(f"Gemini narrative unavailable, continuing without it. {exc}")

    report = render_markdown_report(
        design,
        evidence,
        prior,
        grid,
        recommendation,
        narrative,
        source_outcomes=outcomes,
    )

    return DesignResult(
        design=design,
        evidence=evidence,
        prior=prior,
        grid=grid,
        recommendation=recommendation,
        report=report,
        narrative=narrative,
        outcomes=outcomes,
        warnings=warnings,
    )
