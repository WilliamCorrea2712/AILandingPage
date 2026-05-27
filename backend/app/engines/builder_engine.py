"""
Builder Engine — converts layout sections into Vue.js Single-File Components.

Requirements: 4.1–4.6
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.exceptions import MalformedInputError

if TYPE_CHECKING:
    from app.engines.design_engine import DesignResult
    from app.engines.copy_engine import CopyResult
    from app.engines.template_engine import LayoutResult

logger = logging.getLogger(__name__)

SUPPORTED_COMPONENTS = [
    "Hero", "CTA", "FAQ", "Pricing", "Testimonials",
    "Footer", "Header", "Features", "Banner", "Formulário",
]


@dataclass
class VueComponent:
    name: str
    template: str
    script: str
    styles: str
    a11y_warnings: list[str] = field(default_factory=list)

    def to_sfc(self) -> str:
        return f"<template>\n{self.template}\n</template>\n\n<script setup lang=\"ts\">\n{self.script}\n</script>\n\n<style scoped>\n{self.styles}\n</style>\n"


class BuilderEngine:
    SUPPORTED_COMPONENTS = SUPPORTED_COMPONENTS

    def build(
        self,
        layout: "LayoutResult",
        design: "DesignResult",
        copy: "CopyResult",
    ) -> list[VueComponent]:
        if layout is None or not layout.sections:
            raise MalformedInputError("LayoutResult está malformado ou vazio.")

        components: list[VueComponent] = []
        for i, section in enumerate(layout.sections):
            comp_type = section.component
            if comp_type not in SUPPORTED_COMPONENTS:
                logger.warning(
                    "Tipo de componente desconhecido '%s' na posição %d. Ignorando.",
                    comp_type, i,
                )
                continue
            comp = self._build_component(comp_type, section.content, design, copy)
            components.append(comp)

        return components

    def _build_component(
        self,
        comp_type: str,
        content: dict[str, Any],
        design: "DesignResult",
        copy: "CopyResult",
    ) -> VueComponent:
        primary = design.palette.primary
        accent = design.palette.accent
        neutral1 = design.palette.neutral_1
        heading_font = design.typography.heading_font
        body_font = design.typography.body_font
        a11y_warnings: list[str] = []

        builders = {
            "Hero": self._hero,
            "CTA": self._cta,
            "FAQ": self._faq,
            "Pricing": self._pricing,
            "Testimonials": self._testimonials,
            "Footer": self._footer,
            "Header": self._header,
            "Features": self._features,
            "Banner": self._banner,
            "Formulário": self._formulario,
        }

        template, script, styles = builders[comp_type](content, copy, primary, accent, neutral1, heading_font, body_font)

        # Accessibility checks
        if "<img" in template and 'alt=' not in template:
            a11y_warnings.append(f"{comp_type}: imagem sem atributo alt.")
            logger.warning("%s: imagem sem atributo alt.", comp_type)
        if comp_type == "Formulário" and "<label" not in template:
            a11y_warnings.append(f"{comp_type}: formulário sem labels.")
            logger.warning("%s: formulário sem labels.", comp_type)

        return VueComponent(name=comp_type, template=template, script=script, styles=styles, a11y_warnings=a11y_warnings)

    def _hero(self, content, copy, primary, accent, neutral1, hf, bf):
        headline = copy.approved_headline
        subtitle = copy.subtitle
        cta = copy.ctas[0] if copy.ctas else "Saiba mais"
        template = f"""  <section class="hero-section">
    <div class="hero-content">
      <h1 class="hero-title">{{ headline }}</h1>
      <p class="hero-subtitle">{{ subtitle }}</p>
      <button class="hero-cta" type="button">{{ cta }}</button>
    </div>
  </section>"""
        script = f'const headline = "{headline}"\nconst subtitle = "{subtitle}"\nconst cta = "{cta}"'
        styles = f"""  .hero-section {{ background-color: {primary}; padding: 64px 32px; }}
  .hero-content {{ max-width: 800px; margin: 0 auto; text-align: center; }}
  .hero-title {{ font-family: "{hf}", sans-serif; color: {neutral1}; font-size: 2.5rem; margin-bottom: 16px; }}
  .hero-subtitle {{ font-family: "{bf}", sans-serif; color: {neutral1}; font-size: 1.25rem; margin-bottom: 32px; }}
  .hero-cta {{ background-color: {accent}; color: #fff; padding: 16px 32px; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}"""
        return template, script, styles

    def _cta(self, content, copy, primary, accent, neutral1, hf, bf):
        cta_text = copy.ctas[1] if len(copy.ctas) > 1 else copy.ctas[0]
        template = f"""  <section class="cta-section">
    <div class="cta-content">
      <h2 class="cta-title">Pronto para começar?</h2>
      <button class="cta-button" type="button">{{ ctaText }}</button>
    </div>
  </section>"""
        script = f'const ctaText = "{cta_text}"'
        styles = f"""  .cta-section {{ background-color: {accent}; padding: 48px 32px; text-align: center; }}
  .cta-title {{ font-family: "{hf}", sans-serif; color: #fff; font-size: 2rem; margin-bottom: 24px; }}
  .cta-button {{ background-color: #fff; color: {accent}; padding: 16px 32px; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}"""
        return template, script, styles

    def _faq(self, content, copy, primary, accent, neutral1, hf, bf):
        template = """  <section class="faq-section">
    <h2 class="faq-title">Perguntas Frequentes</h2>
    <div v-for="(item, i) in faqs" :key="i" class="faq-item">
      <h3 class="faq-question">{{ item.question }}</h3>
      <p class="faq-answer">{{ item.answer }}</p>
    </div>
  </section>"""
        script = 'const faqs = [{ question: "Como funciona?", answer: "É simples e rápido." }]'
        styles = f"""  .faq-section {{ padding: 48px 32px; background-color: {neutral1}; }}
  .faq-title {{ font-family: "{hf}", sans-serif; color: {primary}; font-size: 2rem; margin-bottom: 32px; text-align: center; }}
  .faq-item {{ margin-bottom: 24px; }}
  .faq-question {{ font-family: "{hf}", sans-serif; color: {primary}; font-size: 1.25rem; }}
  .faq-answer {{ font-family: "{bf}", sans-serif; color: #4A5568; margin-top: 8px; }}"""
        return template, script, styles

    def _pricing(self, content, copy, primary, accent, neutral1, hf, bf):
        template = """  <section class="pricing-section">
    <h2 class="pricing-title">Planos e Preços</h2>
    <div class="pricing-grid">
      <div v-for="(plan, i) in plans" :key="i" class="pricing-card">
        <h3>{{ plan.name }}</h3>
        <p class="price">{{ plan.price }}</p>
        <button type="button">Escolher</button>
      </div>
    </div>
  </section>"""
        script = 'const plans = [{ name: "Básico", price: "R$ 99/mês" }, { name: "Pro", price: "R$ 199/mês" }]'
        styles = f"""  .pricing-section {{ padding: 48px 32px; background-color: {neutral1}; }}
  .pricing-title {{ font-family: "{hf}", sans-serif; color: {primary}; font-size: 2rem; text-align: center; margin-bottom: 32px; }}
  .pricing-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; }}
  .pricing-card {{ background: #fff; padding: 32px; border-radius: 8px; text-align: center; }}
  .price {{ font-size: 2rem; color: {accent}; margin: 16px 0; }}"""
        return template, script, styles

    def _testimonials(self, content, copy, primary, accent, neutral1, hf, bf):
        testimonial = copy.social_proof.testimonial or "Excelente serviço!"
        template = f"""  <section class="testimonials-section">
    <h2 class="testimonials-title">O que dizem nossos clientes</h2>
    <blockquote class="testimonial">
      <p>{{ testimonial }}</p>
    </blockquote>
  </section>"""
        script = f'const testimonial = "{testimonial}"'
        styles = f"""  .testimonials-section {{ padding: 48px 32px; background-color: {primary}; text-align: center; }}
  .testimonials-title {{ font-family: "{hf}", sans-serif; color: {neutral1}; font-size: 2rem; margin-bottom: 32px; }}
  .testimonial {{ font-family: "{bf}", sans-serif; color: {neutral1}; font-size: 1.25rem; font-style: italic; max-width: 600px; margin: 0 auto; }}"""
        return template, script, styles

    def _footer(self, content, copy, primary, accent, neutral1, hf, bf):
        template = """  <footer class="footer-section">
    <p class="footer-text">© 2024 Todos os direitos reservados.</p>
  </footer>"""
        script = ""
        styles = f"""  .footer-section {{ background-color: {primary}; padding: 32px; text-align: center; }}
  .footer-text {{ font-family: "{bf}", sans-serif; color: {neutral1}; font-size: 0.875rem; }}"""
        return template, script, styles

    def _header(self, content, copy, primary, accent, neutral1, hf, bf):
        template = """  <header class="header-section">
    <nav class="header-nav">
      <span class="header-logo">Logo</span>
      <button class="header-cta" type="button">Contato</button>
    </nav>
  </header>"""
        script = ""
        styles = f"""  .header-section {{ background-color: {primary}; padding: 16px 32px; }}
  .header-nav {{ display: flex; justify-content: space-between; align-items: center; max-width: 1200px; margin: 0 auto; }}
  .header-logo {{ font-family: "{hf}", sans-serif; color: {neutral1}; font-size: 1.5rem; font-weight: bold; }}
  .header-cta {{ background-color: {accent}; color: #fff; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; }}"""
        return template, script, styles

    def _features(self, content, copy, primary, accent, neutral1, hf, bf):
        template = """  <section class="features-section">
    <h2 class="features-title">Nossos Diferenciais</h2>
    <div class="features-grid">
      <div v-for="(f, i) in features" :key="i" class="feature-item">
        <h3>{{ f.title }}</h3>
        <p>{{ f.description }}</p>
      </div>
    </div>
  </section>"""
        script = 'const features = [{ title: "Qualidade", description: "Excelência em tudo." }, { title: "Rapidez", description: "Entrega no prazo." }, { title: "Suporte", description: "Atendimento 24/7." }]'
        styles = f"""  .features-section {{ padding: 48px 32px; background-color: {neutral1}; }}
  .features-title {{ font-family: "{hf}", sans-serif; color: {primary}; font-size: 2rem; text-align: center; margin-bottom: 32px; }}
  .features-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 24px; }}
  .feature-item {{ padding: 24px; background: #fff; border-radius: 8px; text-align: center; }}"""
        return template, script, styles

    def _banner(self, content, copy, primary, accent, neutral1, hf, bf):
        template = """  <section class="banner-section">
    <p class="banner-text">{{ bannerText }}</p>
  </section>"""
        script = f'const bannerText = "{copy.social_proof.stat or "Oferta especial por tempo limitado!"}"'
        styles = f"""  .banner-section {{ background-color: {accent}; padding: 16px 32px; text-align: center; }}
  .banner-text {{ font-family: "{bf}", sans-serif; color: #fff; font-size: 1rem; font-weight: bold; }}"""
        return template, script, styles

    def _formulario(self, content, copy, primary, accent, neutral1, hf, bf):
        template = """  <section class="form-section">
    <h2 class="form-title">Entre em Contato</h2>
    <form class="contact-form" @submit.prevent="handleSubmit">
      <div class="form-group">
        <label for="name">Nome</label>
        <input id="name" v-model="form.name" type="text" placeholder="Seu nome" required />
      </div>
      <div class="form-group">
        <label for="email">E-mail</label>
        <input id="email" v-model="form.email" type="email" placeholder="seu@email.com" required />
      </div>
      <button type="submit" class="form-submit">Enviar</button>
    </form>
  </section>"""
        script = """import { reactive } from 'vue'
const form = reactive({ name: '', email: '' })
const handleSubmit = () => { console.log('Form submitted', form) }"""
        styles = f"""  .form-section {{ padding: 48px 32px; background-color: {neutral1}; }}
  .form-title {{ font-family: "{hf}", sans-serif; color: {primary}; font-size: 2rem; text-align: center; margin-bottom: 32px; }}
  .contact-form {{ max-width: 480px; margin: 0 auto; }}
  .form-group {{ margin-bottom: 16px; }}
  .form-group label {{ display: block; font-family: "{bf}", sans-serif; color: {primary}; margin-bottom: 4px; }}
  .form-group input {{ width: 100%; padding: 12px; border: 1px solid #CBD5E0; border-radius: 4px; font-size: 1rem; }}
  .form-submit {{ width: 100%; background-color: {accent}; color: #fff; padding: 16px; border: none; border-radius: 4px; font-size: 1rem; cursor: pointer; }}"""
        return template, script, styles
