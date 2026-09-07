import math

import pytest

from opentrial.compute.priors import MIN_PRIOR_SD, build_prior
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.schemas import EvidenceRecord


def _record(
    effect: float,
    standard_error: float,
    n: int = 100,
    *,
    url: str = "https://example.org",
    title: str = "t",
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_kind="effect_estimate",
        source="test",
        title=title,
        effect=effect,
        standard_error=standard_error,
        n=n,
        endpoint="HbA1c",
        indication="Type 2 Diabetes",
        year=2024,
        url=url,
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

    # Four distinct studies with identical estimates: zero observed scatter, so certainly no
    # heterogeneity. Distinct registry ids keep de-duplication from collapsing them into one.
    records = [
        _record(0.5, 0.1, url=f"https://clinicaltrials.gov/study/NCT{i:08d}") for i in range(4)
    ]
    prior = build_prior(records)

    fixed_sd = math.sqrt(1.0 / sum(1.0 / 0.1**2 for _ in range(4)))
    assert prior.sd == pytest.approx(fixed_sd, abs=1e-9)
    assert "tau^2 = 0" in prior.method


def test_genuinely_heterogeneous_studies_do_widen_the_prior():
    """The estimator must still respond when studies really do disagree."""

    tight = build_prior(
        [
            _record(0.5, 0.05, url="https://clinicaltrials.gov/study/NCT00000001"),
            _record(0.5, 0.05, url="https://clinicaltrials.gov/study/NCT00000002"),
        ]
    )
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
    prior = build_prior(
        [
            _record(0.5, 0.001, url="https://clinicaltrials.gov/study/NCT00000001"),
            _record(0.5, 0.001, url="https://clinicaltrials.gov/study/NCT00000002"),
        ]
    )
    assert prior.sd == pytest.approx(MIN_PRIOR_SD)


def test_the_demo_prior_is_stable_and_documented():
    """Pins the seeded demo, which METHODS.md and the README both quote."""

    prior = build_prior(list(t2d_hba1c_evidence()))
    assert prior.records_used == 4
    assert prior.pooled_participants == 2564
    assert prior.mean == pytest.approx(0.5009, abs=5e-4)
    assert prior.sd == pytest.approx(0.0544, abs=5e-4)


def test_reml_is_opt_in_and_labels_itself():
    """Selecting REML changes the method label but leaves the pipeline shape unchanged."""

    records = [_record(0.0, 0.05), _record(1.0, 0.05)]
    reml = build_prior(records, tau_method="reml")
    assert "REML" in reml.method
    assert "random-effects" in reml.method
    assert reml.records_used == 2


def test_reml_and_dl_agree_when_studies_are_homogeneous():
    """With no detectable heterogeneity both estimators collapse to the fixed-effect prior."""

    records = [
        _record(0.5, 0.1, url=f"https://clinicaltrials.gov/study/NCT{i:08d}") for i in range(4)
    ]
    dl = build_prior(records, tau_method="dl")
    reml = build_prior(records, tau_method="reml")

    fixed_sd = math.sqrt(1.0 / sum(1.0 / 0.1**2 for _ in range(4)))
    assert reml.sd == pytest.approx(fixed_sd, abs=1e-9)
    assert reml.mean == pytest.approx(dl.mean, abs=1e-9)
    assert "tau^2 = 0" in reml.method


def test_reml_reaches_a_fixed_point_of_its_estimating_equation():
    """The returned tau^2 must actually solve the REML equation it iterates, not merely stop.

    Recomputing one more step from the converged value should not move it, which is the
    definition of the fixed point and guards against an off-by-one or early-exit bug.
    """

    from opentrial.compute.priors import _reml_tau_squared

    effects = [0.1, 0.9, 0.3, 0.7]
    variances = [0.04, 0.05, 0.03, 0.06]
    tau2 = _reml_tau_squared(effects, variances, initial_tau_squared=0.0)
    assert tau2 > 0.0

    weights = [1.0 / (v + tau2) for v in variances]
    total = sum(weights)
    mean = sum(w * y for w, y in zip(weights, effects)) / total
    numerator = sum(
        w**2 * ((y - mean) ** 2 - v) for w, y, v in zip(weights, effects, variances)
    )
    denominator = sum(w**2 for w in weights)
    one_more_step = max(0.0, numerator / denominator + 1.0 / total)
    assert one_more_step == pytest.approx(tau2, abs=1e-8)


def test_reml_is_steadier_than_dl_when_dl_truncates_at_small_k():
    """The point of offering REML: it detects heterogeneity DL's moment estimator misses.

    These studies scatter more than sampling error alone explains, but not by enough for
    Cochran's Q to clear its expectation, so DerSimonian-Laird truncates tau^2 to zero. REML,
    which does not rely on that single moment threshold, still returns a positive tau^2 and so
    a wider, more honest prior. (Effects and SEs found by search to sit in exactly this gap.)
    """

    effects = [0.549, 0.666, 0.374, 0.612, 0.324]
    ses = [0.196, 0.155, 0.295, 0.294, 0.126]
    records = [_record(e, se) for e, se in zip(effects, ses)]
    dl = build_prior(records, tau_method="dl")
    reml = build_prior(records, tau_method="reml")

    assert "tau^2 = 0" in dl.method
    assert "REML random-effects" in reml.method
    assert reml.sd > dl.sd


def test_a_single_record_reproduces_itself_under_reml_too():
    prior = build_prior([_record(0.4, 0.2)], tau_method="reml")
    assert prior.mean == pytest.approx(0.4)
    assert prior.sd == pytest.approx(0.2)


def test_reml_prefers_the_boundary_when_it_beats_an_interior_stationary_point():
    """Regression test for a bimodal restricted profile likelihood.

    On this evidence the REML estimating equation has an interior stationary point at
    tau^2 ~= 0.0316, and the naive fixed-point iteration (seeded from DerSimonian-Laird)
    converges straight to it. But the restricted likelihood is actually *higher* at the
    boundary tau^2 = 0, so the correct REML estimate is 0. The estimator must maximize the
    likelihood, not merely solve the estimating equation, or it silently returns an inflated
    prior here. Found by an independent SciPy cross-check.
    """

    from opentrial.compute.priors import _reml_restricted_loglik, _reml_tau_squared

    effects = [0.3751, -0.0638, 0.3095, 0.0854, 0.803, 0.8441, 0.339]
    variances = [se**2 for se in (0.0555, 0.2673, 0.3921, 0.2326, 0.2497, 0.2164, 0.0567)]

    # The boundary genuinely wins on likelihood, and the trap point is a real stationary point.
    assert _reml_restricted_loglik(0.0, effects, variances) > _reml_restricted_loglik(
        0.0316, effects, variances
    )
    tau2 = _reml_tau_squared(effects, variances, initial_tau_squared=0.0)
    assert tau2 == pytest.approx(0.0, abs=1e-9)
    assert tau2 != pytest.approx(0.0316, abs=1e-3)  # must not land on the interior trap

    records = [_record(e, se) for e, se in zip(effects, (0.0555, 0.2673, 0.3921, 0.2326, 0.2497, 0.2164, 0.0567))]
    prior = build_prior(records, tau_method="reml")
    assert "REML tau^2 = 0" in prior.method


def test_reml_is_independent_of_the_starting_value():
    """The estimate must be the same however the internal search bracket is seeded."""

    from opentrial.compute.priors import _reml_tau_squared

    effects = [0.2, 0.9, 0.35, 0.75, 0.5]
    variances = [se**2 for se in (0.1, 0.12, 0.2, 0.15, 0.11)]
    from_zero = _reml_tau_squared(effects, variances, initial_tau_squared=0.0)
    from_big = _reml_tau_squared(effects, variances, initial_tau_squared=5.0)
    assert from_zero == pytest.approx(from_big, abs=1e-8)
    assert from_zero > 0.0


def test_duplicate_reports_of_one_trial_are_merged_by_registry_id():
    """Two papers sharing an NCT id are one trial and must be pooled once, keeping the
    more informative (larger-n) report."""

    from opentrial.compute.priors import deduplicate_trial_records

    records = [
        _record(0.5, 0.10, 200, url="https://clinicaltrials.gov/study/NCT01234567"),
        _record(0.52, 0.14, 120, title="secondary publication of NCT01234567"),
        _record(0.30, 0.09, 150, url="https://example.org/other-trial"),
    ]
    kept, removed = deduplicate_trial_records(records)
    assert removed == 1
    assert len(kept) == 2
    # The larger-n report of the shared trial survives.
    assert kept[0].n == 200


def test_exact_duplicate_effect_records_are_merged_without_a_registry_id():
    """Same primary numbers, no NCT id: still one trial, so counted once."""

    from opentrial.compute.priors import deduplicate_trial_records

    records = [_record(0.5, 0.1, 100), _record(0.5, 0.1, 100)]
    kept, removed = deduplicate_trial_records(records)
    assert removed == 1
    assert len(kept) == 1


def test_distinct_trials_are_never_merged():
    """Different effects are different trials; de-duplication must not touch them."""

    from opentrial.compute.priors import deduplicate_trial_records

    records = [_record(0.4, 0.1, 100), _record(0.6, 0.1, 100), _record(0.5, 0.12, 90)]
    kept, removed = deduplicate_trial_records(records)
    assert removed == 0
    assert len(kept) == 3


def test_double_counting_a_trial_would_wrongly_narrow_the_prior():
    """The reason de-duplication matters: a trial entered twice inflates precision.

    Pooling the same strong study twice halves its variance contribution, producing a
    falsely narrow prior. After de-duplication the prior matches the single-study prior.
    """

    once = build_prior([_record(0.5, 0.1, 100)])
    twice_raw = [
        _record(0.5, 0.1, 100, url="https://clinicaltrials.gov/study/NCT09999999"),
        _record(0.5, 0.1, 100, title="duplicate report of NCT09999999"),
    ]
    deduped = build_prior(twice_raw)
    assert deduped.records_merged == 1
    assert deduped.records_used == 1
    assert deduped.sd == pytest.approx(once.sd)


def test_the_demo_evidence_has_no_duplicates_to_merge():
    """Guards the poster numbers: de-duplication must be a no-op on the seeded demo."""

    prior = build_prior(list(t2d_hba1c_evidence()))
    assert prior.records_merged == 0
    assert prior.records_used == 4
    assert prior.mean == pytest.approx(0.5009, abs=5e-4)
    assert prior.sd == pytest.approx(0.0544, abs=5e-4)


def test_pooled_participants_is_not_the_priors_information_content():
    """The rename guards a real confusion: 2564 people, but the weight of ~675 per arm.

    "Effective N" reads as effective sample size, a Bayesian term of art meaning how many
    patients the prior is *worth*. This prior is pooled from 2564 participants but carries far
    less weight than that, so the two numbers must not share a name.
    """

    from opentrial.compute.simulation import prior_equivalent_n_per_arm
    from opentrial.schemas import TrialDesignInput

    prior = build_prior(list(t2d_hba1c_evidence()))
    design = TrialDesignInput(
        indication="Type 2 Diabetes",
        endpoint="HbA1c",
        target_effect=0.5,
        alpha=0.025,
        desired_power=0.8,
        max_n_per_arm=300,
    )

    equivalent = prior_equivalent_n_per_arm(prior, design)
    assert equivalent == pytest.approx(675, abs=1)
    assert equivalent < prior.pooled_participants
