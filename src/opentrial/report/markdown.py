from __future__ import annotations

from opentrial.compute.simulation import prior_equivalent_n_per_arm
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


def render_markdown_report(
    design: TrialDesignInput,
    evidence: list[EvidenceRecord],
    prior: PriorSummary,
    grid: list[DesignPoint],
    recommendation: DesignPoint | None,
    narrative: str = "",
    source_outcomes: list[SourceOutcome] | None = None,
    audit_records: list[EvidenceRecord] | None = None,
    decision: DecisionSummary | None = None,
    sensitivity: list[PriorScenario] | None = None,
    group_sequential: GroupSequentialResult | None = None,
) -> str:
    if recommendation:
        rec_text = (
            f"{recommendation.n_per_arm} participants per arm "
            f"({recommendation.n_per_arm * 2} total)"
        )
        if design.dropout_rate > 0:
            analyzable = round(recommendation.n_per_arm * (1 - design.dropout_rate))
            rec_text += (
                f" to enroll, for about {analyzable} analyzable per arm after "
                f"{design.dropout_rate:.0%} dropout"
            )
    else:
        rec_text = f"Not reached by {design.max_n_per_arm} participants per arm"
    effect_label = "risk difference" if design.endpoint_type == "binary" else "mean difference"
    endpoint_assumptions = (
        [
            f"- Baseline event rate: {design.baseline_proportion:.2f}",
            (
                "- Implied treatment event rate: "
                f"{design.baseline_proportion + design.target_effect:.2f}"
            ),
        ]
        if design.endpoint_type == "binary"
        else [f"- Endpoint SD: {design.endpoint_sd:.2f}"]
    )

    lines = [
        "# OpenTrial Design Report",
        "",
        "## Design Question",
        f"- Indication: {design.indication}",
        f"- Endpoint: {design.endpoint}",
        f"- Endpoint type: {design.endpoint_type}",
        f"- Target effect ({effect_label}): {design.target_effect:.2f}",
        *endpoint_assumptions,
        f"- One-sided alpha: {design.alpha:.3f}",
        f"- Desired power: {design.desired_power:.2f}",
        f"- Planned dropout: {design.dropout_rate:.0%}",
        "",
        "## Evidence-Derived Prior",
        f"- Method: {prior.method}",
        f"- Prior mean: {prior.mean:.3f}",
        f"- Prior SD: {prior.sd:.3f}",
        f"- Records used: {prior.records_used}",
        *(
            [f"- Duplicate trial reports merged: {prior.records_merged}"]
            if prior.records_merged
            else []
        ),
        f"- Participants behind the prior: {prior.pooled_participants} (provenance, not weight)",
        f"- Prior is worth about {prior_equivalent_n_per_arm(prior, design):.0f} patients "
        "per arm (its actual information content)",
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
            "| N per arm | Power | Beta | Alpha / Type I error | Bayesian assurance |",
            "| ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for point in grid:
        lines.append(
            f"| {point.n_per_arm} | {point.power:.3f} | {point.beta:.3f} | "
            f"{point.type_i_error:.3f} | {point.assurance:.3f} |"
        )

    if decision is not None:
        lines.extend(
            [
                "",
                "## Bayesian Decision Criterion",
                (
                    f"At {decision.n_per_arm} per arm, success is declared when the posterior "
                    f"probability of a positive effect exceeds {decision.decision_threshold:.3f}."
                ),
                "",
                f"- Posterior Pr(effect > 0): {decision.posterior_success_probability:.3f}",
                (
                    "- Predictive probability of success (averaged over the prior): "
                    f"{decision.predictive_probability_of_success:.3f}"
                ),
                (
                    "- Meets decision threshold: "
                    f"{'yes' if decision.meets_decision_threshold else 'no'}"
                ),
            ]
        )

    if sensitivity:
        lines.extend(
            [
                "",
                "## Prior Sensitivity Analysis",
                (
                    "Operating characteristics under four contrasting priors "
                    f"(evaluated at {sensitivity[0].n_per_arm} per arm). "
                    "Stability across rows means the design is robust to the prior."
                ),
                "| Prior | Mean | SD | Assurance | Predictive success | Posterior Pr(>0) |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for scenario in sensitivity:
            lines.append(
                f"| {scenario.label} | {scenario.prior.mean:.3f} | {scenario.prior.sd:.3f} | "
                f"{scenario.assurance:.3f} | {scenario.predictive_probability_of_success:.3f} | "
                f"{scenario.posterior_success_probability:.3f} |"
            )

    if group_sequential is not None:
        gs = group_sequential
        lines.extend(
            [
                "",
                "## Group-Sequential Design",
                (
                    f"{gs.n_looks} planned interim looks with {gs.boundary} efficacy "
                    "boundaries, calibrated by simulation so the overall one-sided Type I "
                    f"error equals {gs.alpha:.3f}."
                ),
                "",
                f"- Type I error (simulated): {gs.type_i_error:.3f}",
                f"- Power: {gs.power:.3f}",
                (
                    f"- Expected N per arm under the alternative: {gs.expected_n_per_arm_alt:.0f} "
                    f"vs {gs.fixed_n_per_arm} for the fixed design "
                    f"({gs.expected_reduction_vs_fixed * 100:.0f}% smaller)."
                ),
                "",
                "| Look | Information fraction | N per arm | Efficacy z | Cumulative stop (alt) |",
                "| ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for look in gs.looks:
            lines.append(
                f"| {look.look} | {look.information_fraction:.2f} | {look.n_per_arm} | "
                f"{look.efficacy_z:.3f} | {look.cumulative_stop_prob_alt:.3f} |"
            )

    if audit_records:
        lines.extend(
            [
                "",
                "## Audit Mode",
                "| Audit target | Source | Enrollment / N | Recommendation comparison |",
                "| --- | --- | ---: | --- |",
            ]
        )
        for record in audit_records:
            title = record.title.replace("|", " ")
            comparison = _audit_comparison(record, recommendation)
            lines.append(
                f"| [{title}]({record.url}) | {record.source} | {record.n} | {comparison} |"
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
            "- Duplicate reports of the same trial (matched by registry id, or an exact effect/SE/N fingerprint) are collapsed to one before pooling, so no trial is counted twice.",
            "- Dropout: operating characteristics are computed on the analyzable count n*(1 - dropout), so the recommended N is the number to enroll to retain power after attrition.",
            "- Registry, citation, safety, label, target-biology, pharmacogenomic, and web records provide context unless effect uncertainty is extractable.",
            "- PubMed abstracts can enter prior estimation only when a conservative effect-size extractor finds an effect with 95% CI.",
            "- Beta is the type-II error rate at the target effect: beta = 1 - power.",
            "- Alpha / type-I error is shown as the pre-specified one-sided error-control reference.",
            "- Bayesian assurance is the probability of target-effect success averaged over the evidence-derived prior.",
            "- The current power model is a transparent normal-approximation engine; binary endpoints use the two-proportion standard error.",
            "- Decision criterion: success is defined on the Bayesian scale as posterior Pr(effect > 0) exceeding the pre-specified threshold, following the FDA Complex Innovative Trial Designs decision-criteria framing.",
            "- Prior sensitivity: per the same guidance, operating characteristics are reported under skeptical, reference, and enthusiastic priors so the dependence on the prior is explicit.",
            "- Group-sequential caveat: interim looks require Type-I-controlled boundaries (here calibrated by simulation), and a naive end-of-trial effect estimate is biased upward under early stopping, as noted in the FDA Adaptive Designs guidance.",
        ]
    )
    return "\n".join(lines)


def _audit_comparison(
    record: EvidenceRecord,
    recommendation: DesignPoint | None,
) -> str:
    if recommendation is None:
        return "No recommended sample size was reached within the configured maximum."
    if record.n <= 0:
        return "No enrollment/sample-size value available for direct comparison."

    recommended_total = recommendation.n_per_arm * 2
    difference = record.n - recommended_total
    if abs(difference) <= max(10, recommended_total * 0.10):
        label = "near recommendation"
    elif difference < 0:
        label = "below recommendation"
    else:
        label = "above recommendation"

    signed = f"+{difference}" if difference > 0 else str(difference)
    return f"{label}; recommended total {recommended_total}, audit target {signed} participants."
