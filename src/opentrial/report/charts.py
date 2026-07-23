"""The operating-characteristics chart.

The report's headline figure answers one question a reader actually has in front of the
form: *how big must the trial be?* A generic multi-line plot buries that. This module builds
a purpose-made decision chart with Altair (which ships with Streamlit, so no new dependency),
laid out to be read the way the handbook's power-curve figure is:

* two curves that matter -- **power** (frequentist) and **Bayesian assurance** (averaged over
  the prior) -- named by a top legend (the two curves nearly coincide when the prior is tight,
  so direct end-labels would collide; the report's data table below is the accessibility relief);
* a dashed **target-power** reference line, so the reader can see where the curve crosses it;
* a faint **alpha / type-I** reference at the pre-specified error rate;
* a marker at the **recommended N**, the first sample size whose power clears the target.

Beta is deliberately omitted: it is exactly ``1 - power`` (the power curve upside down), so
plotting it doubles the ink for no new information. It remains in the report table.

Colors are the validated categorical slots 1 (blue) and 2 (aqua); chrome (axes, labels) is
left to the Streamlit theme so the chart reads in both light and dark mode. Altair is imported
lazily so the core package stays importable without it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentrial.schemas import DesignPoint, TrialDesignInput

if TYPE_CHECKING:  # pragma: no cover - typing only
    import altair as alt

# Validated categorical hues (see the data-viz palette): slot 1 blue, slot 2 aqua.
_POWER_COLOR = "#2a78d6"
_ASSURANCE_COLOR = "#1baf7a"
# Shared muted token, identical in light and dark, for recessive reference lines and labels.
_MUTED = "#898781"

_POWER_LABEL = "Power"
_ASSURANCE_LABEL = "Bayesian assurance"


def operating_characteristics_chart(
    design: TrialDesignInput,
    grid: list[DesignPoint],
    recommendation: DesignPoint | None = None,
) -> "alt.Chart":
    """Build the layered operating-characteristics decision chart."""

    import altair as alt

    # Tidy (long-form) records for the two decision curves, so a single color encoding
    # drives both the lines and the legend. Kept as plain dicts -- no pandas needed.
    curve_rows = []
    for point in grid:
        curve_rows.append(
            {"n_per_arm": point.n_per_arm, "metric": _POWER_LABEL, "value": point.power}
        )
        curve_rows.append(
            {
                "n_per_arm": point.n_per_arm,
                "metric": _ASSURANCE_LABEL,
                "value": point.assurance,
            }
        )

    color_scale = alt.Scale(
        domain=[_POWER_LABEL, _ASSURANCE_LABEL],
        range=[_POWER_COLOR, _ASSURANCE_COLOR],
    )
    x_axis = alt.X(
        "n_per_arm:Q",
        title="N per arm",
        scale=alt.Scale(nice=False, zero=False),
    )
    y_axis = alt.Y(
        "value:Q",
        title="probability",
        scale=alt.Scale(domain=[0, 1]),
        axis=alt.Axis(format="%", tickCount=6),
    )

    curves = alt.Chart(alt.Data(values=curve_rows)).mark_line(
        strokeWidth=2, interpolate="monotone"
    ).encode(
        x=x_axis,
        y=y_axis,
        color=alt.Color(
            "metric:N",
            scale=color_scale,
            legend=alt.Legend(title=None, orient="top", direction="horizontal"),
        ),
        tooltip=[
            alt.Tooltip("n_per_arm:Q", title="N per arm"),
            alt.Tooltip("metric:N", title="Curve"),
            alt.Tooltip("value:Q", title="Probability", format=".3f"),
        ],
    )

    layers: list[alt.Chart] = []

    first_n = grid[0].n_per_arm if grid else 0
    last_n = grid[-1].n_per_arm if grid else 0

    # Label placement exploits the one thing always true of these monotonically-rising
    # curves: the top-left corner is empty (curves are low on the left) and the right edge
    # has a clear band above the target line (curves are high on the right). So reference
    # labels sit at the RIGHT edge, and the recommended-N label sits TOP-LEFT -- neither can
    # collide with the curves or each other regardless of the design.
    target_rule = alt.Chart(
        alt.Data(values=[{"y": design.desired_power}])
    ).mark_rule(color=_MUTED, strokeDash=[6, 4]).encode(y="y:Q")
    target_text = alt.Chart(
        alt.Data(
            values=[
                {
                    "x": last_n,
                    "y": design.desired_power,
                    "t": f"target power {design.desired_power:.0%}",
                }
            ]
        )
    ).mark_text(color=_MUTED, align="right", dx=-3, dy=-5, baseline="bottom").encode(
        x="x:Q", y="y:Q", text="t:N"
    )
    alpha_rule = alt.Chart(
        alt.Data(values=[{"y": design.alpha}])
    ).mark_rule(color=_MUTED, strokeDash=[2, 3], opacity=0.8).encode(y="y:Q")
    alpha_text = alt.Chart(
        alt.Data(values=[{"x": last_n, "y": design.alpha, "t": f"α = {design.alpha:.3f}"}])
    ).mark_text(color=_MUTED, align="right", dx=-3, dy=-5, baseline="bottom").encode(
        x="x:Q", y="y:Q", text="t:N"
    )
    layers.extend([target_rule, target_text, alpha_rule, alpha_text, curves])

    # Recommended-N annotation: a vertical rule and a ringed point on the power curve, with
    # a bold label beside the dot. The label sits up-and-to-the-left of the dot: for these
    # rising curves the region above the curve and left of the marker is always clear, so the
    # text never overlaps the curve. Near the left edge it flips to the right of the dot so it
    # cannot run off-canvas. (target power stays at the right edge, so nothing collides there.)
    if recommendation is not None:
        rec_n = recommendation.n_per_arm
        # Flip the label to the right of the dot only when it sits close enough to the left
        # edge that a left-extending label would run off-canvas; a small recommended N also
        # means a steep, quickly-saturating curve with a clear band to the dot's right.
        near_left_edge = last_n and rec_n < first_n + (last_n - first_n) * 0.18
        rec_rule = alt.Chart(
            alt.Data(values=[{"x": rec_n}])
        ).mark_rule(color=_MUTED, strokeDash=[4, 3]).encode(x="x:Q")
        rec_point = alt.Chart(
            alt.Data(values=[{"x": rec_n, "y": recommendation.power}])
        ).mark_point(
            color=_POWER_COLOR, size=90, filled=True, stroke="white", strokeWidth=1.5
        ).encode(x="x:Q", y="y:Q")
        rec_text = alt.Chart(
            alt.Data(
                values=[
                    {"x": rec_n, "y": recommendation.power, "t": f"recommended N = {rec_n}"}
                ]
            )
        ).mark_text(
            color=_POWER_COLOR,
            fontWeight="bold",
            align="left" if near_left_edge else "right",
            dx=10 if near_left_edge else -10,
            dy=-9,
            baseline="bottom",
        ).encode(x="x:Q", y="y:Q", text="t:N")
        layers.extend([rec_rule, rec_point, rec_text])

    return alt.layer(*layers).properties(height=360).configure_view(strokeOpacity=0)
