from opentrial.compute.priors import build_prior
from opentrial.compute.sensitivity import prior_sensitivity
from opentrial.data.demo_evidence import t2d_hba1c_evidence
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


def test_sensitivity_returns_the_four_named_scenarios():
    design = _design()
    prior = build_prior(t2d_hba1c_evidence())
    scenarios = prior_sensitivity(design, prior, n_per_arm=80)
    assert [s.label for s in scenarios] == ["evidence", "skeptical", "reference", "enthusiastic"]
    for scenario in scenarios:
        assert scenario.n_per_arm == 80
        assert 0.0 <= scenario.assurance <= 1.0
        assert 0.0 <= scenario.predictive_probability_of_success <= 1.0


def test_skeptical_prior_is_least_assured_evidence_most():
    """The point of the analysis: assurance depends on the prior, and in a sensible order."""

    design = _design()
    prior = build_prior(t2d_hba1c_evidence())
    by_label = {s.label: s for s in prior_sensitivity(design, prior, n_per_arm=80)}
    assert by_label["skeptical"].assurance < by_label["reference"].assurance
    assert by_label["reference"].assurance < by_label["enthusiastic"].assurance
    assert by_label["skeptical"].assurance < by_label["evidence"].assurance


def test_scenario_prior_centers_match_their_intent():
    design = _design()
    prior = build_prior(t2d_hba1c_evidence())
    by_label = {s.label: s for s in prior_sensitivity(design, prior, n_per_arm=80)}
    assert by_label["skeptical"].prior.mean == 0.0
    assert by_label["reference"].prior.mean == 0.0
    assert by_label["enthusiastic"].prior.mean == design.target_effect
