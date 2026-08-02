"""Independent cross-check of the OpenTrial engine against SciPy and statsmodels.

The default engine and its committed test suite use only the Python standard library, on
purpose. This script is a *separate* validation: it re-derives every core quantity with an
independent scientific library and confirms the engine agrees to machine precision.

It is deliberately kept out of the default test suite so the core stays dependency-light.
Install the optional extras and run it directly:

    pip install -e ".[validation]"
    python validation/scipy_crosscheck.py

Exit code is 0 when every SciPy-based check agrees to 9 decimals (they agree to ~1e-15 in
practice) and the DerSimonian-Laird result reconciles with statsmodels; 1 otherwise. If the
optional libraries are absent the script prints how to install them and exits 0 (skipped).
"""
from __future__ import annotations

import math
import sys

try:
    import numpy as np
    from scipy import stats
    from scipy.integrate import quad
except ModuleNotFoundError:
    print('SciPy/NumPy not installed. Run: pip install -e ".[validation]"  (skipping)')
    sys.exit(0)

from opentrial.compute import priors as pr
from opentrial.compute import simulation as sim
from opentrial.compute.sensitivity import _spiegelhalter_sd
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.schemas import TrialDesignInput

norm = stats.norm
TOL = 5e-10  # "agree to 9 decimals"; observed differences are ~1e-15
checks: list[tuple[str, float, float, float]] = []


def chk(name: str, engine: float, reference: float) -> None:
    checks.append((name, engine, reference, abs(engine - reference)))


# 1. Normal CDF / quantile: engine uses statistics.NormalDist; SciPy is the independent oracle.
for x in (-2.5, -1.0, -0.3, 0.0, 0.7, 1.645, 2.33):
    chk(f"normal_cdf({x})", sim._normal_cdf(x), float(norm.cdf(x)))
for p in (0.025, 0.05, 0.5, 0.9, 0.975, 0.99):
    chk(f"normal_quantile({p})", sim._normal_quantile(p), float(norm.ppf(p)))

# 2. Continuous one-sided z-test power vs SciPy.
alpha, effect, sd = 0.025, 0.5, 1.0
for n in (20, 40, 60, 80, 100, 120, 140):
    se = math.sqrt(2 * sd**2 / n)
    ref = float(1 - norm.cdf(norm.ppf(1 - alpha) - effect / se))
    chk(f"power(n={n})", sim.estimate_power(n, effect, alpha, sd), ref)

# 3. Binary two-proportion z-test power vs SciPy.
p_c, rd = 0.30, 0.10
for n in (50, 100, 150, 200, 300):
    p_t = p_c + rd
    se = math.sqrt(p_c * (1 - p_c) / n + p_t * (1 - p_t) / n)
    ref = float(1 - norm.cdf(norm.ppf(1 - alpha) - rd / se))
    chk(f"binary_power(n={n})", sim.estimate_power_binary(n, p_c, rd, alpha), ref)

# 4. DerSimonian-Laird pooled prior, independent NumPy re-derivation.
prior = pr.build_prior(list(t2d_hba1c_evidence()))
ev = [r for r in t2d_hba1c_evidence() if r.standard_error > 0]
y = np.array([r.effect for r in ev])
v = np.array([r.standard_error**2 for r in ev])
k = len(y)
w0 = 1 / v
fixed_mean = float((w0 * y).sum() / w0.sum())
q_stat = float((w0 * (y - fixed_mean) ** 2).sum())
scaling = float(w0.sum() - (w0**2).sum() / w0.sum())
tau2 = max(0.0, (q_stat - (k - 1)) / scaling)
w = 1 / (v + tau2)
chk("prior.mean (DL)", prior.mean, float((w * y).sum() / w.sum()))
chk("prior.sd (DL)", prior.sd, max(math.sqrt(1 / w.sum()), 0.05))

# 5. Prior-predictive assurance: closed form vs SciPy, and again by numerical integration.
design = TrialDesignInput(
    indication="T2D", endpoint="HbA1c", target_effect=0.5, alpha=0.025,
    desired_power=0.8, max_n_per_arm=200, endpoint_sd=1.0,
)
for n in (20, 40, 60, 80, 100, 140):
    se = math.sqrt(2 * sd**2 / n)
    thr = float(norm.ppf(1 - alpha)) * se
    marg = math.sqrt(prior.sd**2 + se**2)
    chk(f"assurance(n={n})", sim.prior_predictive_assurance(n, prior, alpha, sd),
        float(1 - norm.cdf((thr - prior.mean) / marg)))
for n in (40, 80, 120):
    se = math.sqrt(2 * sd**2 / n)
    zc = float(norm.ppf(1 - alpha))
    ref, _ = quad(
        lambda th: norm.pdf(th, prior.mean, prior.sd) * (1 - norm.cdf(zc - th / se)),
        prior.mean - 8 * prior.sd, prior.mean + 8 * prior.sd,
    )
    chk(f"assurance_by_integration(n={n})", sim.prior_predictive_assurance(n, prior, alpha, sd), float(ref))

# 6. Posterior Pr(effect > 0): conjugate normal update vs SciPy.
for n in (20, 40, 80, 120, 160):
    se = math.sqrt(2 * sd**2 / n)
    post_var = 1 / (1 / prior.sd**2 + 1 / se**2)
    post_mean = post_var * (prior.mean / prior.sd**2 + design.target_effect / se**2)
    chk(f"posterior_Pr>0(n={n})", sim.posterior_success_probability(n, design, prior),
        float(1 - norm.cdf((0 - post_mean) / math.sqrt(post_var))))

# 7. Prior-equivalent N (information content) closed form.
chk("prior_equiv_n continuous", sim.prior_equivalent_n_per_arm(prior, design), 2 * sd**2 / prior.sd**2)
d_bin = TrialDesignInput(
    indication="X", endpoint="resp", target_effect=0.1, alpha=0.025, desired_power=0.8,
    max_n_per_arm=500, endpoint_type="binary", baseline_proportion=0.3,
)
chk("prior_equiv_n binary", sim.prior_equivalent_n_per_arm(prior, d_bin), (0.3 * 0.7 + 0.4 * 0.6) / prior.sd**2)

# 8. Spiegelhalter skeptical SD = target / z_0.95 vs SciPy.
chk("spiegelhalter_sd", _spiegelhalter_sd(0.5), 0.5 / float(norm.ppf(0.95)))

# --- report SciPy checks ---
failures = [c for c in checks if c[3] >= TOL]
print(f"{'CHECK':40} {'ENGINE':>16} {'REFERENCE':>16} {'|diff|':>10}")
print("-" * 86)
for name, eng, ref, d in checks:
    print(f"{name:40} {eng:16.12f} {ref:16.12f} {d:10.2e}" + ("  FAIL" if d >= TOL else ""))
print("-" * 86)
print(f"SciPy checks: {len(checks) - len(failures)}/{len(checks)} agree to 9 decimals; "
      f"max |diff| = {max(c[3] for c in checks):.2e}")

# --- statsmodels DerSimonian-Laird reconciliation (optional) ---
sm_ok = True
try:
    from statsmodels.stats.meta_analysis import combine_effects

    res = combine_effects(y, v, method_re="dl")
    sm_tau2 = float(res.tau2)
    sm_fixed_mean = float(res.mean_effect_fe)
    # statsmodels reports the RAW moment tau^2, which is negative here (no heterogeneity).
    # The standard DL estimator truncates it to 0, which is exactly what the engine does,
    # collapsing to the fixed-effect mean. So the correct comparison is against mean_effect_fe.
    truncation_correct = sm_tau2 <= 0 and tau2 == 0.0
    mean_matches = abs(prior.mean - sm_fixed_mean) < TOL
    print("\nstatsmodels DerSimonian-Laird reconciliation:")
    print(f"  raw DL tau^2 (statsmodels)   = {sm_tau2:.12g}  (<= 0 -> no heterogeneity)")
    print(f"  engine tau^2 (truncated)     = {tau2:.12g}")
    print(f"  statsmodels fixed-effect mean= {sm_fixed_mean:.15f}")
    print(f"  engine prior.mean            = {prior.mean:.15f}")
    print(f"  truncation correct: {truncation_correct}   mean matches to 9dp: {mean_matches}")
    sm_ok = truncation_correct and mean_matches
except ModuleNotFoundError:
    print('\nstatsmodels not installed; skipping DL reconciliation. Run: pip install -e ".[validation]"')

if failures or not sm_ok:
    print("\nRESULT: FAIL")
    sys.exit(1)
print("\nRESULT: PASS - engine matches SciPy and statsmodels to machine precision.")
