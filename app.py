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

from opentrial.integrations.registry import integration_statuses
from opentrial.schemas import TrialDesignInput
from opentrial.workflow import EVIDENCE_SOURCES, SRC_DEMO, run_design


st.set_page_config(page_title="OpenTrial", page_icon="OT", layout="wide")

st.title("OpenTrial")
st.caption("Bayesian trial design engine - proof of concept")

with st.sidebar:
    st.header("Integrations")
    statuses = integration_statuses()
    for item in statuses:
        state = item.status or ("connected" if item.connected else "mock")
        st.write(f"**{item.name}:** {state}")

    use_mc_oc = st.checkbox(
        "Monte Carlo operating characteristics (slower)",
        value=False,
        help=(
            "Estimate power, type-I error, and assurance by simulation instead of the "
            "closed-form approximation. The empirical type-I error is a calibration "
            "check against the nominal alpha."
        ),
    )
    use_gemini_narrative = st.checkbox(
        "Gemini narrative",
        value=False,
        disabled=not any(item.key == "gemini" and item.connected for item in statuses),
        help="Optional: add a plain-language narrative. The numbers stay deterministic.",
    )

st.subheader("Trial Inputs")
left, right = st.columns(2)

with left:
    indication = st.text_input("Indication", value="Type 2 Diabetes")
    endpoint = st.text_input("Endpoint", value="HbA1c change from baseline")
    drug_or_class = st.text_input("Drug or class", value="metformin")
    target_effect = st.number_input(
        "Target treatment effect",
        min_value=0.05,
        max_value=2.0,
        value=0.50,
        step=0.05,
        help=(
            "The treatment-vs-control difference you want to detect, in the endpoint's "
            "own units (the demo uses absolute HbA1c percentage points)."
        ),
    )
    endpoint_sd = st.number_input(
        "Endpoint SD (population)",
        min_value=0.1,
        max_value=20.0,
        value=1.0,
        step=0.1,
        help=(
            "Population standard deviation of the endpoint, in the same units as the "
            "target effect; the power maths standardizes by it (HbA1c ~1.0-1.2; "
            "1.0 = already standardized)."
        ),
    )

with right:
    alpha = st.number_input(
        "One-sided alpha", min_value=0.001, max_value=0.20, value=0.025, step=0.005, format="%.3f"
    )
    desired_power = st.number_input("Desired power", min_value=0.50, max_value=0.99, value=0.80)
    max_n = st.number_input("Max N per arm", min_value=40, max_value=1000, value=300, step=20)
    evidence_sources = st.multiselect(
        "Evidence sources",
        options=EVIDENCE_SOURCES,
        default=[SRC_DEMO],
        help=(
            "Pick any combination. Defaults to the offline demo; tick live sources to "
            "pull real data. Each name matches the sidebar Integrations panel."
        ),
    )

design = TrialDesignInput(
    indication=indication,
    endpoint=endpoint,
    target_effect=float(target_effect),
    alpha=float(alpha),
    desired_power=float(desired_power),
    max_n_per_arm=int(max_n),
    endpoint_sd=float(endpoint_sd),
)

if st.button("Generate design report", type="primary"):
    with st.spinner("Building design report..."):
        result = run_design(
            design,
            drug_or_class,
            evidence_sources,
            use_gemini_narrative=use_gemini_narrative,
            use_mc_operating_characteristics=use_mc_oc,
        )

    for message in result.warnings:
        st.warning(message)
    if not result.evidence:
        st.info(
            "No evidence gathered (nothing selected, or live sources returned nothing). "
            "The prior falls back to weakly-informative."
        )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Evidence records", len(result.evidence))
    metric_cols[1].metric("Prior mean", f"{result.prior.mean:.2f}")
    metric_cols[2].metric("Prior SD", f"{result.prior.sd:.2f}")
    metric_cols[3].metric(
        "Recommended N/arm",
        str(result.recommendation.n_per_arm) if result.recommendation else "Not reached",
    )

    if result.outcomes:
        st.subheader("Sources")
        badge = {"ok": "OK", "empty": "0 records", "failed": "failed"}
        source_cols = st.columns(len(result.outcomes))
        for col, outcome in zip(source_cols, result.outcomes):
            detail = (
                f"{outcome.n_records} records"
                if outcome.status in {"ok", "empty"}
                else badge[outcome.status]
            )
            col.metric(outcome.name, badge[outcome.status], detail)

    st.subheader("Operating Characteristics")
    st.line_chart(
        [
            {
                "n_per_arm": p.n_per_arm,
                "Target-effect power": p.power,
                "Beta (type-II error)": p.beta,
                "Alpha / type-I error": p.type_i_error,
                "Bayesian assurance": p.assurance,
            }
            for p in result.grid
        ],
        x="n_per_arm",
        y=[
            "Target-effect power",
            "Beta (type-II error)",
            "Alpha / type-I error",
            "Bayesian assurance",
        ],
    )

    st.subheader("Report")
    st.markdown(result.report)
    st.download_button(
        "Download Markdown",
        data=result.report,
        file_name="opentrial_design_report.md",
        mime="text/markdown",
    )
    st.download_button(
        "Download JSON",
        data=result.to_json(),
        file_name="opentrial_design_report.json",
        mime="application/json",
    )
else:
    st.info(
        "Pick one or more evidence sources above (the offline demo is selected by "
        "default), then click Generate. Add live sources to pull real data."
    )
