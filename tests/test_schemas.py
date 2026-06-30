import pytest
from pydantic import ValidationError

from opentrial.schemas import EvidenceRecord, SourceOutcome, TrialDesignInput


def test_trial_design_input_validates_probability_bounds():
    with pytest.raises(ValidationError):
        TrialDesignInput(
            indication="Type 2 Diabetes",
            endpoint="HbA1c",
            target_effect=0.5,
            alpha=1.2,
            desired_power=0.8,
            max_n_per_arm=300,
        )


def test_evidence_record_validates_standard_error_and_n():
    with pytest.raises(ValidationError):
        EvidenceRecord(
            source="PubMed",
            title="Bad record",
            effect=0.5,
            standard_error=-0.1,
            n=-5,
            endpoint="HbA1c",
            indication="Type 2 Diabetes",
            year=2024,
            url="https://example.test",
        )


def test_models_are_immutable():
    record = EvidenceRecord(
        source="PubMed",
        title="Good record",
        effect=0.5,
        standard_error=0.1,
        n=100,
        endpoint="HbA1c",
        indication="Type 2 Diabetes",
        year=2024,
        url="https://example.test",
    )

    with pytest.raises(ValidationError):
        record.n = 200


def test_evidence_kind_rejects_unknown_values():
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_kind="mystery",
            source="PubMed",
            title="Bad kind",
            effect=0.5,
            standard_error=0.1,
            n=100,
            endpoint="HbA1c",
            indication="Type 2 Diabetes",
            year=2024,
            url="https://example.test",
        )


def test_source_outcome_rejects_unknown_status():
    with pytest.raises(ValidationError):
        SourceOutcome(name="PubMed", status="slow", n_records=0)
