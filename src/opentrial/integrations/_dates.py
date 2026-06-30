from __future__ import annotations

from datetime import date


def safe_year(value: object, fallback: int | None = None) -> int:
    """Return a year inside EvidenceRecord's valid range, or a safe fallback.

    External APIs occasionally report a missing, malformed, or out-of-range year:
    a 19th-century reference from Semantic Scholar, or a parsing artefact such as
    ``"0019"`` from a garbled ClinicalTrials.gov date. Such a value would fail
    ``EvidenceRecord`` validation (which requires ``1900 <= year <= this year + 1``)
    and crash record construction. Clamping it to a fallback keeps the record's
    other provenance intact instead of dropping the whole source.
    """

    this_year = date.today().year
    fb = fallback if fallback is not None else this_year
    try:
        year = int(str(value)[:4])
    except (TypeError, ValueError):
        return fb
    if 1900 <= year <= this_year + 1:
        return year
    return fb
