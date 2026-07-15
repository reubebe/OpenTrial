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
"""

from __future__ import annotations

import math

from opentrial.schemas import EvidenceRecord, PriorSummary

# A prior narrower than this claims more precision than this evidence base can support.
MIN_PRIOR_SD = 0.05


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


def build_prior(evidence: list[EvidenceRecord]) -> PriorSummary:
    """Pool effect records into a normal prior by DerSimonian-Laird random-effects."""

    usable = [record for record in evidence if record.standard_error > 0]
    if not usable:
        return PriorSummary(
            mean=0.0,
            sd=1.0,
            effective_n=0,
            records_used=0,
            method="weakly-informative fallback prior",
        )

    effects = [record.effect for record in usable]
    variances = [record.standard_error**2 for record in usable]

    # Fixed-effect pooling first: DerSimonian-Laird measures scatter about this mean.
    fixed_weights = [1.0 / v for v in variances]
    fixed_mean = sum(w * y for w, y in zip(fixed_weights, effects)) / sum(fixed_weights)

    tau_squared = _dersimonian_laird_tau_squared(effects, variances, fixed_mean)

    # Random-effects weights add tau^2 to each study's own variance, so heterogeneity both
    # widens the prior and flattens the weighting between studies.
    weights = [1.0 / (v + tau_squared) for v in variances]
    total_weight = sum(weights)
    mean = sum(w * y for w, y in zip(weights, effects)) / total_weight
    sd = max(math.sqrt(1.0 / total_weight), MIN_PRIOR_SD)

    method = (
        "DerSimonian-Laird random-effects prior"
        if tau_squared > 0
        else "inverse-variance prior (no heterogeneity detected; tau^2 = 0)"
    )

    return PriorSummary(
        mean=mean,
        sd=sd,
        effective_n=sum(record.n for record in usable),
        records_used=len(usable),
        method=method,
    )
