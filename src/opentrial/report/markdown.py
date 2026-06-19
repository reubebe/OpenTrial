from __future__ import annotations

from opentrial.schemas import (
    DesignPoint,
    EvidenceRecord,
    PriorSummary,
    TrialDesignInput,
)


def render_markdown_report(
    design: TrialDesignInput,
    evidence: list[EvidenceRecord],
    prior: PriorSummary,
    grid: list[DesignPoint],
    recommendation: DesignPoint | None,
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
        f"- Target effect: {design.target_effect:.2f}",
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
        "## Recommendation",
        f"- Recommended sample size: {rec_text}",
        "",
        "## Operating Characteristics",
        "| N per arm | Power | Posterior Pr(effect > 0) |",
        "| ---: | ---: | ---: |",
    ]

    for point in grid:
        lines.append(
            f"| {point.n_per_arm} | {point.power:.3f} | "
            f"{point.posterior_success_probability:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Evidence Provenance",
            "| Source | Year | Title | Effect | SE | N |",
            "| --- | ---: | --- | ---: | ---: | ---: |",
        ]
    )

    for record in evidence:
        title = record.title.replace("|", " ")
        lines.append(
            f"| {record.source} | {record.year} | [{title}]({record.url}) | "
            f"{record.effect:.3f} | {record.standard_error:.3f} | {record.n} |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "- This first slice uses deterministic seeded evidence so the app runs without secrets.",
            "- Live ClinicalTrials.gov and PubMed adapters should replace the seeded evidence next.",
            "- The current power model is a transparent normal approximation for a continuous endpoint.",
        ]
    )
    return "\n".join(lines)
