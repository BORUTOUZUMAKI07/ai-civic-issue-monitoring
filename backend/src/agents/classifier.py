from __future__ import annotations

import json
import logging
from typing import Any

from src.agents.state import AgentState
from src.core.config import settings
from src.core.llm import chat_completion_retryable

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


async def _openai_classify(text: str, rag_context: str = "") -> tuple[str, int, float] | None:
    """Use OpenAI to classify the issue. Returns (category, severity, confidence) or None on failure.

    ``rag_context`` is the rendered block of similar historical issues from the
    retrieval layer (see ``src/rag/context.py``). When present it is injected into
    the prompt so the model can lean on recurring local patterns; it never
    replaces the current report, which remains the primary signal.
    """
    if not settings.OPENAI_API_KEY:
        return None

    try:
        history_block = ""
        if rag_context:
            history_block = (
                "\nUse the following historical issues from this city as supporting "
                "evidence for recurring patterns. The current report is still the "
                "primary signal — do not let history override clear evidence in it.\n\n"
                f"{rag_context}\n"
            )

        prompt = f"""Classify this civic issue report into exactly one category and severity level.

Issue description: "{text}"
{history_block}
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

        # Shared client (connection pooling + timeout + SDK retries) wrapped in
        # a tenacity backoff for transient upstream failures; see src/core/llm.
        response = await chat_completion_retryable(
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

    Priority: OpenAI (optionally RAG-assisted) → keyword matching → default.

    When ``RAG_CLASSIFY_ENABLED`` is on and the intake gate preclassified the
    report with low confidence, the LLM is consulted *with* the retrieved
    historical context so it can refine the label. With the flag off (the
    default) a preclassified category is always trusted, exactly as before.
    """
    description = state.get("description", "")
    existing_category = state.get("category", "")
    rag_context = state.get("rag_context", "") if settings.RAG_CLASSIFY_ENABLED else ""
    try:
        category_confidence = float(state.get("category_confidence", 1.0) or 1.0)
    except (TypeError, ValueError):
        category_confidence = 1.0

    preclassified = bool(existing_category) and existing_category in LABEL_TO_SEVERITY
    # Re-consult the LLM only when there is no gate label, or when the gate was
    # unsure AND we actually have retrieved context to give it.
    consult_llm = not preclassified or (
        bool(rag_context) and category_confidence < settings.RAG_CLASSIFY_MIN_CONFIDENCE
    )

    if preclassified and not consult_llm:
        category = existing_category
        severity = LABEL_TO_SEVERITY[category]
        confidence = 0.8
        source = "preclassified"
    else:
        openai_result = await _openai_classify(description, rag_context)

        if openai_result:
            category, severity, confidence = openai_result
            source = "openai+rag" if rag_context else "openai"
        elif preclassified:
            # LLM unavailable/failed — keep the gate's label rather than guessing.
            category = existing_category
            severity = LABEL_TO_SEVERITY[category]
            confidence = 0.8
            source = "preclassified"
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
            "rag_context_used": bool(rag_context),
        },
        "messages": state.get("messages", []),
    }
