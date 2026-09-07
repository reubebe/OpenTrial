# OpenTrial

[![CABS: ds4cabs](https://img.shields.io/badge/CABS-ds4cabs-1f4b99?logo=github)](https://github.com/ds4cabs)
[![GitHub Pages: live](https://img.shields.io/badge/GitHub_Pages-live-brightgreen?logo=github)](https://ds4cabs.github.io/OpenTrial/)
![CABS: 2026](https://img.shields.io/badge/CABS-2026-6f42c1)
![status: active](https://img.shields.io/badge/status-active-2ea44f)
![type: Computation Engine](https://img.shields.io/badge/type-Computation_Engine-1f6feb)
![domain: Bayesian Trial Design](https://img.shields.io/badge/domain-Bayesian_Trial_Design-0aa)

**Intern:** Reuben N Addison
**Project Type:** Computation Engine

## What it is
OpenTrial is a Bayesian trial-design report engine. You describe a two-arm trial; it returns a
reproducible report whose **prior is traceable to cited evidence** and whose **operating
characteristics** (power, and a simulated Type I error) are the part a statistician can actually
check. It began as a single-path proof of concept and now covers continuous and binary
endpoints, prior sensitivity, a Bayesian decision criterion, and group-sequential designs. It
remains a learning-oriented engine, not a validated clinical tool.

![OpenTrial's view: a trial-design form with the core and extended evidence sources](docs/images/app_screenshot.png)

*The core demonstrated path: a continuous two-arm design and the operating-characteristics
route, input to cited prior to power/Type-I to downloadable report. The sections below cover
the capabilities built on top of it.*

## The core path, end to end
The project is anchored on a single, end-to-end path, a two-arm trial on a continuous endpoint,
demonstrated with seeded **Type 2 Diabetes / HbA1c** evidence:

1. **Trial inputs**: indication, endpoint, target effect, endpoint SD, alpha, desired power, max N.
2. **Evidence-derived prior with provenance**: every contributing record is listed with its
   source and link; only records with a real standard error move the prior.
3. **Operating characteristics**: a sample-size grid with power, beta, an alpha/Type-I
   reference, and prior-predictive assurance; plus an optional Monte-Carlo pass that reports an
   **empirical Type I error** as a calibration check.
4. **Downloadable report**: Markdown (for people) and JSON (for a reproducible record).

> **Why this is the story.** For a Bayesian/adaptive design, the most scrutinized output is
> Type I error / power under the design, justified by simulation, with the priors traceable to
> their sources. OpenTrial's report leads with exactly that; see *Operating characteristics &
> provenance* below. This maps to the FDA expectations for adaptive designs (pre-specification,
> Type I error control, simulation-based justification).

## Beyond the core path (now implemented)
The capabilities first sketched as future work are built and tested on top of the core path:

- **Binary endpoints**: a two-proportion (risk-difference) design alongside the continuous one,
  anchored on a baseline event rate.
- **Prior sensitivity analysis**: evidence, skeptical, reference, and enthusiastic priors run
  side by side, reporting how assurance and the decision move with the prior.
- **Bayesian decision criterion**: posterior Pr(effect > 0) against a decision threshold, plus a
  predictive probability of success.
- **Group-sequential designs**: O'Brien-Fleming and Pocock boundaries, calibrated by simulation
  so the overall Type I error holds at the nominal alpha, with the expected-sample-size saving
  reported.
- **Wider evidence sources**: Open Targets, PharmGKB, Semantic Scholar, and You.com, on top of
  the core four.
- **PDF report**: a self-contained PDF export (the `[pdf]` extra) beside Markdown and JSON, plus
  operating-characteristic charts.

An optional PyMC random-effects prior is available as the `[bayes]` extra; the default math
stays standard-library only, and the engine degrades gracefully when an extra is absent.

## Quickstart
```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
python3 -m pip install -e ".[dev]"     # install OpenTrial + test tools
python3 -m pytest                       # offline suite, no network/keys needed
streamlit run app.py                    # opens in your browser
```
With no configuration it runs **fully offline** on the seeded T2D / HbA1c demo; the complete
core path works on day one. To pull live evidence, copy `.env.example` to `.env`, set
`OPENTRIAL_USE_LIVE_APIS=true`, and add any optional keys (see **Configuration**).

## How to use it
1. Fill in the trial-design form (indication, endpoint, target effect, endpoint SD, alpha,
   desired power, max N per arm).
2. Leave **Evidence sources** on the seeded demo (default) or tick live sources.
3. Click **Generate design report**.
4. Read the prior summary, the operating-characteristic curves, and the provenance table;
   download the report as Markdown or JSON.

## Operating characteristics & provenance (the part to scrutinize)
This is the heart of the PoC and the thing reviewers should look at first. Every formula
below is written out, with its assumptions and known limitations, in **[docs/METHODS.md](docs/METHODS.md)**.

- **Power / beta / assurance.** The report's operating-characteristics table walks sample size
  upward and shows, at each N: power at the target effect, beta (Type II error), an alpha /
  Type-I-error reference, and prior-predictive **assurance** (success averaged over the prior).
- **Simulated Type I error.** Tick *Monte Carlo operating characteristics* to estimate power,
  assurance, and the **empirical Type I error** by simulation. For this design the empirical
  Type I should land on the nominal alpha, a visible calibration check, not a number you are
  asked to trust. (`src/opentrial/compute/mc.py`, standard-library only.)
- **Prior provenance.** Every evidence record that informs the prior is listed with its source,
  year, linked title, effect, and standard error. Records without a usable effect (registry
  rows, safety counts, labels) are shown for provenance but **excluded from the prior**, the
  central honesty rule.

## Evidence sources
The core four carry the demonstrated path:

- **ClinicalTrials.gov** (v2 studies API): US trial precedent.
- **PubMed** (NCBI E-utilities): published effect estimates, with a cautious effect + 95% CI extractor.
- **openFDA FAERS**: post-market safety-signal context.
- **DailyMed**: structured label provenance (dosing / adverse events).

Four further sources add translational and literature context:

- **Open Targets**: disease-target biology associations.
- **PharmGKB**: drug-gene clinical annotation and pharmacogenomics context.
- **Semantic Scholar**: academic citation enrichment and related literature.
- **You.com**: broad web context for exploratory provenance.

Live sources are off by default; the seeded demo needs none of them.

## Configuration (`.env`)
| Variable | Enables | Required? |
| --- | --- | --- |
| `OPENTRIAL_USE_LIVE_APIS` | the live public sources (CT.gov, PubMed, openFDA, DailyMed, …) | Off by default |
| `NCBI_EMAIL`, `NCBI_API_KEY` | PubMed etiquette / higher rate limits | Optional |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar higher rate limits | Optional |
| `YOU_API_KEY` | You.com web-context source | Optional |
| `GEMINI_API_KEY` | optional AI narrative synthesis | Optional |
| `OPENTRIAL_DEBUG` | verbose logging + exception detail in warnings | Off by default |
| `OPENTRIAL_HTTP_RETRIES` | retries for transient API errors (429/5xx/timeout) | Default 2 |

## Tech Stack
Python 3.11+: **standard library for the default math** (`statistics`, `math`, `urllib`,
`xml`, `re`), **Pydantic** for validated domain models, **Streamlit** for the UI. The
statistics are deterministic by default; Gemini, when used, is called over its REST API for
narrative only and never changes the numbers.

---

## Future work
The remaining roadmap, now that binary endpoints, prior sensitivity, the decision criterion,
group-sequential designs, the wider sources, and PDF export are built:
- **Count endpoints**: a beta-binomial design alongside the continuous and binary ones.
- **Audit mode**: benchmark an existing NCT/PMID trial against the recommendation.
- **Richer diagnostics**: expanded plots and reporting.
- Before any real-world use, a statistician's review and formal validation.

## Notes
This is a learning-oriented engine, not a validated clinical tool. The report's own
Notes section states the model's assumptions; the math is a transparent approximation by
design, with simulation available to check it.
