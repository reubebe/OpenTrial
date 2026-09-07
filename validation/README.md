# Independent validation

The OpenTrial engine and its committed test suite use only the Python standard library, by
design, so the core stays dependency-light and reproducible offline.

This folder holds a **separate** cross-check that re-derives every core quantity with
independent scientific libraries (SciPy and statsmodels) and confirms the engine agrees to
machine precision. It is intentionally kept out of the default test suite so the core carries
no heavy dependencies.

## Run it

```bash
pip install -e ".[validation]"     # adds scipy + statsmodels (not needed by the engine itself)
python validation/scipy_crosscheck.py
```

## What it checks (44 SciPy checks + a statsmodels reconciliation)

- Normal CDF and quantiles against `scipy.stats.norm`.
- Continuous one-sided z-test power and binary two-proportion power.
- Prior-predictive assurance, by the closed form and again by SciPy numerical integration over
  the prior (two independent routes).
- Posterior Pr(effect > 0) via the conjugate normal update.
- DerSimonian-Laird pooled prior mean and SD.
- Prior-equivalent sample size and the Spiegelhalter skeptical SD.

Every SciPy-based check agrees to roughly 1e-15 (machine precision).

## The statsmodels DerSimonian-Laird note

On the seeded demo evidence, Cochran's Q (1.52) is below its expectation (3 df), so there is no
detectable heterogeneity. `statsmodels` reports the raw moment estimate `tau^2 = -0.0061`
(negative). The standard DerSimonian-Laird estimator truncates `tau^2` to 0, which is exactly
what OpenTrial does, collapsing to the fixed-effect result. Once truncated, the engine's pooled
mean matches the statsmodels fixed-effect mean to 15 decimals:

```
statsmodels fixed-effect mean : 0.5008966148215919
engine prior.mean             : 0.500896614821592
```

So the apparent difference from the statsmodels random-effects mean is a truncation-convention
difference, and it confirms the engine's handling rather than contradicting it.
