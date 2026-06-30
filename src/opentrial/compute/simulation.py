from __future__ import annotations

import math
from statistics import NormalDist

from opentrial.schemas import DesignPoint, PriorSummary, TrialDesignInput


def _normal_cdf(x: float) -> float:
    return NormalDist().cdf(x)


def _normal_quantile(p: float) -> float:
    return NormalDist().inv_cdf(p)


def _difference_se(n_per_arm: int, endpoint_sd: float) -> float:
    """SE of the difference in arm means for a two-arm CONTINUOUS endpoint.

    ``endpoint_sd`` is the population SD of the endpoint, in the same units as the
    target effect. With endpoint_sd = 1.0 the effect is treated as standardized.
    """

    return math.sqrt((2 * endpoint_sd**2) / n_per_arm)


def effect_standard_error(design: TrialDesignInput, n_per_arm: int) -> float:
    """Effect-scale standard error at ``n_per_arm`` for this design.

    This single quantity is all the power/assurance/posterior formulas need.
    """

    if n_per_arm <= 0:
        return 0.0
    return _difference_se(n_per_arm, design.endpoint_sd)


# --- the four core formulas, expressed once in terms of an effect-scale SE ----------


def _power_from_se(effect: float, standard_error: float, alpha: float) -> float:
    if standard_error <= 0:
        return 0.0
    return 1 - _normal_cdf(_normal_quantile(1 - alpha) - effect / standard_error)


def _assurance_from_se(prior: PriorSummary, standard_error: float, alpha: float) -> float:
    if standard_error <= 0:
        return 0.0
    success_threshold = _normal_quantile(1 - alpha) * standard_error
    marginal_sd = math.sqrt(prior.sd**2 + standard_error**2)
    return 1 - _normal_cdf((success_threshold - prior.mean) / marginal_sd)


def _posterior_from_se(target_effect: float, prior: PriorSummary, standard_error: float) -> float:
    likelihood_variance = standard_error**2
    prior_variance = prior.sd**2
    posterior_variance = 1 / ((1 / prior_variance) + (1 / likelihood_variance))
    posterior_mean = posterior_variance * (
        (prior.mean / prior_variance) + (target_effect / likelihood_variance)
    )
    posterior_sd = math.sqrt(posterior_variance)
    return 1 - _normal_cdf((0 - posterior_mean) / posterior_sd)


# --- public continuous helpers (used by tests and the continuous path) --------------


def estimate_power(
    n_per_arm: int, effect: float, alpha: float, endpoint_sd: float = 1.0
) -> float:
    """Approximate one-sided z-test power for a continuous two-arm endpoint."""

    if n_per_arm <= 0:
        return 0.0
    return _power_from_se(effect, _difference_se(n_per_arm, endpoint_sd), alpha)


def estimate_beta(
    n_per_arm: int, effect: float, alpha: float, endpoint_sd: float = 1.0
) -> float:
    """Approximate type-II error rate at the target effect."""

    return 1 - estimate_power(n_per_arm, effect, alpha, endpoint_sd)


def prior_predictive_assurance(
    n_per_arm: int,
    prior: PriorSummary,
    alpha: float,
    endpoint_sd: float = 1.0,
) -> float:
    """Probability of statistical success averaged over the evidence-derived prior."""

    if n_per_arm <= 0:
        return 0.0
    return _assurance_from_se(prior, _difference_se(n_per_arm, endpoint_sd), alpha)


def posterior_success_probability(
    n_per_arm: int, design: TrialDesignInput, prior: PriorSummary
) -> float:
    """Approximate posterior probability that the treatment effect is positive."""

    return _posterior_from_se(
        design.target_effect, prior, effect_standard_error(design, n_per_arm)
    )


def simulate_design_grid(
    design: TrialDesignInput,
    prior: PriorSummary,
    step: int = 20,
) -> list[DesignPoint]:
    points: list[DesignPoint] = []
    start = max(20, step)
    for n_per_arm in range(start, design.max_n_per_arm + 1, step):
        standard_error = effect_standard_error(design, n_per_arm)
        power = _power_from_se(design.target_effect, standard_error, design.alpha)
        points.append(
            DesignPoint(
                n_per_arm=n_per_arm,
                power=power,
                beta=1 - power,
                type_i_error=design.alpha,
                posterior_success_probability=_posterior_from_se(
                    design.target_effect, prior, standard_error
                ),
                assurance=_assurance_from_se(prior, standard_error, design.alpha),
            )
        )
    return points


def recommend_sample_size(
    grid: list[DesignPoint],
    desired_power: float,
) -> DesignPoint | None:
    for point in grid:
        if point.power >= desired_power:
            return point
    return None
