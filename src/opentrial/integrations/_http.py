"""Shared HTTP helper: open a URL with bounded retry on transient failures.

Every adapter calls one external service and wraps its own typed error. The flaky part
in practice is *transient* failure -- rate limits (HTTP 429) and brief 5xx/timeout
blips -- which a short exponential backoff usually rides out. This helper centralizes that
retry without changing how adapters are tested: it calls the ``opener`` (each module's own
``urlopen``) that the tests already monkeypatch, so a mocked response still short-circuits on
the first attempt.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.error import HTTPError, URLError

from opentrial.config import logger, settings

# Status codes worth retrying: rate limiting and transient server errors.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code in _RETRYABLE_STATUS
    return isinstance(exc, (URLError, TimeoutError))


def read_url(
    opener: Any,
    target: Any,
    timeout: float,
    retries: int | None = None,
    backoff: float = 0.5,
) -> bytes:
    """Open ``target`` with ``opener`` (a ``urlopen``-like callable) and return the body.

    Retries transient errors (429, 5xx, timeouts) up to ``retries`` times with exponential
    backoff, then re-raises the last exception. Non-retryable errors (e.g. 404) raise at
    once. ``opener`` is passed in -- not imported -- so each adapter keeps its own
    monkeypatchable ``urlopen``.
    """

    attempts = settings.http_retries if retries is None else retries
    last_exc: Exception | None = None
    for attempt in range(attempts + 1):
        try:
            with opener(target, timeout=timeout) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt >= attempts or not _is_retryable(exc):
                raise
            label = target if isinstance(target, str) else getattr(target, "full_url", target)
            logger.warning(
                "Transient error from %s (%s); retry %d/%d", label, exc, attempt + 1, attempts
            )
            time.sleep(backoff * (2**attempt))
    if last_exc is not None:  # pragma: no cover - loop always returns or raises above
        raise last_exc
    raise RuntimeError("read_url exhausted retries without an exception")  # pragma: no cover
