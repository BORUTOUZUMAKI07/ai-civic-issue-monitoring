from __future__ import annotations

from src.core.config import settings

CIVIC_LABELS = {"pothole", "garbage", "debris"}

# Keyword fallback keys MUST stay aligned with the DB's issuetype enum and the
# trained ML classes (pothole, garbage, debris). road-damage text folds into
# pothole (pavement damage class). Unrecognised civic text is routed by the
# gate to review_required rather than into a category that no longer exists.
CIVIC_KEYWORDS: dict[str, list[str]] = {
    "pothole": ["pothole", "road damage", "road crack", "broken road", "asphalt", "road repair", "road broken"],
    "garbage": ["garbage", "waste", "trash", "rubbish", "dump", "litter"],
    "debris": ["debris", "rubble", "construction waste"],
}


def classify_description(description: str) -> dict:
    """Keyword-based text classifier with civic-confidence score."""
    if not description:
        return {"label": "pothole", "confidence": 0.5, "civic_confidence": 0.0}

    desc_lower = description.lower()
    best_label = "pothole"
    best_score = 0
    total_score = 0

    for label, keywords in CIVIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in desc_lower)
        total_score += score
        if score > best_score:
            best_score = score
            best_label = label

    confidence = min(0.95, 0.6 + best_score * 0.1)
    civic_confidence = min(1.0, total_score * 0.25)

    return {
        "label": best_label,
        "confidence": confidence,
        "civic_confidence": civic_confidence,
    }


def gate_decision(vision: dict | None, description: str, force_submit: bool) -> dict:
    """Three-way intake gate.

    Returns:
        {"action": "accept", "issue_type": str, "confidence": float,
         "review_required": bool, "reason": str}
        {"action": "reject", "reason": str}
    """
    text = classify_description(description)

    if force_submit:
        issue_type = text["label"] if text["civic_confidence"] >= 0.25 else (vision["label"] if vision else "pothole")
        return {
            "action": "accept",
            "issue_type": issue_type,
            "confidence": text["confidence"],
            "review_required": True,
            "reason": "User submitted after rejection (force_submit)",
        }

    # Vision succeeded with a known civic class → accept directly
    if vision and vision["is_civic"]:
        review = vision["confidence"] < settings.REVIEW_THRESHOLD
        return {
            "action": "accept",
            "issue_type": vision["label"],
            "confidence": vision["confidence"],
            "review_required": review,
            "reason": "",
        }

    # Vision failed → fall back to text description
    if vision is None:
        return {
            "action": "accept",
            "issue_type": text["label"],
            "confidence": text["confidence"],
            "review_required": text["civic_confidence"] < 0.3,
            "reason": "" if text["civic_confidence"] >= 0.3 else "Vision unavailable, low-text signal",
        }

    # Vision says non_civic
    if vision["is_non_civic"]:
        high_conf_non_civic = vision["civic_prob"] >= settings.REJECT_THRESHOLD
        text_says_civic = text["civic_confidence"] >= 0.25

        if high_conf_non_civic and not text_says_civic:
            return {
                "action": "reject",
                "reason": "This image does not appear to be a civic issue.",
            }

        # Unsure or text hints civic → accept with review
        return {
            "action": "accept",
            "issue_type": text["label"],
            "confidence": min(vision["confidence"], text["confidence"]),
            "review_required": True,
            "reason": "Low-confidence prediction, routed to human review",
        }

    # Unknown label from model (future-proof)
    return {
        "action": "accept",
        "issue_type": text["label"],
        "confidence": text["confidence"],
        "review_required": True,
        "reason": "Unrecognised prediction, routed to human review",
    }
