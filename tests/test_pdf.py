import pytest

from opentrial.compute.decision import summarize_decision
from opentrial.compute.priors import build_prior
from opentrial.compute.sensitivity import prior_sensitivity
from opentrial.compute.simulation import recommend_sample_size, simulate_design_grid
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.report.pdf import PdfExportError, render_pdf_report
from opentrial.schemas import TrialDesignInput

# The PDF engine is an optional extra; skip cleanly when it is not installed.
pytest.importorskip("fpdf")


def _design():
    return TrialDesignInput(
        indication="Type 2 Diabetes",
        endpoint="HbA1c",
        target_effect=0.5,
        alpha=0.025,
        desired_power=0.8,
        max_n_per_arm=300,
    )


def test_render_pdf_returns_valid_pdf_bytes():
    design = _design()
    evidence = t2d_hba1c_evidence()
    prior = build_prior(evidence)
    grid = simulate_design_grid(design, prior)
    recommendation = recommend_sample_size(grid, design.desired_power)
    decision = summarize_decision(design, prior, recommendation.n_per_arm)
    sensitivity = prior_sensitivity(design, prior, recommendation.n_per_arm)

    pdf = render_pdf_report(
        design,
        prior,
        grid,
        recommendation,
        decision=decision,
        sensitivity=sensitivity,
        evidence=evidence,
    )

    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000


def test_render_pdf_without_optional_sections_still_works():
    design = _design()
    prior = build_prior(t2d_hba1c_evidence())
    grid = simulate_design_grid(design, prior)
    recommendation = recommend_sample_size(grid, design.desired_power)

    pdf = render_pdf_report(design, prior, grid, recommendation)

    assert pdf.startswith(b"%PDF-")


def test_pdf_export_error_is_available_for_fallbacks():
    assert issubclass(PdfExportError, RuntimeError)
