"""Bayesian decision criteria: a posterior success rule and predictive success.

The default engine reports frequentist power alongside a posterior probability that the
effect is positive. Real Bayesian and adaptive trials, however, *decide* on a Bayesian
scale: the FDA Complex Innovative Trial Designs guidance describes decision criteria such
as ``Pr(effect > 0) > 0.99``, and the I-SPY 2 platform trial graduates an agent when the
*predictive probability* of success in a future confirmatory trial reaches 85%.

This module expresses both, in closed form, for the same normal model the rest of the
engine uses:

* **Posterior success probability** -- given the planned trial's *point* estimate lands on
  the target effect, the posterior probability the true effect exceeds zero.
* **Predictive probability of success (PPoS)** -- averaging over the evidence-derived prior
  (the prior-predictive distribution of the trial's estimate), the probability the trial
  will *meet the decision threshold* ``Pr(effect > 0 | data) >= gamma``. This is the
  planning analogue of I-SPY 2's graduation rule.

Standard library only; no sampling required.
"""

from __future__ import annotations

import math
from statistics import NormalDist

from opentrial.compute.simulation import effect_standard_error
from opentrial.schemas import DecisionSummary, PriorSummary, TrialDesignInput

_STANDARD_NORMAL = NormalDist()


def posterior_success_probability_at(
    observed_effect: float, prior: PriorSummary, standard_error: float
) -> float:
    """Posterior Pr(effect > 0) after observing ``observed_effect`` with ``standard_error``."""

    if standard_error <= 0:
        return 0.0
    prior_variance = prior.sd**2
    likelihood_variance = standard_error**2
    posterior_variance = 1.0 / ((1.0 / prior_variance) + (1.0 / likelihood_variance))
    posterior_mean = posterior_variance * (
        (prior.mean / prior_variance) + (observed_effect / likelihood_variance)
    )
    return _STANDARD_NORMAL.cdf(posterior_mean / math.sqrt(posterior_variance))


def predictive_probability_of_success(
    design: TrialDesignInput,
    prior: PriorSummary,
    n_per_arm: int,
    threshold: float | None = None,
) -> float:
    """Prior-predictive probability the trial meets its Bayesian decision threshold.

    Success is defined as the final posterior clearing the threshold,
    ``Pr(effect > 0 | data) >= gamma``. Because the posterior mean is linear in the
    observed estimate, that event is equivalent to the estimate exceeding a fixed cutoff,
    and the estimate's prior-predictive law is ``Normal(prior.mean, prior.sd^2 + SE^2)``.
    Integrating gives a closed form -- no simulation needed.
    """

    gamma = design.decision_threshold if threshold is None else threshold
    standard_error = effect_standard_error(design, n_per_arm)
    if standard_error <= 0:
        return 0.0

    prior_variance = prior.sd**2
    likelihood_variance = standard_error**2
    posterior_variance = 1.0 / ((1.0 / prior_variance) + (1.0 / likelihood_variance))
    z_gamma = _STANDARD_NORMAL.inv_cdf(gamma)

    # Posterior mean >= z_gamma * posterior_sd  <=>  observed estimate >= cutoff.
    cutoff = (
        likelihood_variance * z_gamma / math.sqrt(posterior_variance)
        - likelihood_variance * prior.mean / prior_variance
    )
    marginal_sd = math.sqrt(prior_variance + likelihood_variance)
    return 1.0 - _STANDARD_NORMAL.cdf((cutoff - prior.mean) / marginal_sd)


def summarize_decision(
    design: TrialDesignInput,
    prior: PriorSummary,
    n_per_arm: int,
) -> DecisionSummary:
    """Bundle the posterior and predictive success readouts at ``n_per_arm``."""

    posterior = posterior_success_probability_at(
        design.target_effect, prior, effect_standard_error(design, n_per_arm)
    )
    predictive = predictive_probability_of_success(design, prior, n_per_arm)
    return DecisionSummary(
        n_per_arm=n_per_arm,
        decision_threshold=design.decision_threshold,
        posterior_success_probability=posterior,
        predictive_probability_of_success=predictive,
        meets_decision_threshold=posterior >= design.decision_threshold,
    )
