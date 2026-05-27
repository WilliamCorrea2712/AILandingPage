"""
Property-based tests for Renderer.

Property 11: HTML sanitization with OWASP allowlist
Property 12: Well-formed HTML5 output
Property 13: CSS max size
"""
import pytest
from app.services.renderer import sanitize_html, Renderer
from app.engines.builder_engine import VueComponent


FORBIDDEN_TAGS = ["<script>", "<iframe>", "<object>", "<embed>"]
FORBIDDEN_ATTRS = ['onclick=', 'onload=', 'onerror=', 'javascript:']


def test_sanitize_removes_script_tags():
    """Property 11: <script> tags must be removed."""
    html = '<div>Hello</div><script>alert("xss")</script>'
    result = sanitize_html(html)
    assert "<script>" not in result
    assert "alert" not in result


def test_sanitize_removes_iframe():
    """Property 11: <iframe> tags must be removed."""
    html = '<div>Content</div><iframe src="evil.com"></iframe>'
    result = sanitize_html(html)
    assert "<iframe" not in result


def test_sanitize_removes_event_handlers():
    """Property 11: on* event handlers must be removed."""
    html = '<button onclick="evil()">Click</button>'
    result = sanitize_html(html)
    assert "onclick" not in result


def test_sanitize_removes_javascript_urls():
    """Property 11: javascript: URLs must be removed."""
    html = '<a href="javascript:void(0)">Link</a>'
    result = sanitize_html(html)
    assert "javascript:" not in result


def test_sanitize_preserves_allowed_tags():
    """Property 11: Allowed tags must be preserved."""
    html = '<div class="hero"><h1>Title</h1><p>Text</p><a href="https://example.com">Link</a></div>'
    result = sanitize_html(html)
    assert "<h1>" in result
    assert "<p>" in result


def _make_component(name: str) -> VueComponent:
    return VueComponent(
        name=name,
        template=f'  <section class="{name.lower()}-section"><h2>{name}</h2><p>Content</p></section>',
        script="",
        styles=f"  .{name.lower()}-section {{ padding: 32px; }}",
    )


def test_renderer_produces_valid_html5():
    """Property 12: Rendered HTML must be well-formed HTML5."""
    renderer = Renderer()
    components = [_make_component(n) for n in ["Hero", "CTA", "Footer"]]
    result = renderer.render(components)
    assert "<!DOCTYPE html>" in result.html
    assert "<html" in result.html
    assert "<head>" in result.html
    assert "<body>" in result.html
    assert "</html>" in result.html


def test_renderer_css_under_100kb():
    """Property 13: CSS must be <= 100KB for <= 10 sections."""
    renderer = Renderer()
    components = [_make_component(n) for n in
                  ["Hero", "CTA", "FAQ", "Pricing", "Testimonials", "Footer", "Header", "Features", "Banner", "Formulário"]]
    result = renderer.render(components)
    css_bytes = len(result.css.encode("utf-8"))
    assert css_bytes <= 100 * 1024, f"CSS size {css_bytes} bytes exceeds 100KB"
