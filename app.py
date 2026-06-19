from __future__ import annotations

import sys
from pathlib import Path

try:
    import streamlit as st
except ModuleNotFoundError as exc:  # pragma: no cover - friendly CLI failure
    raise SystemExit(
        "Streamlit is not installed. Run `python3 -m pip install -e .` first."
    ) from exc

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from opentrial.compute.priors import build_prior
from opentrial.compute.simulation import recommend_sample_size, simulate_design_grid
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.integrations.registry import integration_statuses
from opentrial.report.markdown import render_markdown_report
from opentrial.schemas import TrialDesignInput


st.set_page_config(page_title="OpenTrial", page_icon="OT", layout="wide")

st.title("OpenTrial")
st.caption("Bayesian trial design engine - first vertical slice")

with st.sidebar:
    st.header("Integrations")
    for item in integration_statuses():
        state = "connected" if item.connected else "mock"
        st.write(f"**{item.name}:** {state}")

st.subheader("Trial Inputs")
left, right = st.columns(2)

with left:
    indication = st.text_input("Indication", value="Type 2 Diabetes")
    endpoint = st.text_input("Endpoint", value="HbA1c change from baseline")
    target_effect = st.number_input(
        "Target treatment effect",
        min_value=0.05,
        max_value=2.0,
        value=0.50,
        step=0.05,
        help="For the demo, this is an absolute HbA1c percentage-point difference.",
    )

with right:
    alpha = st.number_input("One-sided alpha", min_value=0.001, max_value=0.20, value=0.025)
    desired_power = st.number_input("Desired power", min_value=0.50, max_value=0.99, value=0.80)
    max_n = st.number_input("Max N per arm", min_value=40, max_value=1000, value=300, step=20)

design = TrialDesignInput(
    indication=indication,
    endpoint=endpoint,
    target_effect=float(target_effect),
    alpha=float(alpha),
    desired_power=float(desired_power),
    max_n_per_arm=int(max_n),
)

if st.button("Generate design report", type="primary"):
    evidence = t2d_hba1c_evidence()
    prior = build_prior(evidence)
    grid = simulate_design_grid(design, prior)
    recommendation = recommend_sample_size(grid, design.desired_power)
    report = render_markdown_report(design, evidence, prior, grid, recommendation)

    metric_cols = st.columns(4)
    metric_cols[0].metric("Evidence records", len(evidence))
    metric_cols[1].metric("Prior mean", f"{prior.mean:.2f}")
    metric_cols[2].metric("Prior SD", f"{prior.sd:.2f}")
    metric_cols[3].metric(
        "Recommended N/arm",
        str(recommendation.n_per_arm) if recommendation else "Not reached",
    )

    st.subheader("Operating Characteristics")
    st.line_chart(
        [{"n_per_arm": p.n_per_arm, "power": p.power} for p in grid],
        x="n_per_arm",
        y="power",
    )

    st.subheader("Report")
    st.markdown(report)
    st.download_button(
        "Download Markdown",
        data=report,
        file_name="opentrial_design_report.md",
        mime="text/markdown",
    )
else:
    st.info("Start with the seeded T2D/HbA1c demo. Live API wrappers come next.")
