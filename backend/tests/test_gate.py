from __future__ import annotations

import pytest

from src.core.gate import classify_description, gate_decision


class TestClassifyDescription:
    def test_empty_description(self) -> None:
        result = classify_description("")
        assert result["label"] == "pothole"
        assert result["confidence"] == 0.5
        assert result["civic_confidence"] == 0.0

    def test_pothole_keywords(self) -> None:
        result = classify_description("big pothole near bus stop")
        assert result["label"] == "pothole"
        assert result["confidence"] >= 0.7

    def test_garbage_keywords(self) -> None:
        result = classify_description("garbage pile near market")
        assert result["label"] == "garbage"

    def test_road_damage_text_maps_to_pothole(self) -> None:
        result = classify_description("road damage on the highway surface")
        assert result["label"] == "pothole"
        assert result["civic_confidence"] > 0.0

    def test_sure_civic_keywords_high_confidence(self) -> None:
        result = classify_description("huge pothole and road crack here")
        assert result["civic_confidence"] >= 0.25

    def test_unrelated_text_low_civic_confidence(self) -> None:
        result = classify_description("nice weather today")
        assert result["civic_confidence"] < 0.25


class TestGateDecision:
    def test_vision_civic_high_conf_accepted(self) -> None:
        vision = {
            "label": "pothole",
            "is_civic": True,
            "is_non_civic": False,
            "confidence": 0.92,
            "civic_prob": 0.92,
            "model": "mobilenet_v2",
            "probabilities": {},
        }
        result = gate_decision(vision, "pothole on main road", force_submit=False)
        assert result["action"] == "accept"
        assert result["issue_type"] == "pothole"
        assert result["review_required"] is False

    def test_vision_civic_low_conf_accepted_with_review(self) -> None:
        vision = {
            "label": "debris",
            "is_civic": True,
            "is_non_civic": False,
            "confidence": 0.45,
            "civic_prob": 0.45,
            "model": "mobilenet_v2",
            "probabilities": {},
        }
        result = gate_decision(vision, "", force_submit=False)
        assert result["action"] == "accept"
        assert result["review_required"] is True

    def test_vision_non_civic_high_conf_no_description_rejected(self) -> None:
        vision = {
            "label": "non_civic",
            "is_civic": False,
            "is_non_civic": True,
            "confidence": 0.95,
            "civic_prob": 0.95,
            "model": "mobilenet_v2",
            "probabilities": {"non_civic": 0.95},
        }
        result = gate_decision(vision, "", force_submit=False)
        assert result["action"] == "reject"
        assert "not appear to be a civic issue" in result["reason"]

    def test_vision_non_civic_high_conf_civic_text_accepted_with_review(self) -> None:
        vision = {
            "label": "non_civic",
            "is_civic": False,
            "is_non_civic": True,
            "confidence": 0.90,
            "civic_prob": 0.90,
            "model": "mobilenet_v2",
            "probabilities": {"non_civic": 0.90},
        }
        result = gate_decision(vision, "road damage on highway", force_submit=False)
        assert result["action"] == "accept"
        assert result["review_required"] is True

    def test_vision_non_civic_low_conf_accepted_with_review(self) -> None:
        vision = {
            "label": "non_civic",
            "is_civic": False,
            "is_non_civic": True,
            "confidence": 0.60,
            "civic_prob": 0.60,
            "model": "mobilenet_v2",
            "probabilities": {"non_civic": 0.60},
        }
        result = gate_decision(vision, "", force_submit=False)
        assert result["action"] == "accept"
        assert result["review_required"] is True

    def test_vision_unavailable_falls_back_to_text(self) -> None:
        result = gate_decision(None, "waterlogging on road", force_submit=False)
        assert result["action"] == "accept"
        assert result["issue_type"] == "pothole"

    def test_vision_unavailable_no_description_low_conf_review(self) -> None:
        result = gate_decision(None, "", force_submit=False)
        assert result["action"] == "accept"
        assert result["review_required"] is True

    def test_force_submit_bypasses_rejection(self) -> None:
        vision = {
            "label": "non_civic",
            "is_civic": False,
            "is_non_civic": True,
            "confidence": 0.99,
            "civic_prob": 0.99,
            "model": "mobilenet_v2",
            "probabilities": {"non_civic": 0.99},
        }
        result = gate_decision(vision, "", force_submit=True)
        assert result["action"] == "accept"
        assert result["review_required"] is True
        assert "User submitted" in result["reason"]
