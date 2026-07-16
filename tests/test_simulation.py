import pytest

from opentrial.compute.priors import build_prior
from opentrial.compute.simulation import (
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

