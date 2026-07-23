"""PDF export of a design report.

The default deliverables are Markdown (for people) and JSON (for a reproducible record).
A PDF is what actually gets attached to an email or a regulatory meeting package, so this
module renders the same structured report to a self-contained PDF.

It uses ``fpdf2`` -- a small, pure-Python engine with no system dependencies -- installed as
the optional ``[pdf]`` extra. When it is absent the caller gets a typed
:class:`PdfExportError` and can fall back to Markdown/JSON, the same graceful-degradation
pattern the optional PyMC prior uses. No network, no shelling out to LaTeX.
"""

from __future__ import annotations

from opentrial.schemas import (
    DecisionSummary,
    DesignPoint,
    EvidenceRecord,
    GroupSequentialResult,
    PriorScenario,
    PriorSummary,
    TrialDesignInput,
)

_NAVY = (31, 75, 153)
_INK = (33, 37, 41)
_MUTED = (110, 118, 129)


class PdfExportError(RuntimeError):
    """Raised when a PDF cannot be produced (typically the optional extra is missing)."""


def render_pdf_report(
    design: TrialDesignInput,
    prior: PriorSummary,
    grid: list[DesignPoint],
    recommendation: DesignPoint | None,
    *,
    decision: DecisionSummary | None = None,
    sensitivity: list[PriorScenario] | None = None,
    group_sequential: GroupSequentialResult | None = None,
    evidence: list[EvidenceRecord] | None = None,
) -> bytes:
    """Render the design report to PDF bytes."""

    try:
        from fpdf import FPDF
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised when extra is absent
        raise PdfExportError(
            'PDF export needs the optional engine. Install it with pip install -e ".[pdf]".'
        ) from exc

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    _title(pdf, "OpenTrial Design Report")

    effect_label = "risk difference" if design.endpoint_type == "binary" else "mean difference"
    _section(pdf, "Design question")
    _kv(pdf, "Indication", design.indication)
    _kv(pdf, "Endpoint", f"{design.endpoint} ({design.endpoint_type})")
    _kv(pdf, f"Target effect ({effect_label})", f"{design.target_effect:.2f}")
    if design.endpoint_type == "binary":
        _kv(pdf, "Baseline event rate", f"{design.baseline_proportion:.2f}")
    else:
        _kv(pdf, "Endpoint SD", f"{design.endpoint_sd:.2f}")
    _kv(pdf, "One-sided alpha", f"{design.alpha:.3f}")
    _kv(pdf, "Desired power", f"{design.desired_power:.2f}")
    _kv(pdf, "Decision threshold", f"Pr(effect > 0) >= {design.decision_threshold:.3f}")

    _section(pdf, "Evidence-derived prior")
    _kv(pdf, "Method", prior.method)
    _kv(pdf, "Prior mean", f"{prior.mean:.3f}")
    _kv(pdf, "Prior SD", f"{prior.sd:.3f}")
    _kv(pdf, "Records used", str(prior.records_used))

    rec_text = (
        f"{recommendation.n_per_arm} per arm ({recommendation.n_per_arm * 2} total)"
        if recommendation
        else f"Not reached by {design.max_n_per_arm} per arm"
    )
    _section(pdf, "Recommendation")
    _kv(pdf, "Recommended sample size", rec_text)

    if decision is not None:
        _section(pdf, "Bayesian decision criterion")
        _kv(pdf, "At N per arm", str(decision.n_per_arm))
        _kv(pdf, "Posterior Pr(effect > 0)", f"{decision.posterior_success_probability:.3f}")
        _kv(
            pdf,
            "Predictive prob. of success",
            f"{decision.predictive_probability_of_success:.3f}",
        )
        _kv(pdf, "Meets threshold", "yes" if decision.meets_decision_threshold else "no")

    _section(pdf, "Operating characteristics")
    _table(
        pdf,
        ["N/arm", "Power", "Beta", "Alpha/T-I", "Assurance"],
        [
            [
                str(p.n_per_arm),
                f"{p.power:.3f}",
                f"{p.beta:.3f}",
                f"{p.type_i_error:.3f}",
                f"{p.assurance:.3f}",
            ]
            for p in grid
        ],
        [26, 32, 32, 36, 36],
    )

    if sensitivity:
        _section(pdf, "Prior sensitivity analysis")
        _table(
            pdf,
            ["Prior", "Mean", "SD", "Assurance", "PPoS", "Posterior Pr(>0)"],
            [
                [
                    s.label,
                    f"{s.prior.mean:.2f}",
                    f"{s.prior.sd:.2f}",
                    f"{s.assurance:.3f}",
                    f"{s.predictive_probability_of_success:.3f}",
                    f"{s.posterior_success_probability:.3f}",
                ]
                for s in sensitivity
            ],
            [34, 24, 24, 30, 28, 38],
        )

    if group_sequential is not None:
        gs = group_sequential
        _section(pdf, "Group-sequential design")
        _kv(pdf, "Boundary", f"{gs.boundary}, {gs.n_looks} looks")
        _kv(pdf, "Type I error / power", f"{gs.type_i_error:.3f} / {gs.power:.3f}")
        _kv(
            pdf,
            "Expected N/arm (alt) vs fixed",
            f"{gs.expected_n_per_arm_alt:.0f} vs {gs.fixed_n_per_arm} "
            f"({gs.expected_reduction_vs_fixed * 100:.0f}% less)",
        )
        _table(
            pdf,
            ["Look", "Info frac.", "N/arm", "Efficacy z", "Stop (alt)"],
            [
                [
                    str(lk.look),
                    f"{lk.information_fraction:.2f}",
                    str(lk.n_per_arm),
                    f"{lk.efficacy_z:.3f}",
                    f"{lk.cumulative_stop_prob_alt:.3f}",
                ]
                for lk in gs.looks
            ],
            [24, 34, 30, 34, 34],
        )

    if evidence:
        _section(pdf, "Evidence provenance")
        _table(
            pdf,
            ["Source", "Year", "Effect", "SE", "N"],
            [
                [
                    record.source,
                    str(record.year),
                    f"{record.effect:.3f}",
                    f"{record.standard_error:.3f}",
                    str(record.n),
                ]
                for record in evidence
            ],
            [56, 24, 30, 30, 24],
        )

    output = pdf.output()
    return bytes(output)


def _title(pdf, text: str) -> None:
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 12, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*_NAVY)
    pdf.set_line_width(0.5)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(4)


def _section(pdf, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*_NAVY)
    pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")


def _kv(pdf, key: str, value: str) -> None:
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_INK)
    pdf.cell(60, 6, f"{key}:", new_x="RIGHT", new_y="TOP")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*_INK)
    pdf.multi_cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")


def _table(pdf, headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(255, 255, 255)
    pdf.set_fill_color(*_NAVY)
    for header, width in zip(headers, widths):
        pdf.cell(width, 7, header, border=0, align="C", fill=True)
    pdf.ln(7)
    pdf.set_text_color(*_INK)
    for index, row in enumerate(rows):
        pdf.set_font("Helvetica", "", 9)
        if index % 2 == 0:
            pdf.set_fill_color(238, 242, 249)
            fill = True
        else:
            pdf.set_fill_color(255, 255, 255)
            fill = False
        for value, width in zip(row, widths):
            pdf.cell(width, 6, value, border=0, align="C", fill=fill)
        pdf.ln(6)
