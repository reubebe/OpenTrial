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
    assert "Evidence Provenance" in report
