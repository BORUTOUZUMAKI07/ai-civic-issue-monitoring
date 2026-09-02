from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.state import AgentState
from src.core.config import settings

logger = logging.getLogger(__name__)

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "pothole": [
        "pothole",
        "road damage",
        "road crack",
        "broken road",
        "road repair",
        "asphalt",
        "road surface",
        "tarmac",
    ],
    "garbage": ["garbage", "waste", "trash", "rubbish", "dump", "litter", "overflowing bin", "waste collection"],
    "debris": ["debris", "illegal construction", "encroach", "illegal structure", "rubble", "construction waste"],
}

SEVERITY_KEYWORDS: dict[str, list[str]] = {
    "high": ["dangerous", "emergency", "accident", "injury", "hazard", "severe", "collapsed", "urgent", "risk"],
    "medium": ["broken", "damaged", "blocking", "obstruction", "overflow", "crack", "deteriorating"],
    "low": ["minor", "small", "cosmetic", "aesthetic", "slight", "wear"],
}

LABEL_TO_SEVERITY: dict[str, int] = {
    "pothole": 4,
    "garbage": 3,
    "debris": 5,
}


def _keyword_classify(text: str) -> tuple[str, int, float]:
    """Rule-based keyword classification. Returns (category, severity, confidence)."""
    text_lower = text.lower()

    scores: dict[str, int] = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        scores[cat] = sum(1 for kw in keywords if kw in text_lower)

    if max(scores.values()) == 0:
        category = "pothole"
    else:
        category = max(scores, key=scores.get)  # type: ignore[arg-type]

    severity = 1
    for level in ("high", "medium", "low"):
        if any(kw in text_lower for kw in SEVERITY_KEYWORDS[level]):
            severity = {"high": 4, "medium": 3, "low": 1}[level]
            break

    keyword_hits = scores.get(category, 0)
    confidence = min(0.95, 0.5 + keyword_hits * 0.1) if keyword_hits > 0 else 0.4

    return category, severity, confidence


async def _openai_classify(text: str) -> tuple[str, int, float] | None:
    """Use OpenAI to classify the issue. Returns (category, severity, confidence) or None on failure."""
    if not settings.OPENAI_API_KEY:
        return None

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        prompt = f"""Classify this civic issue report into exactly one category and severity level.

Issue description: "{text}"

Categories (choose exactly one):
- pothole: road potholes, road damage, broken asphalt
- garbage: waste, trash, litter, overflowing bins
- debris: construction debris, illegal structures, rubble

Severity (1-5):
1 = minor/cosmetic issue
2 = needs attention, not urgent
3 = moderate, causing inconvenience
4 = serious, needs prompt attention
5 = critical/emergency, public safety risk

Respond with ONLY a JSON object:
{{"category": "<category>", "severity": <1-5>, "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}"""

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or ""
        data = json.loads(content)

        category = data.get("category", "pothole")
        if category not in LABEL_TO_SEVERITY:
            category = "pothole"

        severity = int(data.get("severity", 3))
        severity = max(1, min(5, severity))

        confidence = float(data.get("confidence", 0.7))
        confidence = max(0.1, min(0.99, confidence))

        logger.info(
            "OpenAI classification: category=%s, severity=%d, confidence=%.2f",
            category,
            severity,
            confidence,
        )
        return category, severity, confidence

    except Exception as e:
        logger.warning("OpenAI classification failed, falling back to keywords: %s", e)
        return None


async def classify_issue(state: AgentState) -> dict[str, Any]:
    """Classify issue using OpenAI with keyword fallback.

    Priority: OpenAI → keyword matching → default.
    """
    description = state.get("description", "")
    existing_category = state.get("category", "")

    if existing_category and existing_category in LABEL_TO_SEVERITY:
        category = existing_category
        severity = LABEL_TO_SEVERITY[category]
        confidence = 0.8
        source = "preclassified"
    else:
        openai_result = await _openai_classify(description)

        if openai_result:
            category, severity, confidence = openai_result
            source = "openai"
        else:
            category, severity, confidence = _keyword_classify(description)
            source = "keyword"

    logger.info(
        "Classified issue %s via %s: category=%s, severity=%d, confidence=%.2f",
        state.get("issue_id"),
        source,
        category,
        severity,
        confidence,
    )

    return {
        "category": category,
        "severity": str(severity),
        "result": {
            "classification_source": source,
            "category": category,
            "severity": severity,
            "confidence": round(confidence, 3),
        },
        "messages": state.get("messages", []),
    }
