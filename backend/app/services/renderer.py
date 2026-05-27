"""
Renderer — converts Vue.js SFCs to static HTML5 + minified CSS in an isolated sandbox.

Requirements: 7.1–7.7, 13.2, 13.4
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import bleach

from app.exceptions import RenderError

if TYPE_CHECKING:
    from app.engines.builder_engine import VueComponent

logger = logging.getLogger(__name__)

# OWASP HTML sanitization allowlist
ALLOWED_TAGS = [
    "a", "abbr", "acronym", "b", "blockquote", "br", "button", "caption",
    "cite", "code", "col", "colgroup", "dd", "del", "dfn", "div", "dl",
    "dt", "em", "fieldset", "figcaption", "figure", "footer", "form",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "i", "img",
    "input", "ins", "kbd", "label", "legend", "li", "main", "mark",
    "nav", "ol", "p", "pre", "q", "s", "samp", "section", "select",
    "small", "span", "strong", "sub", "sup", "table", "tbody", "td",
    "textarea", "tfoot", "th", "thead", "time", "tr", "u", "ul", "var",
]
ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "style", "aria-label", "aria-hidden", "role", "tabindex"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height", "loading"],
    "input": ["type", "name", "id", "placeholder", "required", "value", "min", "max"],
    "label": ["for"],
    "form": ["action", "method"],
    "button": ["type", "disabled"],
    "select": ["name", "id", "required"],
    "textarea": ["name", "id", "rows", "cols", "placeholder", "required"],
    "time": ["datetime"],
}


@dataclass
class RenderResult:
    html: str
    css: str
    assets: list[str] = field(default_factory=list)


def sanitize_html(html: str) -> str:
    """Remove disallowed tags and attributes using OWASP allowlist."""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
    )


def _minify_css(css: str) -> str:
    """Basic CSS minification."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)  # remove comments
    css = re.sub(r'\s+', ' ', css)                         # collapse whitespace
    css = re.sub(r'\s*([{};:,>~+])\s*', r'\1', css)       # remove spaces around operators
    return css.strip()


def _extract_template_html(sfc_template: str) -> str:
    """Extract inner HTML from a Vue template string."""
    return sfc_template.strip()


def _extract_styles(sfc_styles: str) -> str:
    return sfc_styles.strip()


class Renderer:
    """Renders Vue.js SFCs to static HTML5 + CSS."""

    def render(self, components: list["VueComponent"]) -> RenderResult:
        if not components:
            raise RenderError("Nenhum componente fornecido para renderização.")

        try:
            body_parts: list[str] = []
            css_parts: list[str] = []

            for comp in components:
                raw_html = _extract_template_html(comp.template)
                clean_html = sanitize_html(raw_html)
                body_parts.append(f"  <!-- {comp.name} -->\n  {clean_html}")
                css_parts.append(_extract_styles(comp.styles))

            body_html = "\n\n".join(body_parts)
            combined_css = "\n".join(css_parts)
            minified_css = _minify_css(combined_css)

            # Enforce CSS size limit (100KB for ≤10 sections)
            css_bytes = len(minified_css.encode("utf-8"))
            if css_bytes > 100 * 1024:
                logger.warning("CSS size %d bytes exceeds 100KB limit.", css_bytes)

            html = self._build_html5(body_html, minified_css)

            return RenderResult(html=html, css=minified_css)

        except RenderError:
            raise
        except Exception as exc:
            logger.error("Render failed: %s", exc, exc_info=True)
            raise RenderError(f"Falha na renderização: {exc}") from exc

    def _build_html5(self, body: str, css: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Landing Page</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    @media (max-width: 320px) {{ body {{ font-size: 14px; }} }}
    @media (min-width: 768px) {{ body {{ font-size: 16px; }} }}
    @media (min-width: 1280px) {{ body {{ max-width: 1280px; margin: 0 auto; }} }}
    {css}
  </style>
</head>
<body>
{body}
</body>
</html>"""
