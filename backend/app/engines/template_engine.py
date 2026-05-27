"""
Template Engine — selects and composes responsive landing page layouts.

Requirements: 3.1–3.6
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.exceptions import MalformedInputError

if TYPE_CHECKING:
    from app.engines.model_engine import LandingPageJSON

logger = logging.getLogger(__name__)

REQUIRED_SECTIONS = ("Hero", "CTA", "Footer")
BREAKPOINTS = {"mobile": "320px", "tablet": "768px", "desktop": "1280px"}
SPACING_UNIT = 8  # multiples of 8px for layout sections


@dataclass
class LayoutSection:
    component: str
    content: dict[str, Any]
    order: int


@dataclass
class LayoutResult:
    template_id: str
    sections: list[LayoutSection]
    breakpoints: dict[str, str] = field(default_factory=lambda: dict(BREAKPOINTS))
    spacing_unit: int = SPACING_UNIT
    visual_style: str = "moderno"


class TemplateEngine:
    def __init__(self, template_repository=None, vector_client=None) -> None:
        self._repo = template_repository
        self._vector = vector_client

    def select_and_compose(
        self,
        json_data: "LandingPageJSON",
        style: str,
        user_template_id: str | None = None,
    ) -> LayoutResult:
        if json_data is None or not json_data.sections:
            raise MalformedInputError("JSON_Estruturado está malformado ou vazio.")

        # Select template
        template_id = self._select_template(style, user_template_id)

        # Build sections list
        sections: list[LayoutSection] = []
        for i, sec in enumerate(json_data.sections):
            sections.append(LayoutSection(component=sec.component, content=sec.content, order=i))

        # Ensure required sections exist
        existing_types = {s.component for s in sections}
        order = len(sections)
        for required in REQUIRED_SECTIONS:
            if required not in existing_types:
                sections.append(LayoutSection(
                    component=required,
                    content={"auto_generated": True},
                    order=order,
                ))
                order += 1
                logger.info("Auto-added required section: %s", required)

        # Sort: Hero first, Footer last
        sections = self._sort_sections(sections)

        return LayoutResult(
            template_id=template_id,
            sections=sections,
            breakpoints=dict(BREAKPOINTS),
            spacing_unit=SPACING_UNIT,
            visual_style=style,
        )

    def _select_template(self, style: str, user_template_id: str | None) -> str:
        if user_template_id:
            return user_template_id

        # Try vector search
        if self._vector:
            try:
                from app.services.embeddings import generate_embedding, TEMPLATES_COLLECTION
                emb = generate_embedding(style)
                results = self._vector.search(TEMPLATES_COLLECTION, emb, threshold=0.50, limit=1)
                if results:
                    return results[0]["payload"].get("template_id", f"default-{style}")
            except Exception as exc:
                logger.warning("Vector search failed: %s. Using default template.", exc)

        # Fallback: style-based default
        return f"default-{style}"

    def _sort_sections(self, sections: list[LayoutSection]) -> list[LayoutSection]:
        priority = {"Header": 0, "Hero": 1, "Features": 3, "Pricing": 4,
                    "Testimonials": 5, "FAQ": 6, "Banner": 7, "Formulário": 8,
                    "CTA": 9, "Footer": 10}
        return sorted(sections, key=lambda s: priority.get(s.component, 5))
