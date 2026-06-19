from __future__ import annotations

import math
from statistics import NormalDist

from opentrial.schemas import DesignPoint, PriorSummary, TrialDesignInput

STANDARDIZED_ENDPOINT_SD = 1.0


def _normal_cdf(x: float) -> float:
    return NormalDist().cdf(x)


def _normal_quantile(p: float) -> float:
    return NormalDist().inv_cdf(p)


def estimate_power(n_per_arm: int, effect: float, alpha: float) -> float:
    """Approximate one-sided z-test power for a continuous two-arm endpoint."""

    if n_per_arm <= 0:
        return 0.0
    standard_error = math.sqrt((2 * STANDARDIZED_ENDPOINT_SD**2) / n_per_arm)
    z_alpha = _normal_quantile(1 - alpha)
    z_effect = effect / standard_error
    return 1 - _normal_cdf(z_alpha - z_effect)


def posterior_success_probability(n_per_arm: int, design: TrialDesignInput, prior: PriorSummary) -> float:
    """Approximate posterior probability that the treatment effect is positive."""

    likelihood_variance = (2 * STANDARDIZED_ENDPOINT_SD**2) / n_per_arm
    prior_variance = prior.sd**2
    posterior_variance = 1 / ((1 / prior_variance) + (1 / likelihood_variance))
    posterior_mean = posterior_variance * (
        (prior.mean / prior_variance) + (design.target_effect / likelihood_variance)
    )
    posterior_sd = math.sqrt(posterior_variance)
    return 1 - _normal_cdf((0 - posterior_mean) / posterior_sd)


def simulate_design_grid(
    design: TrialDesignInput,
    prior: PriorSummary,
    step: int = 20,
) -> list[DesignPoint]:
    points: list[DesignPoint] = []
    start = max(20, step)
    for n_per_arm in range(start, design.max_n_per_arm + 1, step):
        points.append(
            DesignPoint(
                n_per_arm=n_per_arm,
                power=estimate_power(n_per_arm, design.target_effect, design.alpha),
                posterior_success_probability=posterior_success_probability(
                    n_per_arm, design, prior
                ),
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
