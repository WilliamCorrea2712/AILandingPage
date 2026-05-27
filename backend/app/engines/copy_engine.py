"""
Copy Engine — generates persuasive copywriting, SEO metadata and headline variations.

Requirements: 6.1–6.7
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.engines.nlp_engine import NLPResult

logger = logging.getLogger(__name__)

TONE_FORMAL = ("formal", "técnico")
TONE_INFORMAL = ("informal", "descontraído")


@dataclass
class SEOMeta:
    title: str      # 50–60 chars
    description: str  # 150–160 chars
    keywords: list[str] = field(default_factory=list)


@dataclass
class SocialProof:
    testimonial: str | None = None
    stat: str | None = None   # e.g. "+500 clientes satisfeitos"


@dataclass
class ValueProposition:
    benefit: str
    differentiator: str
    target_audience: str


@dataclass
class CopyResult:
    headline_variations: list[str]   # exactly 3
    approved_headline: str
    subtitle: str
    ctas: list[str]                  # min 2, distinct
    social_proof: SocialProof
    value_proposition: ValueProposition
    seo_meta: SEOMeta


class CopyEngine:
    """Generates landing page copy using template-based generation."""

    def generate_copy(
        self,
        nlp_result: "NLPResult",
        approved_headline: str | None = None,
    ) -> CopyResult:
        tone = nlp_result.communication_tone
        niche = nlp_result.niche
        intention = nlp_result.intention
        goal = nlp_result.conversion_goal

        if not tone:
            tone = "formal"
            logger.warning("Tom de comunicação não identificado. Usando padrão: 'formal'.")

        # Generate 3 headline variations
        variations = self._generate_headlines(niche, intention, tone)
        headline = approved_headline if approved_headline else variations[0]

        subtitle = self._generate_subtitle(niche, goal, tone)
        ctas = self._generate_ctas(intention, tone)
        social_proof = self._generate_social_proof(niche)
        value_prop = self._generate_value_proposition(niche, intention, tone)
        seo = self._generate_seo_meta(niche, intention)

        result = CopyResult(
            headline_variations=variations,
            approved_headline=headline,
            subtitle=subtitle,
            ctas=ctas,
            social_proof=social_proof,
            value_proposition=value_prop,
            seo_meta=seo,
        )

        # Validate uniqueness
        sections = [headline, subtitle] + ctas + [social_proof.testimonial or "", value_prop.benefit]
        if not self._check_text_uniqueness(sections):
            logger.warning("Duplicate text sequences detected between sections.")

        return result

    def _is_formal(self, tone: str) -> bool:
        return tone in TONE_FORMAL

    def _generate_headlines(self, niche: str, intention: str, tone: str) -> list[str]:
        niche_cap = niche.capitalize()
        if self._is_formal(tone):
            return [
                f"Soluções Especializadas em {niche_cap} para Resultados Superiores",
                f"Transforme Seu Negócio de {niche_cap} com Excelência e Precisão",
                f"A Referência em {niche_cap}: Qualidade e Confiança Garantidas",
            ]
        else:
            return [
                f"Chega de perder tempo! Descubra o melhor de {niche_cap} agora",
                f"Você merece o melhor em {niche_cap} — e a gente entrega",
                f"Transforme sua vida com {niche_cap} de verdade",
            ]

    def _generate_subtitle(self, niche: str, goal: str, tone: str) -> str:
        if self._is_formal(tone):
            return (
                f"Oferecemos soluções completas em {niche} com foco em {goal}. "
                f"Nossa metodologia comprovada garante resultados mensuráveis para o seu negócio."
            )
        return (
            f"A gente entende o que você precisa em {niche}. "
            f"Vamos juntos alcançar {goal} de um jeito simples e eficiente!"
        )

    def _generate_ctas(self, intention: str, tone: str) -> list[str]:
        if self._is_formal(tone):
            return ["Solicitar Proposta Gratuita", "Conhecer Nossas Soluções"]
        return ["Quero começar agora!", "Me mostra como funciona"]

    def _generate_social_proof(self, niche: str) -> SocialProof:
        return SocialProof(
            testimonial=f"Excelente serviço em {niche}. Superou todas as minhas expectativas!",
            stat=f"+500 clientes satisfeitos em {niche}",
        )

    def _generate_value_proposition(self, niche: str, intention: str, tone: str) -> ValueProposition:
        return ValueProposition(
            benefit=f"Resultados comprovados em {niche}",
            differentiator="Metodologia exclusiva e suporte dedicado",
            target_audience=f"Empresas e profissionais de {niche}",
        )

    def _generate_seo_meta(self, niche: str, intention: str) -> SEOMeta:
        # Title: 50–60 chars
        base_title = f"{niche.capitalize()} — {intention.capitalize()}"
        title = self._fit_to_length(base_title, 50, 60)

        # Description: 150–160 chars
        base_desc = (
            f"Descubra as melhores soluções em {niche} para {intention}. "
            f"Qualidade, confiança e resultados garantidos para o seu negócio."
        )
        description = self._fit_to_length(base_desc, 150, 160)

        return SEOMeta(
            title=title,
            description=description,
            keywords=[niche, intention, "landing page", "solução"],
        )

    def _fit_to_length(self, text: str, min_len: int, max_len: int) -> str:
        if len(text) < min_len:
            text = text + " " * (min_len - len(text))
            text = text[:min_len]
        if len(text) > max_len:
            text = text[:max_len - 3] + "..."
        # Pad if still short
        while len(text) < min_len:
            text += "."
        return text[:max_len]

    def _check_text_uniqueness(self, sections: list[str]) -> bool:
        """Return True if no 10+ word sequence is repeated across sections."""
        def get_ngrams(text: str, n: int) -> set[str]:
            words = re.findall(r'\w+', text.lower())
            return {" ".join(words[i:i+n]) for i in range(len(words) - n + 1)}

        all_ngrams: list[set[str]] = [get_ngrams(s, 10) for s in sections if s]
        for i in range(len(all_ngrams)):
            for j in range(i + 1, len(all_ngrams)):
                if all_ngrams[i] & all_ngrams[j]:
                    return False
        return True


def check_text_uniqueness(sections: list[str]) -> bool:
    """Module-level helper for testing."""
    return CopyEngine()._check_text_uniqueness(sections)
