from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict


def _load_dotenv(path: Path | None = None) -> None:
    env_path = path or Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _get_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


_load_dotenv()


class Settings(BaseModel):
    """Centralized environment access and capability flags."""

    model_config = ConfigDict(frozen=True)

    use_live_apis: bool = _get_bool("OPENTRIAL_USE_LIVE_APIS", False)
    debug: bool = _get_bool("OPENTRIAL_DEBUG", False)
    http_retries: int = int(os.getenv("OPENTRIAL_HTTP_RETRIES", "2"))
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    ncbi_email: str | None = os.getenv("NCBI_EMAIL") or None
    ncbi_api_key: str | None = os.getenv("NCBI_API_KEY") or None

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def pubmed_enabled(self) -> bool:
        return self.use_live_apis

    @property
    def public_apis_enabled(self) -> bool:
        return self.use_live_apis


settings = Settings()


def configure_logging() -> logging.Logger:
    """Configure and return the shared ``opentrial`` logger.

    Level follows the OPENTRIAL_DEBUG flag (DEBUG when on, INFO otherwise). Safe to
    call repeatedly -- it only attaches a handler once.
    """

    logger = logging.getLogger("opentrial")
    logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.propagate = False
    return logger


logger = configure_logging()
