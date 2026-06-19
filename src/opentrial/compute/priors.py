from __future__ import annotations

import math

from opentrial.schemas import EvidenceRecord, PriorSummary


def build_prior(evidence: list[EvidenceRecord]) -> PriorSummary:
    """Build a simple inverse-variance normal prior from effect records."""

    usable = [record for record in evidence if record.standard_error > 0]
    if not usable:
        return PriorSummary(
            mean=0.0,
            sd=1.0,
            effective_n=0,
            records_used=0,
            method="weakly-informative fallback prior",
        )

    weights = [1.0 / (record.standard_error**2) for record in usable]
    weighted_mean = sum(w * record.effect for w, record in zip(weights, usable)) / sum(weights)
    fixed_sd = math.sqrt(1.0 / sum(weights))

    if len(usable) > 1:
        sample_variance = sum((record.effect - weighted_mean) ** 2 for record in usable) / (
            len(usable) - 1
        )
        heterogeneity = math.sqrt(max(sample_variance, 0.0))
    else:
        heterogeneity = 0.0

    prior_sd = max(math.sqrt(fixed_sd**2 + heterogeneity**2), 0.05)

    return PriorSummary(
        mean=weighted_mean,
        sd=prior_sd,
        effective_n=sum(record.n for record in usable),
        records_used=len(usable),
        method="inverse-variance normal prior with heterogeneity inflation",
    )
