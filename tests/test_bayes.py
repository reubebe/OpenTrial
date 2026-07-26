import os

import pytest

from opentrial.compute.bayes import build_prior_bayesian
from opentrial.compute.priors import build_prior
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.schemas import EvidenceRecord


def _record(effect: float, se: float, n: int = 100) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_kind="effect_estimate",
        source="Test",
        title="t",
        effect=effect,
        standard_error=se,
        n=n,
        endpoint="HbA1c",
        indication="Type 2 Diabetes",
        year=2022,
        url="https://example.test",
    )


def test_bayesian_prior_defers_to_closed_form_with_fewer_than_two_studies():
    # No sampler is run here, so this stays fast and never needs PyMC.
    single = [_record(0.5, 0.1)]
    bayesian = build_prior_bayesian(single)
    closed = build_prior(single)
    assert bayesian.mean == closed.mean
    assert bayesian.sd == closed.sd
    assert bayesian.records_used == closed.records_used


def test_bayesian_prior_ignores_context_only_records():
    # Records with SE=0 are not usable; one usable record => defers to closed form.
    mixed = [_record(0.5, 0.1), _record(0.4, 0.0)]
    prior = build_prior_bayesian(mixed)
    assert prior.records_used == 1


@pytest.mark.skipif(
    not os.getenv("OPENTRIAL_RUN_PYMC"),
    reason="set OPENTRIAL_RUN_PYMC=1 to run the slow PyMC sampling test",
)
def test_bayesian_prior_matches_closed_form_mean_on_demo():
    pytest.importorskip("pymc")
    evidence = t2d_hba1c_evidence()
    closed = build_prior(evidence)
    bayesian = build_prior_bayesian(evidence, draws=500, tune=500, chains=2, seed=42)

    assert bayesian.records_used == 4
    assert "PyMC" in bayesian.method
    # The population-mean estimate should track the closed-form pooled mean closely.
    assert abs(bayesian.mean - closed.mean) < 0.1
    # The random-effects predictive SD is at least as wide as the closed-form SD.
    assert bayesian.sd >= 0.05
