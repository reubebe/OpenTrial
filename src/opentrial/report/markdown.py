from __future__ import annotations

from opentrial.schemas import (
    DesignPoint,
    EvidenceRecord,
    PriorSummary,
    SourceOutcome,
    TrialDesignInput,
)


def render_markdown_report(
    design: TrialDesignInput,
    evidence: list[EvidenceRecord],
    prior: PriorSummary,
    grid: list[DesignPoint],
    recommendation: DesignPoint | None,
    narrative: str = "",
    source_outcomes: list[SourceOutcome] | None = None,
) -> str:
    rec_text = (
        f"{recommendation.n_per_arm} participants per arm "
        f"({recommendation.n_per_arm * 2} total)"
        if recommendation
        else f"Not reached by {design.max_n_per_arm} participants per arm"
    )
    lines = [
        "# OpenTrial Design Report",
        "",
        "## Design Question",
        f"- Indication: {design.indication}",
        f"- Endpoint: {design.endpoint}",
        f"- Target effect (mean difference): {design.target_effect:.2f}",
        f"- Endpoint SD: {design.endpoint_sd:.2f}",
        f"- One-sided alpha: {design.alpha:.3f}",
        f"- Desired power: {design.desired_power:.2f}",
        "",
        "## Evidence-Derived Prior",
        f"- Method: {prior.method}",
        f"- Prior mean: {prior.mean:.3f}",
        f"- Prior SD: {prior.sd:.3f}",
        f"- Records used: {prior.records_used}",
        f"- Evidence effective N: {prior.effective_n}",
        "",
    ]

    if narrative:
        lines.extend([narrative, ""])

    if source_outcomes:
        lines.extend(
            [
                "## Evidence Source Status",
                "| Source | Status | Records | Message |",
                "| --- | --- | ---: | --- |",
            ]
        )
        for outcome in source_outcomes:
            message = outcome.message.replace("|", " ") if outcome.message else ""
            lines.append(
                f"| {outcome.name} | {outcome.status} | {outcome.n_records} | {message} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Recommendation",
            f"- Recommended sample size: {rec_text}",
            "",
            "## Operating Characteristics",
            "| N per arm | Power | Beta | Alpha / Type I error | Bayesian assurance | Posterior Pr(effect > 0) |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for point in grid:
        lines.append(
            f"| {point.n_per_arm} | {point.power:.3f} | {point.beta:.3f} | "
            f"{point.type_i_error:.3f} | {point.assurance:.3f} | "
            f"{point.posterior_success_probability:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Evidence Provenance",
            "| Kind | Source | Year | Title | Effect | SE | N |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: |",
        ]
    )

    for record in evidence:
        title = record.title.replace("|", " ")
        lines.append(
            f"| {record.evidence_kind} | {record.source} | {record.year} | [{title}]({record.url}) | "
            f"{record.effect:.3f} | {record.standard_error:.3f} | {record.n} |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- Records with SE=0 are retained for provenance but excluded from prior estimation.",
            "- Registry, citation, safety, and label records provide context unless effect uncertainty is extractable.",
            "- PubMed abstracts can enter prior estimation only when a conservative effect-size extractor finds an effect with 95% CI.",
            "- Beta is the type-II error rate at the target effect: beta = 1 - power.",
            "- Alpha / type-I error is shown as the pre-specified one-sided error-control reference.",
            "- Bayesian assurance is the probability of target-effect success averaged over the evidence-derived prior.",
            "- The current power model is a transparent normal-approximation engine for a continuous endpoint.",
        ]
    )
    return "\n".join(lines)
