from opentrial.compute.mc import simulate_operating_characteristics
from opentrial.compute.priors import build_prior
from opentrial.compute.simulation import simulate_design_grid
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


def test_mc_grid_matches_analytic_grid_shape():
    prior = build_prior(t2d_hba1c_evidence())
    analytic = simulate_design_grid(_design(), prior)
    mc = simulate_operating_characteristics(_design(), prior, n_sims=500, seed=1)
    assert [p.n_per_arm for p in mc] == [p.n_per_arm for p in analytic]


def test_mc_power_tracks_analytic_power():
    prior = build_prior(t2d_hba1c_evidence())
    analytic = {p.n_per_arm: p.power for p in simulate_design_grid(_design(), prior)}
    mc = simulate_operating_characteristics(_design(), prior, n_sims=4000, seed=42)
    for point in mc:
        assert abs(point.power - analytic[point.n_per_arm]) < 0.05


def test_mc_type_i_error_is_calibrated_near_alpha():
    prior = build_prior(t2d_hba1c_evidence())
    mc = simulate_operating_characteristics(_design(), prior, n_sims=8000, seed=7)
    # Empirical false-positive rate under the null should land near the nominal alpha.
    for point in mc:
        assert abs(point.type_i_error - 0.025) < 0.02


def test_mc_is_deterministic_with_seed():
    prior = build_prior(t2d_hba1c_evidence())
    first = simulate_operating_characteristics(_design(), prior, n_sims=1000, seed=99)
    second = simulate_operating_characteristics(_design(), prior, n_sims=1000, seed=99)
    assert [p.power for p in first] == [p.power for p in second]
    assert [p.type_i_error for p in first] == [p.type_i_error for p in second]
