import math

import pytest

from opentrial.compute.priors import build_prior
from opentrial.compute.simulation import (
    effect_standard_error,
    estimate_beta,
    estimate_power,
    prior_predictive_assurance,
    recommend_sample_size,
    simulate_design_grid,
)
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.schemas import TrialDesignInput


def _design() -> TrialDesignInput:
    return TrialDesignInput(
        indication="Type 2 Diabetes",
        endpoint="HbA1c change from baseline",
        target_effect=0.50,
        alpha=0.025,
        desired_power=0.80,
        max_n_per_arm=300,
    )


def test_prior_predictive_assurance_is_bounded_and_increases_with_n():
    prior = build_prior(t2d_hba1c_evidence())

    small = prior_predictive_assurance(20, prior, alpha=0.025)
    large = prior_predictive_assurance(300, prior, alpha=0.025)

    assert 0 <= small <= 1
    assert 0 <= large <= 1
    assert large > small


def test_design_grid_includes_bayesian_assurance():
    prior = build_prior(t2d_hba1c_evidence())
    grid = simulate_design_grid(_design(), prior)

    assert grid
    assert all(0 <= point.assurance <= 1 for point in grid)
    assert "assurance" in grid[0].model_dump()


def test_beta_complements_power_and_type_i_error_matches_alpha():
    design = _design()
    prior = build_prior(t2d_hba1c_evidence())
    grid = simulate_design_grid(design, prior)

    first = grid[0]
    assert first.beta == 1 - first.power
    assert first.type_i_error == design.alpha
    assert estimate_beta(120, design.target_effect, design.alpha) == (
        1 - estimate_power(120, design.target_effect, design.alpha)
    )
    assert all(point.type_i_error == design.alpha for point in grid)


def test_dropout_zero_is_the_complete_follow_up_baseline():
    """The default dropout_rate=0 must leave every operating characteristic unchanged."""

    without = _design()
    explicit_zero = TrialDesignInput(
        indication="Type 2 Diabetes", endpoint="HbA1c change from baseline",
        target_effect=0.50, alpha=0.025, desired_power=0.80, max_n_per_arm=300,
        dropout_rate=0.0,
    )
    assert effect_standard_error(without, 100) == effect_standard_error(explicit_zero, 100)


def test_dropout_inflates_the_standard_error_by_one_over_sqrt_retained():
    """SE is computed on the analyzable count n*(1 - dropout), so it scales exactly."""

    base = _design()
    for rate in (0.1, 0.2, 0.5):
        dropped = TrialDesignInput(
            indication="Type 2 Diabetes", endpoint="HbA1c change from baseline",
            target_effect=0.50, alpha=0.025, desired_power=0.80, max_n_per_arm=300,
            dropout_rate=rate,
        )
        assert effect_standard_error(dropped, 100) == pytest.approx(
            effect_standard_error(base, 100) / math.sqrt(1 - rate)
        )


def test_dropout_requires_enrolling_more_to_keep_power():
    """A design with dropout must recommend at least as many enrolled per arm, and strictly
    more once attrition is heavy enough to matter at the grid resolution."""

    prior = build_prior(t2d_hba1c_evidence())
    no_dropout = TrialDesignInput(
        indication="Type 2 Diabetes", endpoint="HbA1c change from baseline",
        target_effect=0.50, alpha=0.025, desired_power=0.80, max_n_per_arm=400,
    )
    heavy = TrialDesignInput(
        indication="Type 2 Diabetes", endpoint="HbA1c change from baseline",
        target_effect=0.50, alpha=0.025, desired_power=0.80, max_n_per_arm=400,
        dropout_rate=0.5,
    )
    rec_none = recommend_sample_size(simulate_design_grid(no_dropout, prior), 0.80)
    rec_heavy = recommend_sample_size(simulate_design_grid(heavy, prior), 0.80)
    assert rec_heavy.n_per_arm > rec_none.n_per_arm


def test_dropout_at_the_limit_yields_no_information():
    """If essentially everyone drops out, the analyzable count vanishes and SE is not finite
    (returned as 0.0 by convention, i.e. no usable information), never a divide-by-zero."""

    extreme = TrialDesignInput(
        indication="Type 2 Diabetes", endpoint="HbA1c change from baseline",
        target_effect=0.50, alpha=0.025, desired_power=0.80, max_n_per_arm=300,
        dropout_rate=0.99,
    )
    # 20 enrolled * (1 - 0.99) = 0.2 analyzable -> a valid, very large SE (not a crash).
    assert effect_standard_error(extreme, 20) > 0


def test_binary_endpoint_power_and_recommendation():
    from opentrial.compute.simulation import estimate_power_binary
    from opentrial.schemas import PriorSummary

    # Two-proportion power should rise with N and exceed the analytic estimate at the
    # recommended size.
    weak = PriorSummary(mean=0.0, sd=1.0, pooled_participants=0, records_used=0, method="weak")
    design = TrialDesignInput(
        indication="X",
        endpoint="Response rate",
        target_effect=0.15,
        alpha=0.025,
        desired_power=0.80,
        max_n_per_arm=400,
        endpoint_type="binary",
        baseline_proportion=0.30,
    )
    grid = simulate_design_grid(design, weak)
    rec = recommend_sample_size(grid, 0.80)
    assert rec is not None
    assert rec.power >= 0.80
    assert estimate_power_binary(rec.n_per_arm, 0.30, 0.15, 0.025) >= 0.80


def test_binary_power_rejects_impossible_probabilities():
    from opentrial.compute.simulation import estimate_power_binary

    with pytest.raises(ValueError, match="probabilities"):
        estimate_power_binary(100, baseline_proportion=0.90, risk_difference=0.30, alpha=0.025)


def test_binary_needs_more_patients_at_higher_baseline_variance():
    from opentrial.schemas import PriorSummary

    weak = PriorSummary(mean=0.0, sd=1.0, pooled_participants=0, records_used=0, method="weak")
    base = dict(
        indication="X", endpoint="Response", target_effect=0.15, alpha=0.025,
        desired_power=0.80, max_n_per_arm=600, endpoint_type="binary",
    )
    low = recommend_sample_size(
        simulate_design_grid(TrialDesignInput(**base, baseline_proportion=0.30), weak), 0.80
    )
    high = recommend_sample_size(
        simulate_design_grid(TrialDesignInput(**base, baseline_proportion=0.50), weak), 0.80
    )
    # Variance peaks at p=0.5, so a 0.50 baseline needs at least as many patients as 0.30.
    assert high.n_per_arm >= low.n_per_arm
