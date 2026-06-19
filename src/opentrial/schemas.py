from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrialDesignInput:
    indication: str
    endpoint: str
    target_effect: float
    alpha: float
    desired_power: float
    max_n_per_arm: int
    endpoint_type: str = "continuous"


@dataclass(frozen=True)
class EvidenceRecord:
    source: str
    title: str
    effect: float
    standard_error: float
    n: int
    endpoint: str
    indication: str
    year: int
    url: str
    notes: str = ""


@dataclass(frozen=True)
class PriorSummary:
    mean: float
    sd: float
    effective_n: int
    records_used: int
    method: str


@dataclass(frozen=True)
class DesignPoint:
    n_per_arm: int
    power: float
    posterior_success_probability: float


@dataclass(frozen=True)
class IntegrationStatus:
    key: str
    name: str
    purpose: str
    connected: bool
