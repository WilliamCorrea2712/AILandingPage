"""
Property-based tests for NLP Engine.

Property 1: Prompt length validation
Property 2: Completeness of extracted attributes
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.engines.nlp_engine import INTENTIONS, TONES, VISUAL_STYLES, NLPEngine
from app.exceptions import PromptTooLongError, PromptTooShortError


@given(st.text(min_size=0, max_size=9))
def test_prompt_too_short_raises_error(prompt):
    """Property 1: Any prompt < 10 chars must raise PromptTooShortError."""
    engine = NLPEngine()
    with pytest.raises(PromptTooShortError):
        engine.extract_attributes(prompt)


@given(st.text(min_size=2001))
def test_prompt_too_long_raises_error(prompt):
    """Property 1: Any prompt > 2000 chars must raise PromptTooLongError."""
    engine = NLPEngine()
    with pytest.raises(PromptTooLongError):
        engine.extract_attributes(prompt)
