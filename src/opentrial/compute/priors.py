"""Build the evidence-derived prior by random-effects meta-analysis.

Pooling published effects into one normal prior is a meta-analysis, and the question that
decides the prior's width is how much the studies genuinely disagree.

Observed effects scatter for two reasons: real between-study heterogeneity (different
populations, protocols, endpoints) and each study's own sampling error. Only the first should
widen the prior, because the second is already carried by the inverse-variance term. The
plain sample SD of the observed effects mixes the two together and therefore double-counts
sampling error, inflating the prior.

**DerSimonian-Laird** separates them. Cochran's ``Q`` measures the observed scatter; its
expectation under "no heterogeneity" is its degrees of freedom ``k - 1``. Whatever exceeds
that expectation is attributed to real heterogeneity, and ``Q`` at or below ``k - 1`` means
none is detectable, so ``tau^2`` truncates to zero and the estimator collapses to the
fixed-effect answer. Standard library only.

DerSimonian-Laird is a one-shot *moment* estimator, and with only a handful of studies its
``tau^2`` is noisy and truncates to zero readily. **REML** (restricted maximum likelihood)
is the steadier alternative: less biased at small ``k`` and the estimator most meta-analysis
packages default to. It is defined as the ``tau^2 >= 0`` that maximizes the restricted profile
log-likelihood, and we compute it that way directly (see :func:`_reml_tau_squared`) rather than
by the popular fixed-point iteration, which can converge to an interior *local* optimum when
the profile likelihood is bimodal and the true maximum is the boundary ``tau^2 = 0``. It is
offered as ``tau_method="reml"``; the moment estimator remains the default so results stay
comparable with the original poster. Both are standard-library only.
"""

from __future__ import annotations

import math
import re
from typing import Callable, Literal

from opentrial.schemas import EvidenceRecord, PriorSummary

# A ClinicalTrials.gov registry id, the strongest signal that two records are the same trial.
_NCT_PATTERN = re.compile(r"NCT\d{8}", re.IGNORECASE)

# A prior narrower than this claims more precision than this evidence base can support.
MIN_PRIOR_SD = 0.05

TauMethod = Literal["dl", "reml"]

# REML search controls. tau^2 is found by maximizing the restricted profile log-likelihood
# over tau^2 >= 0: a coarse grid locates the basin of the global interior optimum (the profile
# can be bimodal, so a single-seed hill-climb is not safe), golden section refines it, and the
# result is compared against the boundary tau^2 = 0. All bounded and deterministic.
_REML_GRID = 1024
_REML_MAX_EXPANSIONS = 100
_GOLDEN_TOL = 1e-12
_INV_PHI = (math.sqrt(5.0) - 1.0) / 2.0  # 0.6180339..., the golden-section ratio


def _trial_identity(record: EvidenceRecord) -> str:
    """A key identifying the underlying trial, for collapsing duplicate reports.

    A registry id (NCT number, found anywhere in the url, title or notes) is the safe signal.
    Failing that, records are matched only on an *exact* effect / standard-error / n /
    endpoint / indication fingerprint: two papers reporting one trial repeat the same primary
    numbers, while requiring an exact match avoids wrongly merging genuinely distinct trials.
    """

    blob = f"{record.url} {record.title} {record.notes}"
    match = _NCT_PATTERN.search(blob)
    if match:
        return "nct:" + match.group(0).upper()
    return (
        f"fp:{record.endpoint.strip().lower()}|{record.indication.strip().lower()}"
        f"|{record.effect!r}|{record.standard_error!r}|{record.n}"
    )


def deduplicate_trial_records(
    records: list[EvidenceRecord],
) -> tuple[list[EvidenceRecord], int]:
    """Collapse records that describe the same trial, keeping the most informative one.

    Two publications of a single trial must not both enter the prior, or that trial is
    weighted twice. Records are grouped by :func:`_trial_identity`, and each group contributes
    only its most informative member (largest ``n``, tie-broken by smaller standard error).
    Returns the kept records in their original order and the count removed.
    """

    best: dict[str, EvidenceRecord] = {}
    order: list[str] = []
    for record in records:
        key = _trial_identity(record)
        incumbent = best.get(key)
        if incumbent is None:
            best[key] = record
            order.append(key)
        elif (record.n, -record.standard_error) > (incumbent.n, -incumbent.standard_error):
            best[key] = record
    kept = [best[key] for key in order]
    return kept, len(records) - len(kept)


def _dersimonian_laird_tau_squared(
    effects: list[float], variances: list[float], fixed_mean: float
) -> float:
    """Between-study variance ``tau^2`` by the DerSimonian-Laird moment estimator.

    Returns 0.0 when the observed scatter is no larger than sampling error alone would
    produce, which is the estimator's documented behaviour, not a special case.
    """

    n_studies = len(effects)
    if n_studies < 2:
        return 0.0

    weights = [1.0 / v for v in variances]
    total_weight = sum(weights)

    # Cochran's Q: observed scatter, weighted by precision. E[Q] = k - 1 under homogeneity.
    q_statistic = sum(w * (y - fixed_mean) ** 2 for w, y in zip(weights, effects))

    # The scaling constant that converts the excess of Q over its expectation into a variance.
    scaling = total_weight - sum(w**2 for w in weights) / total_weight
    if scaling <= 0:
        return 0.0

    return max(0.0, (q_statistic - (n_studies - 1)) / scaling)


def _reml_restricted_loglik(
    tau_squared: float, effects: list[float], variances: list[float]
) -> float:
    """The REML restricted profile log-likelihood at ``tau^2``, up to an additive constant.

    The population mean ``mu`` is concentrated out (replaced by its weighted-least-squares
    value), leaving a function of ``tau^2`` alone. Maximizing it *is* REML.
    """

    weights = [1.0 / (v + tau_squared) for v in variances]
    total_weight = sum(weights)
    mean = sum(w * y for w, y in zip(weights, effects)) / total_weight
    return -0.5 * (
        sum(math.log(v + tau_squared) for v in variances)
        + math.log(total_weight)
        + sum(w * (y - mean) ** 2 for w, y in zip(weights, effects))
    )


def _golden_section_max(func: Callable[[float], float], a: float, b: float) -> float:
    """Return the argmax of a unimodal ``func`` on ``[a, b]`` by golden-section search."""

    c = b - _INV_PHI * (b - a)
    d = a + _INV_PHI * (b - a)
    fc, fd = func(c), func(d)
    for _ in range(200):  # far more than needed to reach _GOLDEN_TOL; a hard termination bound
        if b - a < _GOLDEN_TOL:
            break
        if fc < fd:
            a, c, fc = c, d, fd
            d = a + _INV_PHI * (b - a)
            fd = func(d)
        else:
            b, d, fd = d, c, fc
            c = b - _INV_PHI * (b - a)
            fc = func(c)
    return (a + b) / 2.0


def _reml_tau_squared(
    effects: list[float], variances: list[float], initial_tau_squared: float
) -> float:
    """Between-study variance ``tau^2`` by restricted maximum likelihood.

    REML is the ``tau^2 >= 0`` that maximizes the restricted profile log-likelihood
    (:func:`_reml_restricted_loglik`). We maximize it directly rather than by the usual
    fixed-point iteration, which can (a) fail to converge on some inputs and (b) settle on an
    interior local optimum when the profile is bimodal and the boundary ``tau^2 = 0`` is the
    true maximum. A coarse grid finds the basin of the best interior point, golden section
    refines it, and it is kept only if it beats the boundary; otherwise the estimate is 0.

    ``initial_tau_squared`` (the DerSimonian-Laird value) is used only to scale the search
    bracket. Returns 0.0 with fewer than two studies, matching the moment estimator.
    """

    n_studies = len(effects)
    if n_studies < 2:
        return 0.0

    def loglik(tau_squared: float) -> float:
        return _reml_restricted_loglik(tau_squared, effects, variances)

    boundary_loglik = loglik(0.0)

    # A generous upper bracket, doubled until the profile is clearly past its peak, so the grid
    # below always spans the global interior optimum however heterogeneous the studies are.
    spread = (max(effects) - min(effects)) ** 2
    tau_high = max(4.0 * initial_tau_squared, spread, max(variances), 1e-6)
    for _ in range(_REML_MAX_EXPANSIONS):
        if loglik(tau_high) <= loglik(tau_high * 0.5):
            break
        tau_high *= 2.0

    # Coarse grid over the interior locates the basin of the global maximum (the profile can be
    # bimodal, so a single-seed climb is not safe), then golden section refines within it.
    step = tau_high / _REML_GRID
    best_tau, best_loglik = step, loglik(step)
    for i in range(2, _REML_GRID + 1):
        tau = i * step
        value = loglik(tau)
        if value > best_loglik:
            best_loglik, best_tau = value, tau
    interior = _golden_section_max(loglik, max(0.0, best_tau - step), best_tau + step)

    # Constrained REML: the estimate is the boundary 0 unless an interior point strictly beats
    # it. This is the correction the fixed-point iteration misses.
    return interior if loglik(interior) > boundary_loglik else 0.0


def build_prior(
    evidence: list[EvidenceRecord], tau_method: TauMethod = "dl"
) -> PriorSummary:
    """Pool effect records into a normal prior by random-effects meta-analysis.

    ``tau_method`` selects the between-study variance estimator: ``"dl"`` (DerSimonian-Laird
    moment estimator, the default) or ``"reml"`` (restricted maximum likelihood, steadier at
    small numbers of studies). Everything downstream of ``tau^2`` is identical.
    """

    with_effect = [record for record in evidence if record.standard_error > 0]
    # Collapse duplicate reports of the same trial before pooling, so no trial is counted
    # twice. This is the correction for the independence assumption.
    usable, records_merged = deduplicate_trial_records(with_effect)
    if not usable:
        return PriorSummary(
            mean=0.0,
            sd=1.0,
            pooled_participants=0,
            records_used=0,
            records_merged=records_merged,
            method="weakly-informative fallback prior",
        )

    effects = [record.effect for record in usable]
    variances = [record.standard_error**2 for record in usable]

    # Fixed-effect pooling first: the moment estimator measures scatter about this mean, and
    # it also seeds the REML iteration.
    fixed_weights = [1.0 / v for v in variances]
    fixed_mean = sum(w * y for w, y in zip(fixed_weights, effects)) / sum(fixed_weights)

    dl_tau_squared = _dersimonian_laird_tau_squared(effects, variances, fixed_mean)
    if tau_method == "reml":
        tau_squared = _reml_tau_squared(effects, variances, dl_tau_squared)
    else:
        tau_squared = dl_tau_squared

    # Random-effects weights add tau^2 to each study's own variance, so heterogeneity both
    # widens the prior and flattens the weighting between studies.
    weights = [1.0 / (v + tau_squared) for v in variances]
    total_weight = sum(weights)
    mean = sum(w * y for w, y in zip(weights, effects)) / total_weight
    sd = max(math.sqrt(1.0 / total_weight), MIN_PRIOR_SD)

    if tau_method == "reml":
        method = (
            "REML random-effects prior"
            if tau_squared > 0
            else "inverse-variance prior (REML tau^2 = 0)"
        )
    else:
        method = (
            "DerSimonian-Laird random-effects prior"
            if tau_squared > 0
            else "inverse-variance prior (no heterogeneity detected; tau^2 = 0)"
        )

    return PriorSummary(
        mean=mean,
        sd=sd,
        pooled_participants=sum(record.n for record in usable),
        records_used=len(usable),
        records_merged=records_merged,
        method=method,
    )
