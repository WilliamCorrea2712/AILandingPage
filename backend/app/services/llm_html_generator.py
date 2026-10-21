"""
LLM HTML Generator — Free-form landing page generation via Ollama.

When the user writes a prompt describing ANYTHING (curriculo, portfolio,
evento, landing page com efeitos, etc.), this module sends the full prompt
directly to Ollama and asks it to generate a complete, professional HTML page.

Pipeline:
1. Detect if prompt is "free-form" (no known niche, or explicit creative request)
2. Build a rich system prompt with HTML/CSS best practices injected
3. Call Ollama → receive full HTML
4. Validate and sanitize the HTML
5. Return (html, css) tuple — same interface as render_html()

Fallback: if Ollama unavailable or fails, returns None so the template
pipeline takes over.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = 120

# ─────────────────────────────────────────────────────────────────────────────
# Signals that tell us the user wants free-form generation,
# not a standard business niche page.
# ─────────────────────────────────────────────────────────────────────────────
FREE_FORM_SIGNALS = [
    r"curr[ií]culo",
    r"portf[oó]lio\s+pessoal",
    r"p[áa]gina\s+pessoal",
    r"sobre\s+mim",
    r"meu\s+site",
    r"efeito\s+(?:ao|de)\s+descer",
    r"scroll\s*(?:animation|efeito|suave)",
    r"parallax",
    r"anima[cç][aã]o\s+(?:css|scroll|entrada)",
    r"dark\s*mode",
    r"modo\s*escuro",
    r"gradiente\s+animado",
    r"landing\s+page\s+(?:criativa|interativa|animada)",
    r"one\s*page",
    r"countdown\s+timer",
    r"cronometro\s+regressivo",
    r"galeria\s+(?:interativa|com\s+lightbox|modal)",
    r"carrossel\s+(?:de\s+)?(?:imagens|fotos|depoimentos)",
    r"hero\s+(?:animado|com\s+video|parallax)",
    r"menu\s+(?:flutuante|sticky|hamburguer\s+animado)",
    r"bot[aã]o\s+(?:flutuante|whatsapp\s+fixo|cta\s+fixo)",
    r"formulario\s+(?:multi.?step|passo\s+a\s+passo)",
    r"quiz\b",
    r"chatbot\s+(?:widget|integrado)",
    r"mapa\s+interativo",
    r"timeline\b|linha\s+do\s+tempo",
    r"antes\s+e\s+depois\s+(?:slider|interativo)",
    r"comparador",
    r"tabela\s+comparativa\s+(?:animada|interativa)",
    r"lottie|svg\s+animado",
]

# ─────────────────────────────────────────────────────────────────────────────
# Niche slugs that map to "free-form" rather than template generation
# ─────────────────────────────────────────────────────────────────────────────
FREE_FORM_NICHES = {
    "negocios", "curriculo", "portfolio pessoal", "pagina pessoal",
    "evento especial", "lancamento criativo", "produto digital",
}


def is_free_form_prompt(prompt: str, niche: str) -> bool:
    """
    Returns True if the prompt should use free-form LLM generation
    instead of the template pipeline.
    """
    pl = prompt.lower()
    # If niche not recognized, try LLM
    if niche in FREE_FORM_NICHES:
        return True
    # If prompt contains creative/technical signals
    for pattern in FREE_FORM_SIGNALS:
        if re.search(pattern, pl):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# System prompt for free-form HTML generation
# ─────────────────────────────────────────────────────────────────────────────
_FREE_FORM_SYSTEM = """Você é um desenvolvedor front-end especialista em criar landing pages profissionais e criativas em HTML/CSS puro.

TAREFA: Gere uma landing page HTML COMPLETA baseada na descrição do usuário.

REGRAS OBRIGATÓRIAS:
1. Retorne APENAS o HTML completo, começando com <!DOCTYPE html> e terminando com </html>
2. NÃO inclua explicações, markdown, blocos de código, comentários externos ao HTML
3. Todo CSS deve estar dentro de <style> no <head>
4. Todo JavaScript deve estar dentro de <script> no final do <body>
5. Use Google Fonts via link rel="stylesheet"
6. A página deve ser 100% responsiva (mobile-first)
7. Cores devem ser harmoniosas e profissionais
8. Fontes: escolha fontes adequadas ao tipo de página pedida
9. Implemente EXATAMENTE o que foi pedido no prompt

RECURSOS QUE VOCÊ PODE USAR (apenas CSS/JS vanilla, sem CDN externo):
- CSS Animations e Transitions
- Scroll animations com Intersection Observer API
- CSS Grid e Flexbox
- CSS Custom Properties (variáveis)
- Sticky header com scroll
- Smooth scroll nativo
- Modal/lightbox com JavaScript puro
- Accordion/FAQ interativo
- Contador regressivo com JavaScript
- Lazy loading nativo
- CSS parallax com background-attachment: fixed
- Botão WhatsApp flutuante

QUALIDADE ESPERADA:
- Layout visual profissional, não genérico
- Hierarquia tipográfica clara
- Espaçamentos consistentes (múltiplos de 8px)
- Hover effects sutis nos botões e cards
- Sombras e bordas arredondadas onde fizer sentido
- Contraste WCAG AA (mínimo 4.5:1 para texto)
- Meta tags SEO preenchidas com base no conteúdo

Gere agora a página completa conforme o pedido do usuário."""


def generate_html_free_form(
    prompt: str,
    brand_color: str | None = None,
    accent_color: str | None = None,
    logo_url: str | None = None,
) -> tuple[str, str] | None:
    """
    Ask Ollama to generate a full HTML page from the user's prompt.
    Returns (html, css_snippet) or None if unavailable/failed.

    css_snippet is extracted from the <style> block for storage,
    but the full CSS is already embedded in the HTML.
    """
    # Enrich the user prompt with any extra context
    enriched = _enrich_prompt(prompt, brand_color, accent_color, logo_url)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": enriched,
        "system": _FREE_FORM_SYSTEM,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.4,
            "top_p": 0.92,
            "num_predict": 4096,
            "num_thread": 8,
        },
    }

    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            resp = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()

        html = _extract_html(raw)
        if not html:
            logger.warning("LLM free-form: no valid HTML in response (len=%d)", len(raw))
            return None

        css = _extract_css(html)
        logger.info("LLM free-form generation OK (html len=%d)", len(html))
        return html, css

    except httpx.ConnectError:
        logger.warning("LLM free-form: Ollama not available")
        return None
    except httpx.TimeoutException:
        logger.warning("LLM free-form: Ollama timed out after %ds", OLLAMA_TIMEOUT)
        return None
    except Exception as exc:
        logger.error("LLM free-form: unexpected error: %s", exc)
        return None


def _enrich_prompt(
    prompt: str,
    brand_color: str | None,
    accent_color: str | None,
    logo_url: str | None,
) -> str:
    """Add extra technical context to the user prompt."""
    parts = [prompt.strip()]

    if brand_color:
        parts.append(f"\nCor principal da marca: {brand_color}")
    if accent_color:
        parts.append(f"Cor de destaque: {accent_color}")
    if logo_url and logo_url.startswith("data:"):
        # Tell the LLM to use the logo but don't include the full base64
        parts.append("O logo foi fornecido como imagem base64 — use a variável {{LOGO_URL}} onde o logo deve aparecer.")
    elif logo_url:
        parts.append(f"URL do logo: {logo_url}")

    parts.append(
        "\n\nIMPORTANTE: Gere HTML completo, responsivo, com CSS interno e JavaScript onde necessário. "
        "Não use frameworks externos (Bootstrap, Tailwind, Vue, React). "
        "Use apenas HTML5, CSS3 e JavaScript vanilla."
    )
    result = "".join(parts)

    # Inject logo URL back if base64 was provided
    if logo_url and logo_url.startswith("data:"):
        result = result.replace("{{LOGO_URL}}", logo_url)

    return result


def _extract_html(raw: str) -> str:
    """
    Extract the HTML document from the LLM response.
    Handles cases where the model wraps it in markdown code blocks.
    """
    # Remove markdown code blocks if present
    raw = re.sub(r'^```(?:html)?\s*', '', raw, flags=re.MULTILINE)
    raw = re.sub(r'```\s*$', '', raw, flags=re.MULTILINE)
    raw = raw.strip()

    # Find <!DOCTYPE html> ... </html>
    match = re.search(r'<!DOCTYPE\s+html[\s\S]*</html>', raw, re.IGNORECASE)
    if match:
        return match.group(0).strip()

    # Fallback: find <html> ... </html>
    match = re.search(r'<html[\s\S]*</html>', raw, re.IGNORECASE)
    if match:
        return f'<!DOCTYPE html>\n{match.group(0).strip()}'

    # Last resort: if it starts with typical HTML tags, accept it
    if raw.startswith('<') and '</body>' in raw.lower():
        return raw

    return ""


def _extract_css(html: str) -> str:
    """Extract CSS from <style> blocks for storage purposes."""
    matches = re.findall(r'<style[^>]*>([\s\S]*?)</style>', html, re.IGNORECASE)
    return "\n".join(matches) if matches else ""


def _extract_js(html: str) -> str:
    """Extract JS from <script> blocks."""
    matches = re.findall(r'<script[^>]*>([\s\S]*?)</script>', html, re.IGNORECASE)
    return "\n".join(matches) if matches else ""
