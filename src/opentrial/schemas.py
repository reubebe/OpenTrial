from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenModel(BaseModel):
    """Validated immutable model for normalized OpenTrial data."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class TrialDesignInput(FrozenModel):
    indication: str
    endpoint: str
    target_effect: float = Field(gt=0)
    alpha: float = Field(gt=0, lt=1)
    desired_power: float = Field(gt=0, lt=1)
    max_n_per_arm: int = Field(gt=0)
    # Bayesian success rule: declare success when the posterior probability that the
    # effect is positive exceeds this threshold. Mirrors the FDA CID guidance's
    # "decision criteria" (e.g. Pr(effect > 0) > 0.99) and I-SPY 2's graduation rule.
    # 0.975 is the Bayesian counterpart of a one-sided alpha of 0.025.
    decision_threshold: float = Field(default=0.975, gt=0.5, lt=1)
    # "continuous" -> target_effect is a mean difference (in endpoint units).
    # "binary"     -> target_effect is a risk difference between the two arms'
    #                 event proportions, anchored on baseline_proportion.
    endpoint_type: Literal["continuous", "binary"] = "continuous"
    # Population standard deviation of a CONTINUOUS endpoint, in the SAME units as
    # ``target_effect``. The power maths needs it to standardize the effect; a value
    # of 1.0 means target_effect is already a standardized effect size. For an
    # absolute endpoint (e.g. HbA1c %), set the real SD (HbA1c is typically ~1.0-1.2).
    endpoint_sd: float = Field(default=1.0, gt=0)
    # Control-arm event rate for a BINARY endpoint (ignored when continuous). The
    # treatment-arm rate is baseline_proportion + target_effect.
    baseline_proportion: float = Field(default=0.5, gt=0, lt=1)
    # Expected proportion of enrolled participants per arm lost before the analysis
    # (dropout / non-evaluable). The operating characteristics are computed on the
    # analyzable count n*(1 - dropout_rate), so a design's recommended N is the number to
    # ENROLL to retain power after attrition. 0.0 (the default) is the complete-follow-up
    # idealization; a typical trial plans for 0.10-0.20.
    dropout_rate: float = Field(default=0.0, ge=0, lt=1)

    @model_validator(mode="after")
    def binary_treatment_rate_is_possible(self) -> "TrialDesignInput":
        if self.endpoint_type == "binary":
            treatment_rate = self.baseline_proportion + self.target_effect
            if not 0 < treatment_rate < 1:
                raise ValueError(
                    "For binary endpoints, baseline_proportion + target_effect "
                    "must be between 0 and 1."
                )
        return self


class EvidenceRecord(FrozenModel):
    evidence_kind: Literal[
        "effect_estimate",
        "trial_precedent",
        "citation",
        "safety",
        "label",
        "target_biology",
        "pharmacogenomics",
        "web_context",
        "context",
    ] = "context"
    source: str
    title: str
    effect: float
    standard_error: float = Field(ge=0)
    n: int = Field(ge=0)
    endpoint: str
    indication: str
    year: int = Field(ge=1900)
    url: str
    notes: str = ""

    @field_validator("year")
    @classmethod
    def year_is_not_far_future(cls, value: int) -> int:
        max_year = date.today().year + 1
        if value > max_year:
            raise ValueError(f"year cannot be later than {max_year}")
        return value


class PriorSummary(FrozenModel):
    mean: float
    sd: float = Field(ge=0)
    # Provenance, NOT the prior's information content: the number of participants behind the
    # contributing records. Deliberately not called "effective N", which in Bayesian usage
    # means effective sample size (how many patients the prior is *worth*). For that, see
    # ``opentrial.compute.simulation.prior_equivalent_n_per_arm``.
    pooled_participants: int = Field(ge=0)
    records_used: int = Field(ge=0)
    # How many effect records were dropped as duplicate reports of a trial already counted
    # (see ``opentrial.compute.priors.deduplicate_trial_records``). 0 when none overlapped.
    records_merged: int = Field(default=0, ge=0)
    method: str


class DesignPoint(FrozenModel):
    n_per_arm: int = Field(gt=0)
    power: float = Field(ge=0, le=1)
    beta: float = Field(default=1.0, ge=0, le=1)
    type_i_error: float = Field(default=0.0, ge=0, le=1)
    assurance: float = Field(default=0.0, ge=0, le=1)


class PriorScenario(FrozenModel):
    """One prior in a sensitivity analysis, with its operating characteristics.

    The four labels follow the FDA Complex Innovative Trial Designs guidance's own
    vocabulary for constructing priors: an evidence-based prior, a ``skeptical`` prior
    (initial skepticism about large effects), a ``reference`` (weakly-informative) prior,
    and an ``enthusiastic`` prior. Reporting operating characteristics across all four is
    exactly the prior-sensitivity assessment that guidance recommends.
    """

    label: Literal["evidence", "skeptical", "reference", "enthusiastic"]
    description: str
    prior: PriorSummary
    n_per_arm: int = Field(gt=0)
    assurance: float = Field(ge=0, le=1)
    posterior_success_probability: float = Field(ge=0, le=1)
    predictive_probability_of_success: float = Field(ge=0, le=1)
    meets_decision_threshold: bool


class DecisionSummary(FrozenModel):
    """Bayesian decision-criterion readout at a chosen sample size."""

    n_per_arm: int = Field(gt=0)
    decision_threshold: float = Field(gt=0.5, lt=1)
    posterior_success_probability: float = Field(ge=0, le=1)
    predictive_probability_of_success: float = Field(ge=0, le=1)
    meets_decision_threshold: bool


class InterimLook(FrozenModel):
    """One planned interim analysis in a group-sequential design."""

    look: int = Field(gt=0)
    information_fraction: float = Field(gt=0, le=1)
    n_per_arm: int = Field(gt=0)
    efficacy_z: float
    cumulative_stop_prob_null: float = Field(ge=0, le=1)
    cumulative_stop_prob_alt: float = Field(ge=0, le=1)


class GroupSequentialResult(FrozenModel):
    """Operating characteristics of a group-sequential design, estimated by simulation.

    The efficacy boundaries are calibrated by simulation so the overall one-sided Type I
    error equals the nominal alpha, addressing the multiplicity inflation the FDA Adaptive
    Designs guidance warns about. Expected sample size under the alternative is the headline
    efficiency gain (the guidance cites roughly a 15% reduction for a single interim look
    with an O'Brien-Fleming boundary).
    """

    boundary: Literal["obrien-fleming", "pocock"]
    n_looks: int = Field(gt=0)
    n_max_per_arm: int = Field(gt=0)
    alpha: float = Field(gt=0, lt=1)
    type_i_error: float = Field(ge=0, le=1)
    power: float = Field(ge=0, le=1)
    expected_n_per_arm_alt: float = Field(ge=0)
    expected_n_per_arm_null: float = Field(ge=0)
    fixed_n_per_arm: int = Field(gt=0)
    expected_reduction_vs_fixed: float
    looks: list[InterimLook]


class SourceOutcome(FrozenModel):
    name: str
    status: Literal["ok", "empty", "failed"]
    n_records: int = Field(ge=0)
    message: str = ""


class IntegrationStatus(FrozenModel):
    key: str
    name: str
    purpose: str
    connected: bool
    status: str = ""
    # The transport and API behind this source, e.g. "urllib | NCBI E-utilities".
    # Named for transparency; OpenTrial talks to every source with the standard
    # library only, so there is no heavy third-party SDK to hide.
    sdk: str = ""
