import math

from opentrial.compute.decision import (
    posterior_success_probability_at,
    predictive_probability_of_success,
    summarize_decision,
)
from opentrial.schemas import PriorSummary, TrialDesignInput


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


def test_posterior_probability_rises_with_a_larger_observed_effect():
    prior = PriorSummary(mean=0.0, sd=1.0, pooled_participants=0, records_used=0, method="reference")
    weak = posterior_success_probability_at(0.1, prior, 0.2)
    strong = posterior_success_probability_at(0.8, prior, 0.2)
    assert 0.0 < weak < strong < 1.0


def test_predictive_probability_is_bounded_and_orders_by_prior_optimism():
    design = _design()
    optimistic = PriorSummary(mean=0.5, sd=0.2, pooled_participants=0, records_used=0, method="up")
    null = PriorSummary(mean=0.0, sd=0.2, pooled_participants=0, records_used=0, method="null")
    p_optimistic = predictive_probability_of_success(design, optimistic, n_per_arm=80)
    p_null = predictive_probability_of_success(design, null, n_per_arm=80)
    assert 0.0 <= p_null < p_optimistic <= 1.0


def test_skeptical_null_prior_makes_predictive_success_hard():
    """A prior centered at no effect should rarely predict clearing the threshold."""

    design = _design()
    skeptical = PriorSummary(mean=0.0, sd=0.1, pooled_participants=0, records_used=0, method="skeptical")
    assert predictive_probability_of_success(design, skeptical, n_per_arm=80) < 0.1


def test_summarize_decision_flags_threshold():
    design = _design(decision_threshold=0.975)
    prior = PriorSummary(mean=0.5, sd=0.1, pooled_participants=400, records_used=4, method="evidence")
    summary = summarize_decision(design, prior, n_per_arm=80)
    assert summary.n_per_arm == 80
    assert summary.decision_threshold == 0.975
    assert summary.meets_decision_threshold is (
        summary.posterior_success_probability >= 0.975
    )
    assert not math.isnan(summary.predictive_probability_of_success)
