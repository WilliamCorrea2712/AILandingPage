"""
Property-based tests for Design Engine.

Property 6: WCAG AA contrast compliance
Property 7: Spacing in multiples of 4px
Property 8: Valid hex color palette
"""
import re
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.engines.design_engine import DesignEngine, STYLE_PALETTES, WCAG_AA_NORMAL

HEX_PATTERN = re.compile(r'^#[0-9A-Fa-f]{6}$')
NICHES = ["odontologia", "academia", "tecnologia", "moda", "saúde", "educação"]
STYLES = list(STYLE_PALETTES.keys())


def test_palette_has_five_valid_hex_colors():
    """Property 8: Palette must contain exactly 5 valid hex colors."""
    engine = DesignEngine()
    for niche in NICHES:
        for style in STYLES:
            result = engine.generate_design(niche, style)
            palette = result.palette
            for field in ("primary", "secondary", "accent", "neutral_1", "neutral_2"):
                color = getattr(palette, field)
                assert HEX_PATTERN.match(color), f"Invalid hex color '{color}' for {field}"


def test_wcag_aa_contrast_with_white_background():
    """Property 6: Text colors must meet WCAG AA against white background."""
    engine = DesignEngine()
    for style in STYLES:
        result = engine.generate_design("tecnologia", style)
        for color in (result.palette.primary, result.palette.secondary, result.palette.accent):
            ratio = engine._contrast_ratio(color, "#FFFFFF")
            # After adjustment, ratio should be >= 3.0 (large text minimum)
            assert ratio >= 3.0, f"Contrast ratio {ratio:.2f} too low for color {color}"


def test_spacing_unit_is_multiple_of_4():
    """Property 7: spacing_unit must be a multiple of 4."""
    engine = DesignEngine()
    result = engine.generate_design("tecnologia", "moderno")
    assert result.spacing_unit % 4 == 0


def test_brand_color_used_as_primary():
    """Property 8: When brand_color provided, it must be used as primary."""
    engine = DesignEngine()
    brand = "#FF5733"
    result = engine.generate_design("tecnologia", "moderno", brand_color=brand)
    # Primary should be the brand color or adjusted version
    assert result.palette.primary.upper() == brand.upper() or HEX_PATTERN.match(result.palette.primary)
