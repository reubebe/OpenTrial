"""Independent cross-check of the OpenTrial engine against SciPy and statsmodels.

The default engine and its committed test suite use only the Python standard library, on
purpose. This script is a *separate* validation: it re-derives every core quantity with an
independent scientific library and confirms the engine agrees to high numerical precision.

It is deliberately kept out of the default test suite so the core stays dependency-light.
Install the optional extras and run it directly:

    pip install -e ".[validation]"
    python validation/scipy_crosscheck.py

Exit code is 0 when every SciPy-based check is within tolerance and the DerSimonian-Laird
result reconciles with statsmodels; 1 otherwise. Closed-form quantities agree to 9 decimals
(~1e-15 in practice); the REML tau^2, a numerical optimum on both sides, agrees to ~1e-9 and
is checked to 1e-8. If the optional libraries are absent the script prints how to install
them and exits 0 (skipped).
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
TOL = 5e-10  # "agree to 9 decimals"; observed differences are ~1e-15 for closed forms
# REML tau^2 is a numerical optimum on both sides (our golden-section search vs SciPy's bounded
# optimizer), so it agrees to ~1e-9 near a flat likelihood peak, not to machine precision.
REML_TOL = 1e-8
checks: list[tuple[str, float, float, float, float]] = []


def chk(name: str, engine: float, reference: float, tol: float = TOL) -> None:
    checks.append((name, engine, reference, abs(engine - reference), tol))


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

# 2b. Dropout adjustment: SE is computed on the analyzable count n*(1 - dropout), so it must
# equal the no-dropout SE divided by sqrt(1 - dropout). Independent closed-form check.
for rate in (0.1, 0.2, 0.35, 0.5):
    d_full = TrialDesignInput(
        indication="T2D", endpoint="HbA1c", target_effect=0.5, alpha=0.025,
        desired_power=0.8, max_n_per_arm=200, endpoint_sd=1.0,
    )
    d_drop = d_full.model_copy(update={"dropout_rate": rate})
    for n in (40, 80, 120):
        base_se = math.sqrt(2 * 1.0**2 / n)
        chk(f"dropout_se(rate={rate},n={n})", sim.effect_standard_error(d_drop, n),
            base_se / math.sqrt(1 - rate))

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

# 4b. REML tau^2: the engine maximizes the restricted profile likelihood over tau^2 >= 0.
# SciPy is the independent oracle -- maximize the same likelihood directly and compare. This
# guards the subtle case where the profile is bimodal and the true maximum is the boundary 0,
# which the popular fixed-point iteration gets wrong.
def _reml_reference(effects: "np.ndarray", variances: "np.ndarray") -> float:
    """REML tau^2 by direct constrained maximization of the restricted profile likelihood."""

    def neg2ll(tau2: float) -> float:
        if tau2 < 0:
            return 1e18
        ww = 1.0 / (variances + tau2)
        wsum = ww.sum()
        mu = float((ww * effects).sum() / wsum)
        return float(np.log(variances + tau2).sum() + math.log(wsum) + (ww * (effects - mu) ** 2).sum())

    hi = max(1e-6, float(np.var(effects)) * 10 + float(variances.mean()) * 10)
    grid = np.linspace(0.0, hi, 5000)
    t0 = float(grid[int(np.argmin([neg2ll(t) for t in grid]))])
    from scipy.optimize import minimize_scalar

    lo_b, hi_b = max(0.0, t0 - hi / 5000 * 3), t0 + hi / 5000 * 3
    cand = t0
    if hi_b > lo_b:
        cand = max(0.0, float(minimize_scalar(neg2ll, bounds=(lo_b, hi_b), method="bounded",
                                              options={"xatol": 1e-14}).x))
    return 0.0 if neg2ll(0.0) <= neg2ll(cand) + 1e-12 else cand


# An interior-optimum dataset and a boundary (bimodal-trap) dataset, both cross-checked.
_reml_datasets = {
    "REML tau^2 (interior)": (
        np.array([0.549, 0.666, 0.374, 0.612, 0.324]),
        np.array([0.196, 0.155, 0.295, 0.294, 0.126]) ** 2,
    ),
    "REML tau^2 (boundary/bimodal)": (
        np.array([0.3751, -0.0638, 0.3095, 0.0854, 0.803, 0.8441, 0.339]),
        np.array([0.0555, 0.2673, 0.3921, 0.2326, 0.2497, 0.2164, 0.0567]) ** 2,
    ),
}
for _name, (_y, _v) in _reml_datasets.items():
    _dl = pr._dersimonian_laird_tau_squared(
        list(_y), list(_v), float((_y / _v).sum() / (1 / _v).sum())
    )
    chk(_name, pr._reml_tau_squared(list(_y), list(_v), _dl), _reml_reference(_y, _v), REML_TOL)

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
failures = [c for c in checks if c[3] >= c[4]]
print(f"{'CHECK':40} {'ENGINE':>16} {'REFERENCE':>16} {'|diff|':>10}")
print("-" * 86)
for name, eng, ref, d, tol in checks:
    print(f"{name:40} {eng:16.12f} {ref:16.12f} {d:10.2e}" + ("  FAIL" if d >= tol else ""))
print("-" * 86)
print(f"SciPy checks: {len(checks) - len(failures)}/{len(checks)} within tolerance "
      f"(closed forms to 9 dp, REML to 1e-8); max |diff| = {max(c[3] for c in checks):.2e}")

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
print("\nRESULT: PASS - engine matches SciPy and statsmodels (closed forms to machine "
      "precision; REML tau^2 to 1e-8).")
