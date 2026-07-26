from opentrial.compute.priors import build_prior
from opentrial.compute.simulation import recommend_sample_size, simulate_design_grid
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.report.markdown import render_markdown_report
from opentrial.schemas import TrialDesignInput


def test_demo_vertical_slice_produces_report():
    design = TrialDesignInput(
        indication="Type 2 Diabetes",
        endpoint="HbA1c change from baseline",
        target_effect=0.50,
        alpha=0.025,
        desired_power=0.80,
        max_n_per_arm=300,
    )

    evidence = t2d_hba1c_evidence()
    prior = build_prior(evidence)
    grid = simulate_design_grid(design, prior)
    recommendation = recommend_sample_size(grid, design.desired_power)
    report = render_markdown_report(design, evidence, prior, grid, recommendation)

    assert evidence
    assert prior.records_used == len(evidence)
    assert recommendation is not None
    assert "# OpenTrial Design Report" in report
    assert "Endpoint type: continuous" in report
    assert "Endpoint SD: 1.00" in report
    assert "Evidence Provenance" in report


def test_binary_markdown_report_includes_endpoint_assumptions():
    from opentrial.schemas import PriorSummary

    design = TrialDesignInput(
        indication="X",
        endpoint="Response rate",
        target_effect=0.15,
        alpha=0.025,
        desired_power=0.80,
        max_n_per_arm=300,
        endpoint_type="binary",
        baseline_proportion=0.30,
    )
    prior = PriorSummary(mean=0.0, sd=1.0, pooled_participants=0, records_used=0, method="weak")
    grid = simulate_design_grid(design, prior)
    recommendation = recommend_sample_size(grid, design.desired_power)

    report = render_markdown_report(design, [], prior, grid, recommendation)

    assert "Endpoint type: binary" in report
    assert "Target effect (risk difference): 0.15" in report
    assert "Baseline event rate: 0.30" in report
    assert "Implied treatment event rate: 0.45" in report


def test_markdown_report_can_include_ai_narrative():
    design = TrialDesignInput(
        indication="Type 2 Diabetes",
        endpoint="HbA1c change from baseline",
        target_effect=0.50,
        alpha=0.025,
        desired_power=0.80,
        max_n_per_arm=300,
    )

    evidence = t2d_hba1c_evidence()
    prior = build_prior(evidence)
    grid = simulate_design_grid(design, prior)
    recommendation = recommend_sample_size(grid, design.desired_power)
    report = render_markdown_report(
        design,
        evidence,
        prior,
        grid,
        recommendation,
        narrative="## AI Narrative Synthesis\n\nShort narrative.",
    )

    assert "AI Narrative Synthesis" in report
