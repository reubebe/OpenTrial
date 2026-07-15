# Methods

The README calls the operating characteristics "the part to scrutinize." This document is
what makes that possible: every formula the proof of concept uses, written out, with its
assumptions and its known limitations stated plainly.

Nothing here is new machinery. It is a transparent account of code that already exists, so a
reviewer can check the math without reading the source. Line references point at
`src/opentrial/compute/`.

**Notation.** `Φ` is the standard normal CDF, `z_p = Φ⁻¹(p)` its quantile, `α` the one-sided
significance level, `δ` the target effect, and `n` the per-arm sample size. All worked numbers
below come from the seeded T2D / HbA1c demo (`src/opentrial/data/demo_evidence.py`) with
`δ = 0.5`, `α = 0.025`, desired power `0.8`.

---

## 1. The evidence-derived prior

`compute/priors.py` pools the cited records into one normal prior by **inverse-variance
weighting**, the standard fixed-effect meta-analysis estimator.

Each usable record contributes weight `wᵢ = 1 / SEᵢ²`, so precise studies count more:

```
prior mean  μ₀ = Σ wᵢ·effectᵢ / Σ wᵢ
fixed-effect SE      = sqrt( 1 / Σ wᵢ )
```

That fixed-effect SE assumes every study estimates the *same* underlying effect. Real trials
differ, so the prior SD is inflated by a **heterogeneity** term (the sample SD of the observed
effects) and floored at 0.05:

```
τ̂ = sample SD of the observed effects        (0 when only one record)
prior SD  σ₀ = max( sqrt( fixed_SE² + τ̂² ), 0.05 )
```

**The honesty rule.** Only records with `standard_error > 0` reach the prior. Registry rows,
FAERS safety counts, and label text carry no effect estimate, so they are listed in the
provenance table for traceability but **contribute nothing to the numbers**. With no usable
record at all, the prior falls back to `Normal(0, 1)`: weakly informative and centered on *no
effect*, which is the conservative direction.

On the demo's four records this gives **μ₀ = 0.5009, σ₀ = 0.1016** from `n = 2564` pooled
participants.

### Limitations worth a reviewer's attention

- **τ̂ is not a proper heterogeneity estimator.** The sample SD of observed effects contains
  both real between-study heterogeneity *and* each study's own sampling error, so it
  double-counts the latter and **over-inflates the prior SD**. A DerSimonian-Laird or REML
  estimate of `τ²` subtracts out the within-study part. The error is in the conservative
  direction (a wider prior claims less), but it is an approximation, not the textbook
  random-effects prior. On the demo it is the dominant term: `fixed_SE = 0.054` vs
  `τ̂ = 0.086`.
- **`effective_n` is descriptive, not statistical.** It sums the participants behind the
  records. It is provenance, not the prior's information content. The prior is not literally
  worth 2564 patients.
- Records are assumed independent. Two publications reporting the same trial would be
  double-counted.

---

## 2. Standard error of the effect

Everything downstream needs exactly one quantity: the effect-scale SE at `n` per arm. For a
two-arm continuous endpoint with population SD `σ` and equal allocation:

```
SE(n) = sqrt( 2σ² / n )
```

With `σ = 1.0` (the default) the effect is read as a **standardized** difference. At `n = 80`,
`SE = 0.158`.

Expressing the four formulas below in terms of `SE(n)` alone is what keeps them short and
mutually consistent. It is also what a future binary or count endpoint would slot into, by
supplying its own SE.

---

## 3. The four core formulas

All four live in `compute/simulation.py` and use a one-sided z-test rejecting when the observed
difference exceeds `z_{1−α}·SE`.

### Power: "if the effect really is δ, how often do we win?"

```
power = 1 − Φ( z_{1−α} − δ / SE(n) )
```

Frequentist, prior-free. `beta = 1 − power`.

### Assurance: "averaged over what we actually believe, how often do we win?"

Power at a *single assumed* effect is optimistic; assurance averages success over the prior
(prior-predictive; O'Hagan et al.). The prior and the sampling error convolve, so the marginal
SD adds in quadrature:

```
assurance = 1 − Φ( ( z_{1−α}·SE(n) − μ₀ ) / sqrt( σ₀² + SE(n)² ) )
```

Assurance is nearly always **below** power at the same `n` (0.845 vs 0.885 at `n = 80` on the
demo), because the prior admits effects smaller than the target. That gap is the honest part.

### Posterior Pr(effect > 0): the conjugate Bayesian update

Normal prior times normal likelihood, in precision (`1/variance`) form:

```
posterior variance  σ_post² = 1 / ( 1/σ₀² + 1/SE² )
posterior mean      μ_post  = σ_post² · ( μ₀/σ₀² + δ/SE² )
Pr(effect > 0)              = 1 − Φ( −μ_post / σ_post )
```

> **Read this one carefully.** It answers a *hypothetical*: "if the trial observed exactly the
> target effect δ, what would we then believe?" It is not a prediction from data, because no
> data exists at design time. Since the demo's prior and δ both sit near 0.5, far above zero,
> this value pins at **1.0000** and stays there across the grid. It is close to uninformative
> here, and it should not be read as "the trial is certain to succeed."

### Type I error

The analytic grid reports the **nominal** α, by construction, since the z-test's critical value
is defined to give it. It is a reference column, not a measurement. Section 4 is what actually
measures it.

---

## 4. The sample-size grid and the recommendation

`simulate_design_grid` walks `n` from 20 to `max_n_per_arm` in **steps of 20**, evaluating all
four quantities at each point. `recommend_sample_size` returns the **first** `n` whose power
reaches the desired power.

Consequence: the recommendation is granular to 20, so it **overshoots**. The demo recommends
`n = 80` with power **0.885**, not 0.800; the true 80% crossing is at `n = 63`. This is a
safe-direction rounding, but a reviewer comparing against a textbook formula should expect the
gap. If no `n` reaches the target power within `max_n_per_arm`, the recommendation is `None`
and the report says the design is underpowered rather than inventing a number.

---

## 5. The Monte Carlo calibration check

`compute/mc.py` (opt-in; standard-library `random` only) re-derives the same grid by
simulation. For each `n` it draws `n_sims` trials from the summary-level sampling distribution
`Normal(true effect, SE(n))` and applies the same decision rule:

| Quantity | True effect drawn from | Should match |
|---|---|---|
| power | fixed at `δ` | analytic power |
| **Type I error** | fixed at **0** (the null) | nominal `α` |
| assurance | a fresh draw from the prior | analytic assurance |

**Why bother, if the closed form is exact?** For this z-test it *is* exact, so Monte Carlo
cannot improve the answer. Its value is that the Type I column stops being a definition and
becomes a **measurement**: simulate under the null, count rejections, see whether it lands on
α. At 20,000 sims the demo returns 0.0240 to 0.0253 against a nominal 0.025, and MC power at
`n = 80` is 0.8850 against the analytic 0.8854. A reviewer can watch the check pass rather
than take the formula on trust.

It is also the seam where realism gets added later. Non-normal endpoints, dropout, or
group-sequential looks have no closed form, and this is where they would go.

Posterior Pr(effect > 0) stays analytic even here: it is a conjugate Bayesian update, not a
frequentist rejection rate, so simulating it would be a category error.

---

## 6. Assumptions, stated once

The math is a deliberate approximation. It assumes:

- **Normality** of the effect's sampling distribution, a z-test rather than a t-test. At small
  `n` the z-test is mildly anti-conservative, because it ignores the uncertainty in estimating
  `σ`.
- **A known endpoint SD** `σ`, supplied by the user rather than estimated from the trial.
- **Two arms, equal allocation, one-sided test, a single analysis**, with no interim looks.
- **No dropout, no covariate adjustment, no multiplicity** across endpoints or subgroups.
- **A normal prior**, adequate for pooling effects but not for skewed or bounded parameters.
- **Independent evidence records**, each contributing one effect and one standard error.

Each assumption is a place a real design would need more, and the README's *Future work*
section tracks the ones already on the roadmap.

---

## 7. Reproducing every number in this document

```bash
PYTHONPATH=src python3 -c "
from opentrial.compute.priors import build_prior
from opentrial.compute.simulation import simulate_design_grid, recommend_sample_size
from opentrial.data.demo_evidence import t2d_hba1c_evidence
from opentrial.schemas import TrialDesignInput

prior = build_prior(list(t2d_hba1c_evidence()))
print(f'prior: mean={prior.mean:.4f} sd={prior.sd:.4f} n={prior.effective_n}')

design = TrialDesignInput(indication='Type 2 Diabetes', endpoint='HbA1c',
                          target_effect=0.5, alpha=0.025, desired_power=0.8,
                          max_n_per_arm=300)
point = recommend_sample_size(simulate_design_grid(design, prior), design.desired_power)
print(f'recommended N={point.n_per_arm} power={point.power:.4f} assurance={point.assurance:.4f}')
"
```

Expected output:

```
prior: mean=0.5009 sd=0.1016 n=2564
recommended N=80 power=0.8854 assurance=0.8453
```

The default path is deterministic, so these are exact. The Monte Carlo path is seeded
(`seed=42`) and therefore reproducible too, but its values are estimates and will move if the
seed or `n_sims` changes.

---

## References

- O'Hagan, Stevens & Campbell (2005), *Assurance in clinical trial design.* The
  prior-predictive success probability in section 3.
- DerSimonian & Laird (1986), *Meta-analysis in clinical trials.* The random-effects `τ²`
  estimator that section 1 approximates.
- Spiegelhalter, Abrams & Myles (2004), *Bayesian Approaches to Clinical Trials and Health-Care
  Evaluation.* The conjugate normal update in section 3.
- FDA, *Adaptive Designs for Clinical Trials of Drugs and Biologics* (2019). Pre-specification,
  Type I error control, and simulation-based justification.
</content>
