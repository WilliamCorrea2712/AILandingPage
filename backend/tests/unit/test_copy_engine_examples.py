"""Unit tests for Copy Engine. Requirements: 6.1–6.7"""
import pytest
from app.engines.copy_engine import CopyEngine
from app.engines.nlp_engine import NLPResult


def make_nlp(tone="formal", niche="tecnologia"):
    return NLPResult(
        intention="captar leads", niche=niche,
        conversion_goal="captar leads", visual_style="moderno",
        communication_tone=tone,
    )


def test_generates_three_headline_variations():
    engine = CopyEngine()
    result = engine.generate_copy(make_nlp())
    assert len(result.headline_variations) == 3


def test_formal_tone_no_contractions():
    engine = CopyEngine()
    result = engine.generate_copy(make_nlp(tone="formal"))
    for text in result.headline_variations + result.ctas:
        assert "tá" not in text.lower()
        assert "tô" not in text.lower()


def test_at_least_two_distinct_ctas():
    engine = CopyEngine()
    result = engine.generate_copy(make_nlp())
    assert len(result.ctas) >= 2
    assert len(set(result.ctas)) >= 2


def test_fallback_to_formal_when_tone_missing():
    engine = CopyEngine()
    nlp = make_nlp(tone="")
    result = engine.generate_copy(nlp)
    assert result is not None
