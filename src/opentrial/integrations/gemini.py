from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from opentrial.config import settings
from opentrial.integrations._http import read_url
from opentrial.schemas import EvidenceRecord, PriorSummary, TrialDesignInput

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_GENERATE_CONTENT_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)


class GeminiError(RuntimeError):
    """Raised when Gemini cannot return usable report narrative."""


def generate_report_narrative(
    design: TrialDesignInput,
    evidence: list[EvidenceRecord],
    prior: PriorSummary,
    timeout: float = 20.0,
) -> str:
    if not settings.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY is not configured.")

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": (
                        "You write concise Bayesian clinical-trial design summaries. "
                        "Use only the structured evidence provided. Do not invent "
                        "citations, effect sizes, or regulatory claims."
                    )
                }
            ]
        },
        "contents": [{"parts": [{"text": _build_prompt(design, evidence, prior)}]}],
        "generationConfig": {"temperature": 0.2},
    }
    request = Request(
        GEMINI_GENERATE_CONTENT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": settings.gemini_api_key,
        },
        method="POST",
    )

    try:
        data = json.loads(read_url(urlopen, request, timeout=timeout).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeminiError(f"Gemini request failed: {exc}") from exc

    text = _extract_output_text(data)
    if not text:
        raise GeminiError("Gemini response did not include output text.")
    return text.strip()


def _build_prompt(
    design: TrialDesignInput,
    evidence: list[EvidenceRecord],
    prior: PriorSummary,
) -> str:
    usable_records = [record for record in evidence if record.standard_error > 0]
    context_records = [record for record in evidence if record.standard_error <= 0]
    evidence_lines = [
        (
            f"- {record.source} ({record.year}): {record.title}; "
            f"effect={record.effect:.3f}, SE={record.standard_error:.3f}, n={record.n}"
        )
        for record in usable_records[:8]
    ]
    context_lines = [
        f"- {record.source} ({record.year}): {record.title}; notes={record.notes}"
        for record in context_records[:10]
    ]

    return "\n".join(
        [
            "Create a markdown section titled 'AI Narrative Synthesis'.",
            "Keep it to 3 short paragraphs plus up to 3 bullets.",
            "Mention limitations when evidence records are provenance-only.",
            "",
            "Design:",
            f"- Indication: {design.indication}",
            f"- Endpoint: {design.endpoint}",
            f"- Target effect: {design.target_effect:.3f}",
            f"- Alpha: {design.alpha:.3f}",
            f"- Desired power: {design.desired_power:.3f}",
            "",
            "Prior:",
            f"- Method: {prior.method}",
            f"- Mean: {prior.mean:.3f}",
            f"- SD: {prior.sd:.3f}",
            f"- Records used: {prior.records_used}",
            "",
            "Prior evidence:",
            *(evidence_lines or ["- None"]),
            "",
            "Context/provenance records:",
            *(context_lines or ["- None"]),
        ]
    )


def _extract_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]

    candidate_text: list[str] = []
    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                candidate_text.append(part["text"])
    if candidate_text:
        return "\n".join(candidate_text)

    text_parts: list[str] = []
    for step in data.get("steps", []):
        for part in step.get("content", []):
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text", "")))
    return "\n".join(part for part in text_parts if part)
