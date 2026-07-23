from __future__ import annotations

from opentrial.schemas import EvidenceRecord, PriorSummary


class BayesianPriorError(RuntimeError):
    """Raised when the PyMC Bayesian meta-analysis cannot be run."""


def build_prior_bayesian(
    evidence: list[EvidenceRecord],
    draws: int = 1000,
    tune: int = 1000,
    chains: int = 2,
    seed: int = 42,
) -> PriorSummary:
    """Build the evidence prior with a PyMC random-effects Bayesian meta-analysis.

    This is the probabilistic-programming counterpart to
    :func:`opentrial.compute.priors.build_prior`. Where the closed-form version pools
    studies analytically (inverse-variance weighting plus a heterogeneity bump), this
    fits the standard hierarchical (random-effects) meta-analysis model with PyMC:

        observed effect_i ~ Normal(theta_i, se_i)      # each study's measurement
        theta_i           ~ Normal(mu, tau)            # study-level true effects
        mu                ~ Normal(0, 1)               # population mean (weak prior)
        tau               ~ HalfNormal(0.5)            # between-study heterogeneity

    The evidence-derived prior is the *posterior predictive* distribution of a new
    study's true effect, i.e. Normal(mu, sqrt(Var(mu) + tau^2)). Its mean and SD become
    the returned :class:`PriorSummary`, so it is a drop-in replacement for the closed-form
    prior everywhere downstream.

    With fewer than two usable studies there is nothing to pool, so it transparently
    defers to the closed-form prior rather than running a sampler.
    """

    usable = [record for record in evidence if record.standard_error > 0]
    if len(usable) < 2:
        from opentrial.compute.priors import build_prior

        return build_prior(evidence)

    try:
        import numpy as np
        import pymc as pm
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised when extra is absent
        raise BayesianPriorError(
            'PyMC is not installed. Install the optional engine with '
            'pip install -e ".[bayes]".'
        ) from exc

    effects = np.array([record.effect for record in usable], dtype=float)
    standard_errors = np.array([record.standard_error for record in usable], dtype=float)

    try:
        with pm.Model():
            mu = pm.Normal("mu", mu=0.0, sigma=1.0)
            tau = pm.HalfNormal("tau", sigma=0.5)
            theta = pm.Normal("theta", mu=mu, sigma=tau, shape=len(usable))
            pm.Normal("obs", mu=theta, sigma=standard_errors, observed=effects)
            idata = pm.sample(
                draws=draws,
                tune=tune,
                chains=chains,
                random_seed=seed,
                progressbar=False,
                compute_convergence_checks=False,
            )
    except Exception as exc:  # pragma: no cover - sampler/backend failures
        raise BayesianPriorError(f"PyMC sampling failed: {exc}") from exc

    mu_samples = idata.posterior["mu"].to_numpy().reshape(-1)
    tau_samples = idata.posterior["tau"].to_numpy().reshape(-1)

    # Posterior predictive spread for a *new* study effect = mean uncertainty + heterogeneity,
    # mirroring what the closed-form prior captures with fixed_sd^2 + heterogeneity^2.
    rng = np.random.default_rng(seed)
    predictive = rng.normal(mu_samples, tau_samples)

    return PriorSummary(
        mean=float(mu_samples.mean()),
        sd=max(float(predictive.std(ddof=1)), 0.05),
        pooled_participants=sum(record.n for record in usable),
        records_used=len(usable),
        method="PyMC random-effects Bayesian meta-analysis (posterior predictive)",
    )
