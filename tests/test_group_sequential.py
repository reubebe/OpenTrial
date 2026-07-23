import pytest

from opentrial.compute.group_sequential import simulate_group_sequential
from opentrial.schemas import TrialDesignInput


def _design(**overrides):
    base = dict(
        indication="Type 2 Diabetes",
        endpoint="HbA1c",
        target_effect=0.5,
        alpha=0.025,
        desired_power=0.8,
        max_n_per_arm=300,
    )
    base.update(overrides)
    return TrialDesignInput(**base)


def test_type_i_error_is_calibrated_to_alpha():
    """Boundaries are calibrated so overall Type I equals the nominal alpha."""

    design = _design()
    result = simulate_group_sequential(design, n_looks=4, boundary="obrien-fleming")
    assert result.type_i_error == pytest.approx(design.alpha, abs=0.003)


def test_type_i_error_is_measured_out_of_sample_not_tautological():
    """Type I must be estimated on a fresh null sample, so it *varies* across seeds.

    If it were counted on the same paths used to calibrate the boundary, it would equal
    alpha exactly for every seed -- a tautology that can never reveal miscalibration. A
    genuine out-of-sample estimate has Monte-Carlo variability.
    """

    design = _design()
    rates = {
        simulate_group_sequential(
            design, n_looks=4, boundary="obrien-fleming", n_sims=20000, seed=s
        ).type_i_error
        for s in range(5)
    }
    assert len(rates) > 1, "Type I identical across seeds -> in-sample tautology"
    assert all(abs(r - design.alpha) < 0.004 for r in rates)


def test_expected_sample_size_is_below_the_fixed_design():
    """The efficiency gain: expected N under the alternative is smaller than fixed N."""

    design = _design()
    result = simulate_group_sequential(design, n_looks=2, boundary="obrien-fleming")
    assert result.expected_n_per_arm_alt < result.fixed_n_per_arm
    # The guidance cites roughly a 15% reduction for one interim look with O'Brien-Fleming.
    assert 0.05 < result.expected_reduction_vs_fixed < 0.30


def test_obrien_fleming_boundaries_decrease_toward_the_final_look():
    design = _design()
    result = simulate_group_sequential(design, n_looks=4, boundary="obrien-fleming")
    efficacy = [look.efficacy_z for look in result.looks]
    assert efficacy == sorted(efficacy, reverse=True)
    # The final boundary sits near the fixed-sample critical value (~1.96 for alpha=0.025).
    assert efficacy[-1] == pytest.approx(1.96, abs=0.15)


def test_pocock_boundaries_are_constant():
    design = _design()
    result = simulate_group_sequential(design, n_looks=4, boundary="pocock")
    efficacy = [round(look.efficacy_z, 6) for look in result.looks]
    assert len(set(efficacy)) == 1


def test_more_looks_never_reduce_power_below_a_reasonable_floor():
    design = _design()
    result = simulate_group_sequential(design, n_looks=4, boundary="obrien-fleming")
    assert result.power > 0.75


def test_unknown_boundary_is_rejected():
    with pytest.raises(ValueError):
        simulate_group_sequential(_design(), boundary="made-up")
