"""
Property-based tests for Copy Engine.

Property 9: SEO metadata length
Property 10: Text uniqueness across sections
"""
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.engines.copy_engine import CopyEngine, check_text_uniqueness
from app.engines.nlp_engine import NLPResult


def make_nlp_result(niche="tecnologia", tone="formal"):
    return NLPResult(
        intention="captar leads",
        niche=niche,
        conversion_goal="captar leads",
        visual_style="moderno",
        communication_tone=tone,
    )


def test_seo_meta_title_length():
    """Property 9: meta_title must be 50–60 chars."""
    engine = CopyEngine()
    for niche in ["odontologia", "academia", "tecnologia", "moda", "saúde"]:
        result = engine.generate_copy(make_nlp_result(niche=niche))
        assert 50 <= len(result.seo_meta.title) <= 60, (
            f"meta_title length {len(result.seo_meta.title)} out of range for niche '{niche}'"
        )


def test_seo_meta_description_length():
    """Property 9: meta_description must be 150–160 chars."""
    engine = CopyEngine()
    for niche in ["odontologia", "academia", "tecnologia", "moda", "saúde"]:
        result = engine.generate_copy(make_nlp_result(niche=niche))
        assert 150 <= len(result.seo_meta.description) <= 160, (
            f"meta_description length {len(result.seo_meta.description)} out of range for niche '{niche}'"
        )


def test_text_uniqueness_no_duplicates():
    """Property 10: No 10+ word sequence repeated across sections."""
    sections = [
        "Transforme seu negócio com soluções inovadoras e resultados comprovados",
        "Descubra como podemos ajudar você a crescer com qualidade e confiança",
        "Entre em contato e solicite uma proposta personalizada para sua empresa",
    ]
    assert check_text_uniqueness(sections) is True


def test_text_uniqueness_detects_duplicates():
    """Property 10: Duplicate sequences must be detected."""
    repeated = "esta é uma sequência de dez palavras que se repete exatamente igual aqui"
    sections = [repeated, repeated]
    assert check_text_uniqueness(sections) is False
