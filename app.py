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
from opentrial.report.charts import operating_characteristics_chart
from opentrial.schemas import TrialDesignInput
from opentrial.workflow import (
    CORE_EVIDENCE_SOURCES,
    EXTRA_EVIDENCE_SOURCES,
    SRC_DEMO,
    run_design,
)


st.set_page_config(page_title="OpenTrial", page_icon="OT", layout="wide")

st.title("OpenTrial")
st.caption("Bayesian trial design engine")

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

    # Extra design settings, collapsed by default to keep the main form simple.
    with st.expander("Advanced options", expanded=False):
        endpoint_type = st.radio(
            "Endpoint type",
            options=["continuous", "binary"],
            help=(
                "Continuous is a two-arm mean-difference design. Binary switches to a "
                "two-proportion (risk-difference) design."
            ),
        )
        baseline_proportion = st.number_input(
            "Baseline (control) event rate",
            min_value=0.01,
            max_value=0.99,
            value=0.30,
            step=0.01,
            disabled=endpoint_type != "binary",
            help="Binary endpoints only: the control-arm event rate the risk difference is measured from.",
        )
        use_bayesian_prior = st.checkbox(
            "PyMC Bayesian meta-analysis prior (slower)",
            value=False,
            help=(
                "Fit a random-effects Bayesian meta-analysis with PyMC instead of the "
                "fast inverse-variance prior. Needs the optional 'bayes' install; falls "
                "back automatically if unavailable."
            ),
        )
        use_gemini_narrative = st.checkbox(
            "Gemini narrative",
            value=False,
            disabled=not any(item.key == "gemini" and item.connected for item in statuses),
        )
        use_prior_sensitivity = st.checkbox(
            "Prior sensitivity analysis",
            value=False,
            help=(
                "Report assurance and predictive success under skeptical, reference, and "
                "enthusiastic priors, per FDA CID guidance, to show how much the result "
                "depends on the prior."
            ),
        )
        use_group_sequential = st.checkbox(
            "Group-sequential design (interim looks, slower)",
            value=False,
            help=(
                "Add prospectively planned interim analyses with Type-I-controlled efficacy "
                "boundaries, and report the expected sample-size saving."
            ),
        )
        gs_boundary = st.selectbox(
            "Interim boundary",
            options=["obrien-fleming", "pocock"],
            disabled=not use_group_sequential,
            help="O'Brien-Fleming is stringent early; Pocock is constant across looks.",
        )
        gs_n_looks = st.slider(
            "Number of looks",
            min_value=2,
            max_value=6,
            value=4,
            disabled=not use_group_sequential,
        )
        st.caption("Audit mode: benchmark an existing study (not added to the prior)")
        audit_nct_id = st.text_input("NCT ID", value="", placeholder="NCT12345678")
        audit_pmid = st.text_input("PMID", value="", placeholder="12345678")

is_binary = endpoint_type == "binary"

st.subheader("Trial Inputs")
left, right = st.columns(2)

with left:
    indication = st.text_input("Indication", value="Type 2 Diabetes")
    endpoint = st.text_input("Endpoint", value="HbA1c change from baseline")
    drug_or_class = st.text_input("Drug or class", value="metformin")
    target_effect = st.number_input(
        "Target risk difference" if is_binary else "Target treatment effect",
        min_value=0.01 if is_binary else 0.05,
        max_value=0.95 if is_binary else 2.0,
        value=0.15 if is_binary else 0.50,
        step=0.01 if is_binary else 0.05,
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
        disabled=is_binary,
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
    core_sources = st.multiselect(
        "Evidence sources",
        options=CORE_EVIDENCE_SOURCES,
        default=[SRC_DEMO],
        help=(
            "Core sources. Defaults to the offline demo; tick live sources to pull real data."
        ),
    )
    advanced_sources = st.multiselect(
        "Advanced evidence sources",
        options=EXTRA_EVIDENCE_SOURCES,
        default=[],
        help=(
            "Extra sources: Semantic Scholar, Open Targets (biology), PharmGKB "
            "(pharmacogenomics), and You.com (web). Some need "
            "an API key; without one they report as unavailable."
        ),
    )

evidence_sources = core_sources + advanced_sources

design = TrialDesignInput(
    indication=indication,
    endpoint=endpoint,
    target_effect=float(target_effect),
    alpha=float(alpha),
    desired_power=float(desired_power),
    max_n_per_arm=int(max_n),
    endpoint_type=endpoint_type,
    endpoint_sd=float(endpoint_sd),
    baseline_proportion=float(baseline_proportion),
)

if st.button("Generate design report", type="primary"):
    with st.spinner("Building design report..."):
        result = run_design(
            design,
            drug_or_class,
            evidence_sources,
            use_bayesian_prior=use_bayesian_prior,
            use_gemini_narrative=use_gemini_narrative,
            audit_nct_id=audit_nct_id,
            audit_pmid=audit_pmid,
            use_mc_operating_characteristics=use_mc_oc,
            use_prior_sensitivity=use_prior_sensitivity,
            use_group_sequential=use_group_sequential,
            gs_n_looks=gs_n_looks,
            gs_boundary=gs_boundary,
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

    if result.audit_records:
        st.subheader("Audit Targets")
        for record in result.audit_records:
            st.write(f"**{record.source}:** [{record.title}]({record.url})")
            st.caption(f"N={record.n}; {record.notes}")

    st.subheader("Operating Characteristics")
    st.caption(
        "Power and Bayesian assurance versus sample size. The dashed line is the target "
        "power; the marker is the recommended N (first size whose power clears the target). "
        "Alpha is the pre-specified type-I reference; beta (1 - power) is in the table below."
    )
    st.altair_chart(
        operating_characteristics_chart(design, result.grid, result.recommendation),
        width="stretch",
    )

    if result.decision is not None:
        st.subheader("Bayesian Decision Criterion")
        dec_cols = st.columns(3)
        dec_cols[0].metric(
            "Posterior Pr(effect > 0)",
            f"{result.decision.posterior_success_probability:.3f}",
        )
        dec_cols[1].metric(
            "Predictive prob. of success",
            f"{result.decision.predictive_probability_of_success:.3f}",
        )
        dec_cols[2].metric(
            f"Meets threshold ({result.decision.decision_threshold:.3f})",
            "Yes" if result.decision.meets_decision_threshold else "No",
        )

    if result.sensitivity:
        st.subheader("Prior Sensitivity Analysis")
        st.caption(
            "Stability across rows means the design is robust to the prior "
            "(FDA Complex Innovative Trial Designs guidance)."
        )
        st.dataframe(
            [
                {
                    "Prior": s.label,
                    "Mean": round(s.prior.mean, 3),
                    "SD": round(s.prior.sd, 3),
                    "Assurance": round(s.assurance, 3),
                    "Predictive success": round(s.predictive_probability_of_success, 3),
                    "Posterior Pr(>0)": round(s.posterior_success_probability, 3),
                }
                for s in result.sensitivity
            ],
        )

    if result.group_sequential is not None:
        gs = result.group_sequential
        st.subheader("Group-Sequential Design")
        gs_cols = st.columns(3)
        gs_cols[0].metric("Type I error (simulated)", f"{gs.type_i_error:.3f}")
        gs_cols[1].metric("Power", f"{gs.power:.3f}")
        gs_cols[2].metric(
            "Expected N/arm vs fixed",
            f"{gs.expected_n_per_arm_alt:.0f} / {gs.fixed_n_per_arm}",
            f"-{gs.expected_reduction_vs_fixed * 100:.0f}%",
        )
        st.dataframe(
            [
                {
                    "Look": lk.look,
                    "Information fraction": round(lk.information_fraction, 2),
                    "N per arm": lk.n_per_arm,
                    "Efficacy z": round(lk.efficacy_z, 3),
                    "Cumulative stop (alt)": round(lk.cumulative_stop_prob_alt, 3),
                }
                for lk in gs.looks
            ],
        )

    st.subheader("Report")
    st.markdown(result.report)
    download_cols = st.columns(3)
    download_cols[0].download_button(
        "Download Markdown",
        data=result.report,
        file_name="opentrial_design_report.md",
        mime="text/markdown",
    )
    download_cols[1].download_button(
        "Download JSON",
        data=result.to_json(),
        file_name="opentrial_design_report.json",
        mime="application/json",
    )
    try:
        pdf_bytes = result.to_pdf()
    except Exception as exc:  # noqa: BLE001 - PDF is optional; keep the page alive
        download_cols[2].caption(f"PDF export unavailable: {exc}")
    else:
        download_cols[2].download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="opentrial_design_report.pdf",
            mime="application/pdf",
        )
else:
    st.info(
        "Pick one or more evidence sources above (the offline demo is selected by "
        "default), then click Generate. Add live sources to pull real data."
    )
