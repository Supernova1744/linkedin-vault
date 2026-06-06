"""
Shared prompt construction and response parsing for all LLM providers.

Keeping prompt logic here means both ZAI and Ollama produce identical
instructions, so changes to the analysis schema only need to be made once.
"""

from __future__ import annotations

import json
import re

from linkedin_vault.enricher.base import EnrichmentResult

# ---------------------------------------------------------------------------
# System prompt (constant)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a content analyst for a knowledge management tool.\n"
    "Analyze LinkedIn posts and return structured JSON."
)

# ---------------------------------------------------------------------------
# Tag vocabulary
# ---------------------------------------------------------------------------

ALLOWED_TAGS: list[str] = [
    "AI",
    "LLM",
    "NLP",
    "Computer Vision",
    "Python",
    "JavaScript",
    "TypeScript",
    "Rust",
    "Go",
    "DevOps",
    "Cloud",
    "Data Science",
    "Machine Learning",
    "Security",
    "Career",
    "Productivity",
    "Open Source",
    "Research",
    "Tutorial",
    "Tool",
    "Framework",
    "Database",
    "API",
    "Architecture",
    "System Design",
    "Leadership",
    "Startup",
    "Product",
    "Other",
]

_RESPONSE_SCHEMA = """{
  "summary": "2-3 sentence summary of the post",
  "tags": ["tag1", "tag2"],
  "importance_score": 7.5,
  "is_outdated": false
}"""

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_enrichment_prompt(
    content: str,
    author_name: str,
    post_date: str | None,
    today: str,
) -> str:
    """Build the user message for enrichment.

    Args:
        content:     Full text of the LinkedIn post.
        author_name: Display name of the post author.
        post_date:   ISO-8601 date string, or None if unavailable.
        today:       Today's date as ISO-8601 (e.g. "2026-06-06").

    Returns:
        A prompt string ready to be sent as the ``user`` message.
    """
    post_date_str = post_date if post_date else "unknown"
    allowed_tags_str = ", ".join(ALLOWED_TAGS)
    return (
        "Analyze the following LinkedIn post and return ONLY valid JSON with no other text.\n\n"
        f"Post Author: {author_name}\n"
        f"Post Date: {post_date_str}\n"
        f"Today's Date: {today}\n\n"
        f"Post Content:\n{content}\n\n"
        f"Return JSON in exactly this format:\n{_RESPONSE_SCHEMA}\n\n"
        "Rules:\n"
        "- summary: 2-3 neutral, factual sentences describing the post content\n"
        f"- tags: 2-8 strings selected ONLY from: {allowed_tags_str}\n"
        "- importance_score: float 0.0-10.0 "
        "(0=spam/useless, 10=must-read landmark content)\n"
        "- is_outdated: true ONLY if the content is time-sensitive AND the post "
        f"date is more than 12 months before today ({today})\n\n"
        "Respond with ONLY the JSON object, no markdown, no explanation."
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """Strip markdown code fences and isolate the JSON object.

    Handles three common LLM response shapes:
    1. Plain JSON object
    2. ```json ... ``` fenced block
    3. Prose with embedded JSON (brace extraction fallback)
    """
    text = text.strip()

    # Try fenced block first (```json ... ``` or ``` ... ```)
    fenced = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()

    # Fallback: find outermost braces — handles trailing commentary
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def parse_enrichment_response(raw_json: str) -> EnrichmentResult:
    """Parse and validate the LLM JSON response into an :class:`EnrichmentResult`.

    Args:
        raw_json: Raw string from the LLM (may include fences or extra prose).

    Returns:
        An :class:`EnrichmentResult` with ``model_used`` set to ``""``; the
        calling provider is responsible for filling in ``model_used``.

    Raises:
        ValueError: if the JSON is malformed or any required field is missing.
    """
    cleaned = _extract_json(raw_json)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in LLM response: {exc}") from exc

    for field in ("summary", "tags", "importance_score", "is_outdated"):
        if field not in data:
            raise ValueError(f"Missing required field '{field}' in LLM response")

    summary = str(data["summary"])
    tags = [str(t) for t in data["tags"]]
    importance_score = max(0.0, min(10.0, float(data["importance_score"])))
    is_outdated = bool(data["is_outdated"])

    return EnrichmentResult(
        summary=summary,
        tags=tags,
        importance_score=importance_score,
        is_outdated=is_outdated,
        model_used="",  # Caller sets this after parsing
    )
