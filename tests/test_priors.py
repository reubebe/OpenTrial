import math

import pytest

from opentrial.compute.priors import MIN_PRIOR_SD, build_prior
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.schemas import EvidenceRecord


def _record(effect: float, standard_error: float, n: int = 100) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_kind="effect_estimate",
        source="test",
        title="t",
        effect=effect,
        standard_error=standard_error,
        n=n,
        endpoint="HbA1c",
        indication="Type 2 Diabetes",
        year=2024,
        url="https://example.org",
    )


def test_records_without_a_standard_error_never_move_the_prior():
    """The honesty rule: no usable effect means no contribution."""

    prior = build_prior([_record(0.5, 0.0)])
    assert prior.records_used == 0
    assert prior.mean == 0.0
    assert prior.sd == 1.0


def test_a_single_record_reproduces_its_own_standard_error():
    prior = build_prior([_record(0.4, 0.2)])
    assert prior.mean == pytest.approx(0.4)
    assert prior.sd == pytest.approx(0.2)


def test_precise_studies_pull_the_mean_harder_when_studies_agree():
    """With no heterogeneity the weighting is pure inverse-variance."""

    # Two studies that agree within noise, so tau^2 = 0 and the precise one dominates 25:1.
    prior = build_prior([_record(0.9, 0.5), _record(1.0, 0.1)])
    assert prior.mean > 0.99


def test_heterogeneity_flattens_the_weighting_between_studies():
    """A documented property of random-effects, easily mistaken for a bug.

    Adding tau^2 to every study's variance shrinks the *ratio* between weights, so a precise
    study stops dominating a vague one once they genuinely disagree. Under fixed-effect
    weighting these two would pool to 0.96; random-effects pulls it back toward the midpoint
    because the disagreement itself is evidence that neither estimate is the whole story.
    """

    prior = build_prior([_record(0.0, 0.5), _record(1.0, 0.1)])
    assert "random-effects" in prior.method
    assert 0.5 < prior.mean < 0.8


def test_homogeneous_studies_give_tau_squared_zero_and_collapse_to_fixed_effect():
    """Scatter explainable by sampling error alone must not widen the prior.

    This is the regression test for the original defect: the prior SD was inflated by the
    sample SD of the observed effects, which contains within-study sampling error as well as
    heterogeneity. On evidence with no detectable heterogeneity that term is pure
    double-counting, so the prior came out wider than the evidence warrants.
    """

    # Four identical estimates: zero observed scatter, so certainly no heterogeneity.
    records = [_record(0.5, 0.1) for _ in range(4)]
    prior = build_prior(records)

    fixed_sd = math.sqrt(1.0 / sum(1.0 / 0.1**2 for _ in range(4)))
    assert prior.sd == pytest.approx(fixed_sd, abs=1e-9)
    assert "tau^2 = 0" in prior.method


def test_genuinely_heterogeneous_studies_do_widen_the_prior():
    """The estimator must still respond when studies really do disagree."""

    tight = build_prior([_record(0.5, 0.05), _record(0.5, 0.05)])
    spread = build_prior([_record(0.0, 0.05), _record(1.0, 0.05)])
    # Same precision, wildly different effects: Q far exceeds its expectation.
    assert spread.sd > tight.sd
    assert "random-effects" in spread.method


def test_heterogeneity_is_not_the_sample_sd_of_the_effects():
    """Guards the specific formula, not just the direction.

    The old implementation used sd = sqrt(fixed_sd^2 + sampleSD^2). On homogeneous evidence
    that is strictly wider than the correct answer, so pinning the correct value keeps the
    old formula from creeping back.
    """

    records = [_record(0.48, 0.12), _record(0.62, 0.15), _record(0.55, 0.10), _record(0.43, 0.09)]
    prior = build_prior(records)

    weights = [1 / se**2 for se in (0.12, 0.15, 0.10, 0.09)]
    fixed_sd = math.sqrt(1 / sum(weights))
    mean = sum(w * e for w, e in zip(weights, (0.48, 0.62, 0.55, 0.43))) / sum(weights)
    sample_sd = math.sqrt(sum((e - mean) ** 2 for e in (0.48, 0.62, 0.55, 0.43)) / 3)
    old_answer = math.sqrt(fixed_sd**2 + sample_sd**2)

    # Cochran's Q here is 1.52 on 3 df, below its expectation, so tau^2 = 0.
    assert prior.sd == pytest.approx(fixed_sd, abs=1e-6)
    assert prior.sd < old_answer


def test_the_prior_is_never_narrower_than_the_floor():
    # Two very precise, perfectly agreeing studies would otherwise imply an implausible prior.
    prior = build_prior([_record(0.5, 0.001), _record(0.5, 0.001)])
    assert prior.sd == pytest.approx(MIN_PRIOR_SD)


def test_the_demo_prior_is_stable_and_documented():
    """Pins the seeded demo, which METHODS.md and the README both quote."""

    prior = build_prior(list(t2d_hba1c_evidence()))
    assert prior.records_used == 4
    assert prior.effective_n == 2564
    assert prior.mean == pytest.approx(0.5009, abs=5e-4)
    assert prior.sd == pytest.approx(0.0544, abs=5e-4)
