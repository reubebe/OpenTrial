"""Monte Carlo operating characteristics.

The default :mod:`opentrial.compute.simulation` engine uses an exact closed-form normal
approximation. For the simple two-arm z-test that is exact, so this Monte Carlo engine does
not change the answer -- its value is twofold:

* It *estimates* the type-I error empirically by simulating under the null, instead of just
  echoing the nominal alpha. For a well-specified design the two should match, which is a
  genuine calibration check a reviewer can see.
* It is the natural place to grow more realistic designs later (non-normal endpoints,
  group-sequential looks, dropout), where no closed form exists.

It is implemented with the standard-library :mod:`random` only -- no NumPy -- so it stays in
the default install. It is opt-in from the UI because it is slower than the instant analytic
grid.
"""

from __future__ import annotations

import random
from statistics import NormalDist

from opentrial.compute.simulation import effect_standard_error, posterior_success_probability
from opentrial.schemas import DesignPoint, PriorSummary, TrialDesignInput


def simulate_operating_characteristics(
    design: TrialDesignInput,
    prior: PriorSummary,
    n_sims: int = 2000,
    step: int = 20,
    seed: int = 42,
) -> list[DesignPoint]:
    """Estimate power, type-I error, and assurance by simulation, per sample size.

    For each N per arm we draw ``n_sims`` trials and apply the one-sided decision rule
    (reject when the observed arm-mean difference exceeds ``z_alpha * SE``):

    * power   -- true effect fixed at the target effect.
    * type-I  -- true effect fixed at zero (the null); the empirical rejection rate
                 should land near the nominal alpha.
    * assurance -- the true effect drawn from the evidence-derived prior each trial.

    The arm-mean difference is its (asymptotically normal) sampling distribution,
    ``Normal(true_effect, SE)``, which is the standard summary-level Monte Carlo for a
    continuous two-arm comparison. Posterior Pr(effect > 0) stays analytic (a conjugate
    update, not a frequentist quantity).
    """

    rng = random.Random(seed)
    z_alpha = NormalDist().inv_cdf(1 - design.alpha)
    points: list[DesignPoint] = []
    start = max(20, step)

    for n_per_arm in range(start, design.max_n_per_arm + 1, step):
        standard_error = effect_standard_error(design, n_per_arm)
        critical_value = z_alpha * standard_error

        power_hits = 0
        type_i_hits = 0
        assurance_hits = 0
        for _ in range(n_sims):
            if rng.gauss(design.target_effect, standard_error) > critical_value:
                power_hits += 1
            if rng.gauss(0.0, standard_error) > critical_value:
                type_i_hits += 1
            true_effect = rng.gauss(prior.mean, prior.sd)
            if rng.gauss(true_effect, standard_error) > critical_value:
                assurance_hits += 1

        power = power_hits / n_sims
        points.append(
            DesignPoint(
                n_per_arm=n_per_arm,
                power=power,
                beta=1 - power,
                type_i_error=type_i_hits / n_sims,
                posterior_success_probability=posterior_success_probability(
                    n_per_arm, design, prior
                ),
                assurance=assurance_hits / n_sims,
            )
        )
    return points
