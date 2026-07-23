"""Orchestration layer: turn a design + source selection into a full report.

This module owns *what happens when you click Generate*, with no UI dependency. It
gathers evidence from the selected sources (degrading gracefully, recording a per-source
outcome), builds the prior (deterministic or optional PyMC), simulates the grid, picks a
recommendation, optionally adds a Gemini narrative, and renders the Markdown report.

Keeping this out of ``app.py`` means the Streamlit page is pure UI, and the whole pipeline
can be unit-tested, scripted from a CLI, or reused for JSON export and audit mode.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from opentrial.compute.bayes import BayesianPriorError, build_prior_bayesian
from opentrial.compute.decision import summarize_decision
from opentrial.compute.group_sequential import simulate_group_sequential
from opentrial.compute.mc import simulate_operating_characteristics
from opentrial.compute.priors import build_prior
from opentrial.compute.sensitivity import prior_sensitivity
from opentrial.config import logger, settings
from opentrial.compute.simulation import recommend_sample_size, simulate_design_grid
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.integrations.clinicaltrials import (
    get_trial_ct_gov_by_nct,
    get_trials_ct_gov,
)
from opentrial.integrations.dailymed import get_dailymed_full_label
from opentrial.integrations.gemini import generate_report_narrative
from opentrial.integrations.openfda import get_safety_signals
from opentrial.integrations.opentargets import get_disease_target_context
from opentrial.integrations.pharmgkb import get_pharmgkb_drug_gene
from opentrial.integrations.pubmed import get_pubmed_effects, get_pubmed_record_by_pmid
from opentrial.integrations.semantic_scholar import get_semantic_scholar_papers
from opentrial.integrations.you_search import get_you_search_context
from opentrial.report.markdown import render_markdown_report
from opentrial.schemas import (
    DecisionSummary,
    DesignPoint,
    EvidenceRecord,
    GroupSequentialResult,
    PriorScenario,
    PriorSummary,
    SourceOutcome,
    TrialDesignInput,
)

# Evidence-source names, shared by the UI and the workflow so the picker, the sidebar
# Integrations panel, and the per-source outcomes all use one spelling.
SRC_DEMO = "Seeded demo (T2D / HbA1c, offline)"
SRC_CTGOV = "ClinicalTrials.gov"
SRC_PUBMED = "PubMed"
SRC_S2 = "Semantic Scholar"
SRC_OPENFDA = "openFDA (safety)"
SRC_DAILYMED = "DailyMed (labels)"
SRC_OPENTARGETS = "Open Targets (biology)"
SRC_PHARMGKB = "PharmGKB (pharmacogenomics)"
SRC_YOU = "You.com (web)"

EVIDENCE_SOURCES = [
    SRC_DEMO,
    SRC_CTGOV,
    SRC_PUBMED,
    SRC_S2,
    SRC_OPENFDA,
    SRC_DAILYMED,
    SRC_OPENTARGETS,
    SRC_PHARMGKB,
    SRC_YOU,
]

# The proof-of-concept scope: the seeded demo plus the four core public sources.
# The UI offers these by default; the remaining sources stay available as "advanced".
CORE_EVIDENCE_SOURCES = [
    SRC_DEMO,
    SRC_CTGOV,
    SRC_PUBMED,
    SRC_OPENFDA,
    SRC_DAILYMED,
]

# Advanced sources surfaced in the UI's "Advanced evidence sources" picker.
EXTRA_EVIDENCE_SOURCES = [
    SRC_S2,
    SRC_OPENTARGETS,
    SRC_PHARMGKB,
    SRC_YOU,
]

# Integration registry keys that back the core sources (used to lean out the sidebar).
CORE_INTEGRATION_KEYS = {"clinicaltrials", "pubmed", "openfda", "dailymed"}


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
    audit_records: list[EvidenceRecord] = field(default_factory=list)
    decision: DecisionSummary | None = None
    sensitivity: list[PriorScenario] = field(default_factory=list)
    group_sequential: GroupSequentialResult | None = None

    def to_export_dict(self) -> dict:
        """Return a stable, machine-readable report payload."""

        return {
            "design": self.design.model_dump(),
            "prior": self.prior.model_dump(),
            "recommendation": (
                self.recommendation.model_dump() if self.recommendation else None
            ),
            "decision": self.decision.model_dump() if self.decision else None,
            "sensitivity": [scenario.model_dump() for scenario in self.sensitivity],
            "group_sequential": (
                self.group_sequential.model_dump() if self.group_sequential else None
            ),
            "grid": [point.model_dump() for point in self.grid],
            "evidence": [record.model_dump() for record in self.evidence],
            "audit_records": [record.model_dump() for record in self.audit_records],
            "source_outcomes": [outcome.model_dump() for outcome in self.outcomes],
            "warnings": list(self.warnings),
            "narrative": self.narrative,
            "report_markdown": self.report,
        }

    def to_pdf(self) -> bytes:
        """Render the report to PDF bytes (raises PdfExportError if the extra is absent)."""

        from opentrial.report.pdf import render_pdf_report

        return render_pdf_report(
            self.design,
            self.prior,
            self.grid,
            self.recommendation,
            decision=self.decision,
            sensitivity=self.sensitivity or None,
            group_sequential=self.group_sequential,
            evidence=self.evidence,
        )

    def to_json(self) -> str:
        """Serialize the full design result for reproducibility and audit."""

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
        SRC_S2: lambda: get_semantic_scholar_papers(design.indication, design.endpoint, n=10),
        SRC_OPENFDA: lambda: get_safety_signals(drug_or_class, n=10),
        SRC_DAILYMED: lambda: get_dailymed_full_label(drug_or_class, n=5),
        SRC_OPENTARGETS: lambda: get_disease_target_context(design.indication, n=10),
        SRC_PHARMGKB: lambda: get_pharmgkb_drug_gene(drug_or_class, n=10),
        SRC_YOU: lambda: get_you_search_context(
            f"{design.indication} {design.endpoint} {drug_or_class} clinical trial",
            indication=design.indication,
            endpoint=design.endpoint,
            n=5,
        ),
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


def gather_audit_targets(
    design: TrialDesignInput,
    nct_id: str = "",
    pmid: str = "",
) -> tuple[list[EvidenceRecord], list[SourceOutcome]]:
    """Fetch user-specified audit targets without adding them to the prior evidence."""

    records: list[EvidenceRecord] = []
    outcomes: list[SourceOutcome] = []

    if nct_id.strip():
        name = f"Audit NCT {nct_id.strip().upper()}"
        try:
            fetched = get_trial_ct_gov_by_nct(nct_id, indication=design.indication)
        except Exception as exc:  # noqa: BLE001 - audit target failures should be reported
            outcomes.append(_failed_outcome(name, exc))
        else:
            records.extend(fetched)
            outcomes.append(
                SourceOutcome(
                    name=name,
                    status="ok" if fetched else "empty",
                    n_records=len(fetched),
                )
            )

    if pmid.strip():
        name = f"Audit PMID {pmid.strip()}"
        try:
            fetched = get_pubmed_record_by_pmid(
                pmid,
                condition=design.indication,
                endpoint=design.endpoint,
            )
        except Exception as exc:  # noqa: BLE001 - audit target failures should be reported
            outcomes.append(_failed_outcome(name, exc))
        else:
            records.extend(fetched)
            outcomes.append(
                SourceOutcome(
                    name=name,
                    status="ok" if fetched else "empty",
                    n_records=len(fetched),
                )
            )

    return records, outcomes


def build_evidence_prior(
    evidence: list[EvidenceRecord], use_bayesian_prior: bool = False
) -> tuple[PriorSummary, str | None]:
    """Build the prior, preferring PyMC when asked but falling back deterministically."""

    if use_bayesian_prior:
        try:
            return build_prior_bayesian(evidence), None
        except BayesianPriorError as exc:
            return (
                build_prior(evidence),
                f"Bayesian prior unavailable, using inverse-variance prior. {exc}",
            )
    return build_prior(evidence), None


def run_design(
    design: TrialDesignInput,
    drug_or_class: str,
    selected: list[str] | set[str],
    use_bayesian_prior: bool = False,
    use_gemini_narrative: bool = False,
    audit_nct_id: str = "",
    audit_pmid: str = "",
    use_mc_operating_characteristics: bool = False,
    use_prior_sensitivity: bool = False,
    use_group_sequential: bool = False,
    gs_n_looks: int = 4,
    gs_boundary: str = "obrien-fleming",
) -> DesignResult:
    """Run the full pipeline: gather -> prior -> simulate -> recommend -> render."""

    warnings: list[str] = []
    evidence, outcomes = gather_evidence(design, drug_or_class, selected)
    audit_records, audit_outcomes = gather_audit_targets(
        design,
        nct_id=audit_nct_id,
        pmid=audit_pmid,
    )
    outcomes.extend(audit_outcomes)
    for outcome in outcomes:
        if outcome.status == "failed":
            warnings.append(f"{outcome.name} unavailable, continuing without it. {outcome.message}")

    prior, prior_warning = build_evidence_prior(evidence, use_bayesian_prior=use_bayesian_prior)
    if prior_warning:
        warnings.append(prior_warning)

    if use_mc_operating_characteristics:
        grid = simulate_operating_characteristics(design, prior)
    else:
        grid = simulate_design_grid(design, prior)
    recommendation = recommend_sample_size(grid, design.desired_power)

    # The Bayesian decision criterion and prior sensitivity are read at the recommended
    # sample size when one is reached, otherwise at the design's maximum.
    eval_n = recommendation.n_per_arm if recommendation else design.max_n_per_arm
    decision = summarize_decision(design, prior, eval_n)

    sensitivity: list[PriorScenario] = []
    if use_prior_sensitivity:
        sensitivity = prior_sensitivity(design, prior, eval_n)

    group_sequential: GroupSequentialResult | None = None
    if use_group_sequential:
        try:
            group_sequential = simulate_group_sequential(
                design, n_looks=gs_n_looks, boundary=gs_boundary
            )
        except ValueError as exc:
            warnings.append(f"Group-sequential design unavailable, skipping it. {exc}")

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
        audit_records=audit_records,
        decision=decision,
        sensitivity=sensitivity,
        group_sequential=group_sequential,
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
        audit_records=audit_records,
        decision=decision,
        sensitivity=sensitivity,
        group_sequential=group_sequential,
    )
