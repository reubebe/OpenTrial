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


st.set_page_config(
    page_title="OpenTrial",
    page_icon="OT",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Futuristic dark polish: deep-space ground, neon accents, glassmorphism cards.
# Everything here is presentational; no app behaviour depends on it.
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Inter:wght@400;500;600&display=swap');

      /* Ambient gradient wash over the deep-space background. */
      .stApp {
        background:
          radial-gradient(1100px 600px at 12% -8%, rgba(34,211,238,.10), transparent 60%),
          radial-gradient(900px 500px at 105% 0%, rgba(139,92,246,.12), transparent 55%),
          #080B14;
      }
      .block-container { padding-top: 2rem; max-width: 1200px; }

      html, body, [class*="css"] { font-family: 'Inter', system-ui, sans-serif; }

      /* Neon header slab with a glass sheen and glow. */
      .ot-header {
        position: relative;
        background: linear-gradient(120deg, rgba(15,22,38,.85) 0%, rgba(23,32,54,.85) 100%);
        border: 1px solid rgba(34,211,238,.35);
        border-radius: 16px;
        padding: 1.3rem 1.6rem;
        margin-bottom: 1.5rem;
        backdrop-filter: blur(8px);
        box-shadow: 0 0 0 1px rgba(34,211,238,.05), 0 8px 40px rgba(34,211,238,.12);
        overflow: hidden;
      }
      .ot-header::before {
        content: ""; position: absolute; inset: 0;
        background: linear-gradient(90deg, transparent, rgba(34,211,238,.06), transparent);
      }
      .ot-header h1 {
        margin: 0; font-family: 'Orbitron', sans-serif; font-weight: 800;
        font-size: 2rem; letter-spacing: 2px;
        background: linear-gradient(90deg, #22D3EE 0%, #8B5CF6 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        text-shadow: 0 0 24px rgba(34,211,238,.25);
      }
      .ot-header p {
        margin: .35rem 0 0 0; font-size: .95rem; color: #9FB0D0;
        letter-spacing: .3px;
      }

      /* Glass cards: the bordered input container and any generic bordered block. */
      div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(15,22,38,.55) !important;
        border: 1px solid rgba(120,150,220,.18) !important;
        border-radius: 14px !important;
        backdrop-filter: blur(6px);
      }

      /* Metric tiles glow faintly and lift on the dark ground. */
      div[data-testid="stMetric"] {
        background: linear-gradient(160deg, rgba(20,28,48,.9), rgba(12,18,32,.9));
        border: 1px solid rgba(34,211,238,.22);
        border-radius: 12px;
        padding: .85rem 1rem;
        box-shadow: 0 4px 24px rgba(0,0,0,.35), inset 0 0 20px rgba(34,211,238,.04);
      }
      div[data-testid="stMetricValue"] {
        color: #E6ECFB; text-shadow: 0 0 16px rgba(34,211,238,.35);
      }
      div[data-testid="stMetricLabel"] p {
        font-weight: 600; color: #7FE9F7; letter-spacing: .4px;
        text-transform: uppercase; font-size: .72rem;
      }

      /* Section headers: monospace-ish, cyan, with an underline accent. */
      h2, h3 {
        color: #CFE8FF; letter-spacing: .6px;
        border-bottom: 1px solid rgba(34,211,238,.18);
        padding-bottom: .3rem;
      }

      /* Primary button: neon gradient with glow, brighter on hover. */
      .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #22D3EE 0%, #6D5AF0 100%);
        border: none; color: #05121A; font-weight: 700; letter-spacing: .4px;
        box-shadow: 0 0 24px rgba(34,211,238,.35);
        transition: box-shadow .2s ease, transform .05s ease;
      }
      .stButton > button[kind="primary"]:hover {
        box-shadow: 0 0 34px rgba(34,211,238,.6); transform: translateY(-1px);
      }

      /* Sidebar: darker glass panel with a cyan hairline edge. */
      section[data-testid="stSidebar"] {
        background: rgba(9,13,22,.92);
        border-right: 1px solid rgba(34,211,238,.15);
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="ot-header">
      <h1>OPENTRIAL</h1>
      <p>Bayesian trial design engine &middot; evidence-based priors &middot; power, assurance &amp; decision criteria</p>
    </div>
    """,
    unsafe_allow_html=True,
)

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
        tau_method_label = st.radio(
            "Heterogeneity (tau squared) estimator",
            options=["DerSimonian-Laird", "REML"],
            help=(
                "How the between-study variance tau^2 is estimated for the random-effects "
                "prior. DerSimonian-Laird is a one-shot moment estimator (fast, but noisy and "
                "quick to truncate to zero when there are only a few studies). REML solves the "
                "likelihood by iteration and is steadier at small numbers of studies."
            ),
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
tau_method = "reml" if tau_method_label == "REML" else "dl"

st.subheader("Trial Inputs")
inputs_card = st.container(border=True)
left, right = inputs_card.columns(2, gap="large")

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
    dropout_rate = st.number_input(
        "Planned dropout rate",
        min_value=0.0,
        max_value=0.90,
        value=0.0,
        step=0.05,
        format="%.2f",
        help=(
            "Expected proportion of enrolled participants per arm lost before analysis. "
            "Operating characteristics are computed on the analyzable count n*(1 - dropout), "
            "so the recommended N is what to ENROLL to keep power after attrition. 0 is the "
            "complete-follow-up idealization; trials typically plan 0.10-0.20."
        ),
    )
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
    dropout_rate=float(dropout_rate),
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
            tau_method=tau_method,
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
    rec_help = None
    if result.recommendation and design.dropout_rate > 0:
        analyzable = round(result.recommendation.n_per_arm * (1 - design.dropout_rate))
        rec_help = f"to enroll; ~{analyzable} analyzable after {design.dropout_rate:.0%} dropout"
    metric_cols[3].metric(
        "Recommended N/arm",
        str(result.recommendation.n_per_arm) if result.recommendation else "Not reached",
        help=rec_help,
    )

    if result.prior.records_merged:
        st.caption(
            f"De-duplication: {result.prior.records_merged} duplicate trial "
            f"report(s) merged before pooling, so no trial is counted twice."
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
