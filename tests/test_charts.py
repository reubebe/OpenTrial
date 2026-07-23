import pytest

from opentrial.compute.priors import build_prior
from opentrial.compute.simulation import recommend_sample_size, simulate_design_grid
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.schemas import TrialDesignInput

# Altair ships with Streamlit; skip cleanly if the chart engine is not installed.
pytest.importorskip("altair")

from opentrial.report.charts import operating_characteristics_chart  # noqa: E402


def _design():
    return TrialDesignInput(
        indication="Type 2 Diabetes",
        endpoint="HbA1c",
        target_effect=0.5,
        alpha=0.025,
        desired_power=0.8,
        max_n_per_arm=300,
    )


def _grid(design):
    prior = build_prior(t2d_hba1c_evidence())
    return simulate_design_grid(design, prior), prior


def test_chart_builds_a_valid_vega_lite_spec():
    design = _design()
    grid, _ = _grid(design)
    recommendation = recommend_sample_size(grid, design.desired_power)

    chart = operating_characteristics_chart(design, grid, recommendation)
    spec = chart.to_dict()  # raises if the spec is invalid

    # Layered chart: curves + the two reference lines (+ labels) + recommendation marks.
    assert "layer" in spec
    assert len(spec["layer"]) >= 5


def test_probability_axis_is_locked_to_zero_one():
    design = _design()
    grid, _ = _grid(design)

    spec = operating_characteristics_chart(design, grid, None).to_dict()

    y_scales = _find_scale_domains(spec, channel="y")
    assert [0, 1] in y_scales


def test_chart_without_a_recommendation_still_builds():
    design = _design()
    grid, _ = _grid(design)

    chart = operating_characteristics_chart(design, grid, recommendation=None)

    assert chart.to_dict()["layer"]  # no recommendation marker, but still a valid chart


def _find_scale_domains(spec, channel):
    domains = []

    def walk(node):
        if isinstance(node, dict):
            enc = node.get("encoding", {})
            ch = enc.get(channel, {})
            scale = ch.get("scale", {})
            if "domain" in scale:
                domains.append(scale["domain"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return domains
