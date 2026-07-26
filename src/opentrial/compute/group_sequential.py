"""Group-sequential designs: interim looks with Type-I-controlled efficacy boundaries.

A fixed-sample trial looks at the data once. A *group-sequential* trial plans several
interim looks and may stop early for efficacy. The FDA Adaptive Designs guidance
(section V.A.) frames both the promise and the pitfall:

* Promise -- stopping early when the evidence is compelling reduces the *expected* sample
  size. The guidance cites roughly a 15% reduction for a single interim look at half the
  information with an O'Brien-Fleming boundary.
* Pitfall -- testing at the nominal alpha at every look inflates the overall Type I error.
  The interim and final boundaries must *spend* the alpha so the whole design still controls
  it at, say, 0.025.

This module implements the two classic efficacy boundary shapes named in the guidance --
**O'Brien-Fleming** (stringent early, easy late) and **Pocock** (constant) -- and calibrates
their scale *by simulation* so the overall one-sided Type I error equals the nominal alpha:
under the null the crossing statistic ``max_k Z_k / shape_k`` has some distribution, and the
boundary multiplier is simply its ``1 - alpha`` quantile. The reported Type I error is then
re-estimated on a *fresh, independent* null sample, so it is an out-of-sample check that can
actually reveal miscalibration rather than a tautology. Standard library :mod:`random` only.

The design is summarized on the same information scale the rest of the engine uses, so it
works for continuous and binary endpoints alike: information at the final look is
``1 / SE(n_max)^2`` and accrues linearly across equally-spaced looks.
"""

from __future__ import annotations

import math
import random

from opentrial.compute.simulation import effect_standard_error, recommend_sample_size
from opentrial.compute.simulation import simulate_design_grid
from opentrial.schemas import (
    GroupSequentialResult,
    InterimLook,
    TrialDesignInput,
)


def _boundary_shape(boundary: str, information_fractions: list[float]) -> list[float]:
    """Per-look boundary *shape* on the z-scale (scaled later to control Type I).

    O'Brien-Fleming boundaries are proportional to ``1 / sqrt(t_k)`` -- very high early,
    approaching the fixed-sample critical value at the end. Pocock boundaries are constant
    across looks.
    """

    if boundary == "obrien-fleming":
        return [1.0 / math.sqrt(t) for t in information_fractions]
    if boundary == "pocock":
        return [1.0 for _ in information_fractions]
    raise ValueError(f"Unknown boundary type: {boundary!r}")


def _standardized_paths(
    n_looks: int, n_sims: int, rng: random.Random
) -> list[list[float]]:
    """Simulate ``n_sims`` null z-processes: ``Z_k = (sum of k iid N(0,1)) / sqrt(k)``.

    Under the null the standardized partial-sum process is free of the information scale,
    so these paths calibrate the boundary and, with an added drift, also give power.
    """

    paths: list[list[float]] = []
    for _ in range(n_sims):
        cumulative = 0.0
        z_path: list[float] = []
        for k in range(1, n_looks + 1):
            cumulative += rng.gauss(0.0, 1.0)
            z_path.append(cumulative / math.sqrt(k))
        paths.append(z_path)
    return paths


def _quantile(values: list[float], q: float) -> float:
    """Empirical ``q`` quantile (linear interpolation) of ``values``."""

    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = q * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def simulate_group_sequential(
    design: TrialDesignInput,
    n_looks: int = 4,
    boundary: str = "obrien-fleming",
    n_sims: int = 20000,
    seed: int = 42,
    n_max_per_arm: int | None = None,
) -> GroupSequentialResult:
    """Estimate the operating characteristics of a group-sequential version of this design.

    The design's *maximum* per-arm sample size is the fixed-sample size that reaches the
    desired power (the fair comparator), and ``n_looks`` equally-spaced interim analyses
    accrue information up to it. Efficacy boundaries of the requested ``boundary`` shape are
    calibrated so the overall one-sided Type I error equals ``design.alpha``. Because the
    trial can stop early for efficacy, its *expected* sample size falls below the fixed
    design's -- the guidance's headline efficiency gain.
    """

    if n_looks < 1:
        raise ValueError("A group-sequential design needs at least one look.")

    fixed_n = _fixed_sample_size(design)
    n_max = n_max_per_arm if n_max_per_arm is not None else fixed_n
    se_final = effect_standard_error(design, n_max)
    if se_final <= 0:
        raise ValueError("Final-look standard error must be positive.")

    information_fractions = [k / n_looks for k in range(1, n_looks + 1)]
    information_max = 1.0 / (se_final**2)
    n_at_look = [max(1, round(n_max * t)) for t in information_fractions]
    shape = _boundary_shape(boundary, information_fractions)

    calibration_paths = _standardized_paths(n_looks, n_sims, random.Random(seed))

    # Calibrate: crossing statistic under the null is max_k Z_k / shape_k. The boundary
    # multiplier that yields overall Type I = alpha is its (1 - alpha) quantile.
    crossing_stats = [max(z / s for z, s in zip(path, shape)) for path in calibration_paths]
    multiplier = _quantile(crossing_stats, 1 - design.alpha)
    efficacy_z = [multiplier * s for s in shape]

    # Drift per look under the alternative: mean of Z_k is target_effect * sqrt(I_k).
    drift = [design.target_effect * math.sqrt(information_max * t) for t in information_fractions]

    null_cross_by_look = [0] * n_looks
    alt_cross_by_look = [0] * n_looks
    type_i_hits = 0
    power_hits = 0
    null_n_total = 0
    alt_n_total = 0

    # Estimate Type I on a FRESH, independent null sample -- not the calibration paths.
    # Counting crossings on the same paths used to set the boundary would force the rate to
    # equal alpha exactly (a tautology); an out-of-sample sample makes it a genuine check
    # that can actually reveal miscalibration.
    eval_null_paths = _standardized_paths(n_looks, n_sims, random.Random(seed + 2))
    alt_rng = random.Random(seed + 1)
    for null_path in eval_null_paths:
        crossed = False
        for k in range(n_looks):
            if null_path[k] >= efficacy_z[k]:
                null_cross_by_look[k] += 1
                type_i_hits += 1
                null_n_total += n_at_look[k]
                crossed = True
                break
        if not crossed:
            null_n_total += n_max

    for _ in range(n_sims):
        cumulative = 0.0
        crossed = False
        for k in range(n_looks):
            cumulative += alt_rng.gauss(0.0, 1.0)
            z_k = cumulative / math.sqrt(k + 1) + drift[k]
            if z_k >= efficacy_z[k]:
                alt_cross_by_look[k] += 1
                power_hits += 1
                alt_n_total += n_at_look[k]
                crossed = True
                break
        if not crossed:
            alt_n_total += n_max

    # Cumulative stopping probabilities per look.
    null_cumulative = 0
    alt_cumulative = 0
    looks: list[InterimLook] = []
    for k in range(n_looks):
        null_cumulative += null_cross_by_look[k]
        alt_cumulative += alt_cross_by_look[k]
        looks.append(
            InterimLook(
                look=k + 1,
                information_fraction=information_fractions[k],
                n_per_arm=n_at_look[k],
                efficacy_z=efficacy_z[k],
                cumulative_stop_prob_null=null_cumulative / n_sims,
                cumulative_stop_prob_alt=alt_cumulative / n_sims,
            )
        )

    expected_n_alt = alt_n_total / n_sims
    reduction = (fixed_n - expected_n_alt) / fixed_n if fixed_n else 0.0

    return GroupSequentialResult(
        boundary=boundary,
        n_looks=n_looks,
        n_max_per_arm=n_max,
        alpha=design.alpha,
        type_i_error=type_i_hits / n_sims,
        power=power_hits / n_sims,
        expected_n_per_arm_alt=expected_n_alt,
        expected_n_per_arm_null=null_n_total / n_sims,
        fixed_n_per_arm=fixed_n,
        expected_reduction_vs_fixed=reduction,
        looks=looks,
    )


def _fixed_sample_size(design: TrialDesignInput) -> int:
    """The comparable fixed-sample N per arm reaching the design's desired power."""

    grid = simulate_design_grid(design, _null_prior())
    recommendation = recommend_sample_size(grid, design.desired_power)
    return recommendation.n_per_arm if recommendation else design.max_n_per_arm


def _null_prior():
    from opentrial.schemas import PriorSummary

    return PriorSummary(mean=0.0, sd=1.0, pooled_participants=0, records_used=0, method="reference")
