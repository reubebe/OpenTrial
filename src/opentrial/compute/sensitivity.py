"""Prior sensitivity analysis: how much do the results depend on the prior?

The FDA Complex Innovative Trial Designs guidance is explicit that, for a Bayesian design,
"it is informative to assess the sensitivity of trial operating characteristics to the
choice of a prior distribution." This module does exactly that: it evaluates the same design
under four contrasting priors, using the guidance's own vocabulary for how priors are
constructed.

* **evidence** -- the evidence-derived prior from :func:`opentrial.compute.priors.build_prior`.
* **skeptical** -- centered at no effect, encoding "initial skepticism regarding the
  likelihood of large treatment effects" (guidance, section III.C.1). Same precision as the
  evidence prior, but recentered on the null.
* **reference** -- a weakly-informative / non-informative prior "to reflect a stance of
  general uncertainty regarding the parameters of interest."
* **enthusiastic** -- centered on the target effect, the optimistic mirror of the skeptical
  prior (FDA Bayesian device guidance).

If the recommendation and assurance are stable across all four, the design is robust to the
prior; if they swing, the prior is doing the heavy lifting and deserves scrutiny. Standard
library only.
"""

from __future__ import annotations

from statistics import NormalDist

from opentrial.compute.decision import (
    posterior_success_probability_at,
    predictive_probability_of_success,
)
from opentrial.compute.simulation import (
    effect_standard_error,
    prior_predictive_assurance,
)
from opentrial.schemas import EvidenceRecord, PriorScenario, PriorSummary, TrialDesignInput

_REFERENCE_SD = 1.0
# Skeptical/enthusiastic priors follow Spiegelhalter's construction: the spread is set so
# that only ~5% of the prior mass lies beyond the target effect (skeptical) or below no
# effect (enthusiastic). sd = target / z_0.95 puts the target at the 95th percentile.
_SKEPTICISM_TAIL = 0.95


def _spiegelhalter_sd(target_effect: float) -> float:
    return max(target_effect / NormalDist().inv_cdf(_SKEPTICISM_TAIL), 0.05)


def _scenario_priors(design: TrialDesignInput, evidence_prior: PriorSummary) -> list[PriorSummary]:
    """Build the four contrasting priors from the evidence-derived prior."""

    spread = _spiegelhalter_sd(design.target_effect)
    return [
        evidence_prior.model_copy(update={"method": "evidence-derived prior"}),
        PriorSummary(
            mean=0.0,
            sd=spread,
            pooled_participants=0,
            records_used=0,
            method="skeptical prior (centered at no effect; ~5% mass beyond target)",
        ),
        PriorSummary(
            mean=0.0,
            sd=_REFERENCE_SD,
            pooled_participants=0,
            records_used=0,
            method="reference weakly-informative prior",
        ),
        PriorSummary(
            mean=design.target_effect,
            sd=spread,
            pooled_participants=0,
            records_used=0,
            method="enthusiastic prior (centered at target; ~5% mass below no effect)",
        ),
    ]


_LABELS: list[tuple[str, str]] = [
    ("evidence", "Evidence-derived prior, pooled from the cited records."),
    ("skeptical", "Skeptical: centered at no effect; doubts large effects a priori."),
    ("reference", "Reference: weakly-informative; lets the trial data dominate."),
    ("enthusiastic", "Enthusiastic: centered on the hoped-for target effect."),
]


def prior_sensitivity(
    design: TrialDesignInput,
    evidence_prior: PriorSummary,
    n_per_arm: int,
) -> list[PriorScenario]:
    """Evaluate operating characteristics at ``n_per_arm`` under four contrasting priors."""

    standard_error = effect_standard_error(design, n_per_arm)
    scenarios: list[PriorScenario] = []
    for (label, description), prior in zip(_LABELS, _scenario_priors(design, evidence_prior)):
        posterior = posterior_success_probability_at(
            design.target_effect, prior, standard_error
        )
        scenarios.append(
            PriorScenario(
                label=label,
                description=description,
                prior=prior,
                n_per_arm=n_per_arm,
                assurance=prior_predictive_assurance(
                    n_per_arm, prior, design.alpha, design.endpoint_sd
                )
                if design.endpoint_type == "continuous"
                else _assurance_effect_scale(prior, standard_error, design.alpha),
                posterior_success_probability=posterior,
                predictive_probability_of_success=predictive_probability_of_success(
                    design, prior, n_per_arm
                ),
                meets_decision_threshold=posterior >= design.decision_threshold,
            )
        )
    return scenarios


def _assurance_effect_scale(prior: PriorSummary, standard_error: float, alpha: float) -> float:
    """Assurance for any endpoint, expressed directly on the effect-scale SE."""

    from opentrial.compute.simulation import _assurance_from_se

    return _assurance_from_se(prior, standard_error, alpha)


def build_evidence_prior_for_sensitivity(evidence: list[EvidenceRecord]) -> PriorSummary:
    """Convenience wrapper mirroring the workflow's default prior construction."""

    from opentrial.compute.priors import build_prior

    return build_prior(evidence)
