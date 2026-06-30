import json

from opentrial import workflow
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


def test_run_design_offline_demo_produces_full_result():
    result = workflow.run_design(_design(), "metformin", [workflow.SRC_DEMO])

    assert result.evidence
    assert result.prior.records_used == len(result.evidence)
    assert result.recommendation is not None
    assert "# OpenTrial Design Report" in result.report
    assert "Evidence Provenance" in result.report
    assert result.warnings == []
    assert [o.name for o in result.outcomes] == [workflow.SRC_DEMO]
    assert result.outcomes[0].status == "ok"
    assert result.outcomes[0].n_records == len(result.evidence)
    assert "Evidence Source Status" in result.report
    assert workflow.SRC_DEMO in result.report


def test_run_design_with_no_sources_uses_fallback_prior():
    result = workflow.run_design(_design(), "metformin", [])

    assert result.evidence == []
    assert result.prior.records_used == 0
    assert "fallback" in result.prior.method
    assert result.outcomes == []
    # The report still renders from the weak fallback prior.
    assert "# OpenTrial Design Report" in result.report


def test_gather_evidence_records_a_failed_source_without_crashing(monkeypatch):
    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(workflow, "get_trials_ct_gov", lambda *a, **k: boom())

    evidence, outcomes = workflow.gather_evidence(
        _design(), "metformin", [workflow.SRC_DEMO, workflow.SRC_CTGOV]
    )

    by_name = {o.name: o for o in outcomes}
    assert by_name[workflow.SRC_DEMO].status == "ok"
    assert by_name[workflow.SRC_CTGOV].status == "failed"
    assert "network down" in by_name[workflow.SRC_CTGOV].message
    # The demo evidence still came through despite the failed live source.
    assert evidence


def test_run_design_surfaces_failed_source_as_warning(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "get_trials_ct_gov",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("429 rate limited")),
    )

    result = workflow.run_design(
        _design(), "metformin", [workflow.SRC_DEMO, workflow.SRC_CTGOV]
    )

    assert any("ClinicalTrials.gov" in w and "429" in w for w in result.warnings)


def test_design_result_exports_reproducible_json_payload():
    result = workflow.run_design(_design(), "metformin", [workflow.SRC_DEMO])

    payload = json.loads(result.to_json())

    assert payload["design"]["indication"] == "Type 2 Diabetes"
    assert payload["prior"]["records_used"] == 4
    assert payload["recommendation"]["n_per_arm"] == result.recommendation.n_per_arm
    assert payload["source_outcomes"][0]["name"] == workflow.SRC_DEMO
    assert payload["source_outcomes"][0]["status"] == "ok"
    assert payload["evidence"][0]["evidence_kind"] == "effect_estimate"
    assert payload["report_markdown"].startswith("# OpenTrial Design Report")


def test_run_design_with_mc_operating_characteristics():
    result = workflow.run_design(
        _design(),
        "metformin",
        [workflow.SRC_DEMO],
        use_mc_operating_characteristics=True,
    )
    assert result.grid
    # Empirical type-I error varies per point (it is simulated, not the constant alpha).
    assert any(p.type_i_error != _design().alpha for p in result.grid)
    assert result.recommendation is not None
