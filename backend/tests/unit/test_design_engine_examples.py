"""Unit tests for Design Engine. Requirements: 5.1–5.5"""
import re
import pytest
from app.engines.design_engine import DesignEngine

HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')


def test_palette_has_five_colors():
    engine = DesignEngine()
    result = engine.generate_design("tecnologia", "moderno")
    p = result.palette
    for color in (p.primary, p.secondary, p.accent, p.neutral_1, p.neutral_2):
        assert HEX.match(color), f"Invalid hex: {color}"


def test_typography_has_two_fonts():
    engine = DesignEngine()
    result = engine.generate_design("tecnologia", "corporativo")
    assert result.typography.heading_font
    assert result.typography.body_font


def test_spacing_unit_multiple_of_4():
    engine = DesignEngine()
    result = engine.generate_design("tecnologia", "moderno")
    assert result.spacing_unit % 4 == 0


def test_wcag_check_passes_for_dark_on_white():
    engine = DesignEngine()
    assert engine.check_wcag_contrast("#000000", "#FFFFFF", 16) is True


def test_wcag_check_fails_for_light_on_white():
    engine = DesignEngine()
    assert engine.check_wcag_contrast("#EEEEEE", "#FFFFFF", 16) is False
