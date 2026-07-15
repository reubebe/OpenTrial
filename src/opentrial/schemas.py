from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # Population standard deviation of the (continuous) endpoint, in the SAME units as
    # ``target_effect``. The power maths needs it to standardize the effect; a value
    # of 1.0 means target_effect is already a standardized effect size. For an
    # absolute endpoint (e.g. HbA1c %), set the real SD (HbA1c is typically ~1.0-1.2).
    endpoint_sd: float = Field(default=1.0, gt=0)
    # Effect the posterior must exceed for "success", in the same units as ``target_effect``.
    # The default of 0 asks Pr(effect > 0), i.e. "is it better than control at all?" -- a
    # question that saturates near 1.0 whenever the prior and target both sit well above
    # zero, and so cannot discriminate between sample sizes. Set it to the minimum clinically
    # important difference to ask the question that actually decides a trial.
    success_threshold: float = Field(default=0.0, ge=0)


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
    method: str


class DesignPoint(FrozenModel):
    n_per_arm: int = Field(gt=0)
    power: float = Field(ge=0, le=1)
    beta: float = Field(default=1.0, ge=0, le=1)
    type_i_error: float = Field(default=0.0, ge=0, le=1)
    assurance: float = Field(default=0.0, ge=0, le=1)


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
