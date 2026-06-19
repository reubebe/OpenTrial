from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Centralized environment access and capability flags."""

    use_live_apis: bool = _get_bool("OPENTRIAL_USE_LIVE_APIS", False)
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    ncbi_email: str | None = os.getenv("NCBI_EMAIL") or None
    ncbi_api_key: str | None = os.getenv("NCBI_API_KEY") or None

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def pubmed_enabled(self) -> bool:
        return self.use_live_apis and bool(self.ncbi_email)

    @property
    def public_apis_enabled(self) -> bool:
        return self.use_live_apis


settings = Settings()
