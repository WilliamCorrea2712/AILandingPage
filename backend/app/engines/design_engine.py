"""
Design Engine — generates color palettes, typography and spacing.

Requirements: 5.1–5.5
"""
from __future__ import annotations

import colorsys
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STYLE_PALETTES: dict[str, dict] = {
    "minimalista": {"primary": "#2D3748", "secondary": "#718096", "accent": "#4299E1",
                    "neutral_1": "#F7FAFC", "neutral_2": "#EDF2F7"},
    "corporativo":  {"primary": "#1A365D", "secondary": "#2B6CB0", "accent": "#ED8936",
                    "neutral_1": "#F7FAFC", "neutral_2": "#E2E8F0"},
    "moderno":      {"primary": "#084753 ", "secondary": "#6B46C1", "accent": "#F6AD55",
                    "neutral_1": "#FAF5FF", "neutral_2": "#E9D8FD"},
    "agressivo":    {"primary": "#C53030", "secondary": "#E53E3E", "accent": "#F6E05E",
                    "neutral_1": "#FFF5F5", "neutral_2": "#FED7D7"},
}

STYLE_FONTS: dict[str, tuple[str, str]] = {
    "minimalista": ("Inter", "Inter"),
    "corporativo":  ("Merriweather", "Open Sans"),
    "moderno":      ("Poppins", "Lato"),
    "agressivo":    ("Oswald", "Roboto"),
}

WCAG_AA_NORMAL = 4.5
WCAG_AA_LARGE = 3.0


@dataclass
class ColorPalette:
    primary: str
    secondary: str
    accent: str
    neutral_1: str
    neutral_2: str


@dataclass
class Typography:
    heading_font: str
    body_font: str


@dataclass
class DesignResult:
    palette: ColorPalette
    typography: Typography
    spacing_unit: int = 4  # multiples of 4px


class DesignEngine:
    def generate_design(
        self,
        niche: str,
        style: str,
        brand_color: str | None = None,
    ) -> DesignResult:
        style = style if style in STYLE_PALETTES else "moderno"
        palette_data = dict(STYLE_PALETTES[style])

        if brand_color:
            palette_data["primary"] = brand_color
            # Derive secondary and accent via analogous harmony
            palette_data["secondary"] = self._rotate_hue(brand_color, 30)
            palette_data["accent"] = self._rotate_hue(brand_color, -60)
            # Ensure WCAG AA contrast with white background
            for key in ("primary", "secondary", "accent"):
                if not self._check_wcag(palette_data[key], "#FFFFFF", 16):
                    adjusted = self._adjust_luminance(palette_data[key])
                    logger.info("Adjusted %s from %s to %s for WCAG AA.", key, palette_data[key], adjusted)
                    palette_data[key] = adjusted

        palette = ColorPalette(**palette_data)
        heading_font, body_font = STYLE_FONTS.get(style, ("Inter", "Inter"))
        typography = Typography(heading_font=heading_font, body_font=body_font)

        return DesignResult(palette=palette, typography=typography, spacing_unit=4)

    # ---- Color utilities ----

    def _hex_to_rgb(self, hex_color: str) -> tuple[float, float, float]:
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return r / 255, g / 255, b / 255

    def _rgb_to_hex(self, r: float, g: float, b: float) -> str:
        return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))

    def _rotate_hue(self, hex_color: str, degrees: float) -> str:
        r, g, b = self._hex_to_rgb(hex_color)
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        h = (h + degrees / 360) % 1.0
        r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
        return self._rgb_to_hex(r2, g2, b2)

    def _relative_luminance(self, hex_color: str) -> float:
        def linearize(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = self._hex_to_rgb(hex_color)
        return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)

    def _contrast_ratio(self, c1: str, c2: str) -> float:
        l1 = self._relative_luminance(c1)
        l2 = self._relative_luminance(c2)
        lighter, darker = max(l1, l2), min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def _check_wcag(self, text_color: str, bg_color: str, font_size_pt: float) -> bool:
        ratio = self._contrast_ratio(text_color, bg_color)
        threshold = WCAG_AA_LARGE if font_size_pt >= 18 else WCAG_AA_NORMAL
        return ratio >= threshold

    def _adjust_luminance(self, hex_color: str) -> str:
        """Darken the color until it meets WCAG AA against white."""
        r, g, b = self._hex_to_rgb(hex_color)
        h, s, v = colorsys.rgb_to_hsv(r, g, b)
        for step in range(20):
            v = max(0.0, v - 0.05)
            r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
            candidate = self._rgb_to_hex(r2, g2, b2)
            if self._check_wcag(candidate, "#FFFFFF", 16):
                return candidate
        return hex_color  # fallback: return original if adjustment fails

    def check_wcag_contrast(self, text_color: str, bg_color: str, font_size_pt: float) -> bool:
        return self._check_wcag(text_color, bg_color, font_size_pt)

    def validate_spacing(self, css: str) -> bool:
        """Return True if all spacing values in CSS are multiples of 4px."""
        values = re.findall(r'(\d+)px', css)
        return all(int(v) % 4 == 0 for v in values)
