"""
NLP Engine — interprets user prompts and extracts structured attributes.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

from app.exceptions import NicheConfidenceLowError, PromptTooLongError, PromptTooShortError

logger = logging.getLogger(__name__)

INTENTIONS = ("captar leads", "vender produto", "apresentar serviço", "divulgar evento")
VISUAL_STYLES = ("minimalista", "corporativo", "moderno", "agressivo")
TONES = ("formal", "informal", "descontraído", "técnico")

DEFAULT_INTENTION: Literal["captar leads", "vender produto", "apresentar serviço", "divulgar evento"] = "captar leads"
DEFAULT_STYLE: Literal["minimalista", "corporativo", "moderno", "agressivo"] = "moderno"
DEFAULT_TONE: Literal["formal", "informal", "descontraído", "técnico"] = "formal"
CONFIDENCE_THRESHOLD = 0.60
MAX_NICHE_RETRIES = 3


@dataclass
class NLPResult:
    intention: Literal["captar leads", "vender produto", "apresentar serviço", "divulgar evento"]
    niche: str
    conversion_goal: str
    visual_style: Literal["minimalista", "corporativo", "moderno", "agressivo"]
    communication_tone: Literal["formal", "informal", "descontraído", "técnico"]
    confidence_scores: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class NLPEngine:
    """
    Extracts structured attributes from a natural-language prompt.
    Uses SentenceTransformers for zero-shot classification.
    """

    def __init__(self) -> None:
        self._model = None  # lazy-loaded

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return self._model

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x ** 2 for x in a))
        norm_b = math.sqrt(sum(x ** 2 for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _classify(self, prompt_emb: list[float], candidates: tuple[str, ...]) -> tuple[str, float]:
        """Zero-shot classification: return best candidate and its confidence score."""
        model = self._load_model()
        best_label, best_score = candidates[0], 0.0
        for label in candidates:
            label_emb = model.encode(label).tolist()
            score = self._cosine_similarity(prompt_emb, label_emb)
            if score > best_score:
                best_score = score
                best_label = label
        return best_label, best_score

    def _extract_niche(self, prompt_emb: list[float]) -> tuple[str, float]:
        """Extract niche using keyword similarity heuristic."""
        model = self._load_model()
        # Use the prompt itself as niche seed — in production this would use
        # a curated niche taxonomy. Here we return the prompt's first noun phrase.
        niche_candidates = [
            "odontologia", "academia", "restaurante", "tecnologia", "saúde",
            "educação", "imóveis", "moda", "beleza", "advocacia", "consultoria",
            "e-commerce", "software", "marketing", "finanças",
        ]
        best_niche, best_score = self._classify(prompt_emb, tuple(niche_candidates))
        return best_niche, best_score

    def extract_attributes(self, prompt: str, niche_hint: str | None = None) -> NLPResult:
        """
        Extract structured attributes from the prompt.

        Args:
            prompt: Natural-language description of the landing page.
            niche_hint: Optional user-provided niche refinement.

        Raises:
            PromptTooShortError: If prompt < 10 characters.
            PromptTooLongError: If prompt > 2000 characters.
            NicheConfidenceLowError: If niche confidence < 60% after 3 attempts.
        """
        # Validate length
        if len(prompt) < 10:
            raise PromptTooShortError("O prompt deve ter no mínimo 10 caracteres.")
        if len(prompt) > 2000:
            raise PromptTooLongError("O prompt deve ter no máximo 2000 caracteres.")

        start = time.monotonic()
        model = self._load_model()
        prompt_emb = model.encode(prompt).tolist()

        warnings: list[str] = []
        confidence_scores: dict[str, float] = {}

        # --- Niche extraction (with retry support) ---
        effective_prompt = niche_hint if niche_hint else prompt
        niche_emb = model.encode(effective_prompt).tolist()
        niche, niche_conf = self._extract_niche(niche_emb)
        confidence_scores["niche"] = niche_conf

        if niche_conf < CONFIDENCE_THRESHOLD:
            raise NicheConfidenceLowError(
                f"Não foi possível identificar o nicho com confiança suficiente "
                f"(confiança: {niche_conf:.0%}). Por favor, refine o prompt."
            )

        # --- Intention ---
        intention, int_conf = self._classify(prompt_emb, INTENTIONS)
        confidence_scores["intention"] = int_conf
        if int_conf < CONFIDENCE_THRESHOLD:
            warnings.append(f"Intenção não identificada com confiança ({int_conf:.0%}). Usando padrão: '{DEFAULT_INTENTION}'.")
            intention = DEFAULT_INTENTION

        # --- Visual style ---
        style, style_conf = self._classify(prompt_emb, VISUAL_STYLES)
        confidence_scores["visual_style"] = style_conf
        if style_conf < CONFIDENCE_THRESHOLD:
            warnings.append(f"Estilo visual não identificado com confiança ({style_conf:.0%}). Usando padrão: '{DEFAULT_STYLE}'.")
            style = DEFAULT_STYLE

        # --- Communication tone ---
        tone, tone_conf = self._classify(prompt_emb, TONES)
        confidence_scores["communication_tone"] = tone_conf
        if tone_conf < CONFIDENCE_THRESHOLD:
            warnings.append(f"Tom de comunicação não identificado com confiança ({tone_conf:.0%}). Usando padrão: '{DEFAULT_TONE}'.")
            tone = DEFAULT_TONE

        # Conversion goal derived from intention
        conversion_goal = intention

        elapsed = time.monotonic() - start
        if elapsed > 3.0:
            logger.warning("NLP extraction took %.2fs (SLA: 3s)", elapsed)

        for w in warnings:
            logger.warning("NLP warning: %s", w)

        return NLPResult(
            intention=intention,  # type: ignore[arg-type]
            niche=niche,
            conversion_goal=conversion_goal,
            visual_style=style,  # type: ignore[arg-type]
            communication_tone=tone,  # type: ignore[arg-type]
            confidence_scores=confidence_scores,
            warnings=warnings,
        )
