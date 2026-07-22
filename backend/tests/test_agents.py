from __future__ import annotations

from src.agents.classifier import _keyword_classify


def test_classify_pothole() -> None:
    category, _, _ = _keyword_classify("There is a large pothole on the main road")
    assert category == "pothole"


def test_classify_garbage() -> None:
    category, _, _ = _keyword_classify("Garbage is overflowing from the bin near the park")
    assert category == "garbage"


def test_classify_broken_streetlight() -> None:
    category, _, _ = _keyword_classify("Street light is not working on MG Road")
    assert category == "broken_streetlight"


def test_classify_waterlogging() -> None:
    category, _, _ = _keyword_classify("Waterlogging after heavy rain in the area")
    assert category == "waterlogging"


def test_classify_sewage() -> None:
    category, _, _ = _keyword_classify("Sewage overflowing from the drain near school")
    assert category == "sewage"


def test_classify_default() -> None:
    category, _, _ = _keyword_classify("Something random happened")
    assert category == "pothole"


def test_severity_high() -> None:
    _, severity, _ = _keyword_classify("Dangerous pothole causing accidents")
    assert severity == 4


def test_severity_medium() -> None:
    _, severity, _ = _keyword_classify("Broken streetlight near the school")
    assert severity == 3


def test_severity_low() -> None:
    _, severity, _ = _keyword_classify("Minor cosmetic issue with the road")
    assert severity == 1


def test_severity_default() -> None:
    _, severity, _ = _keyword_classify("Something needs attention")
    assert severity == 1
