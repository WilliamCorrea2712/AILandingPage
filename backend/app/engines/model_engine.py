"""
Model Engine — generates structured JSON using open-source LLMs with LoRA adapters.

Requirements: 2.1–2.6
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema

from app.config import settings
from app.exceptions import GenerationFailedError, JSONSchemaValidationError

if TYPE_CHECKING:
    from app.engines.nlp_engine import NLPResult

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "landing_page_schema.json"
with open(_SCHEMA_PATH) as _f:
    _LANDING_PAGE_SCHEMA = json.load(_f)

MAX_RETRIES = 2


@dataclass
class SectionJSON:
    component: str
    content: dict[str, Any]


@dataclass
class LandingPageJSON:
    headline: str
    subtitle: str
    sections: list[SectionJSON]
    ctas: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "headline": self.headline,
            "subtitle": self.subtitle,
            "sections": [{"component": s.component, "content": s.content} for s in self.sections],
            "ctas": self.ctas,
            "metadata": self.metadata,
        }


class ModelEngine:
    """Generates LandingPageJSON using a local open-source LLM."""

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        if self._model is not None:
            return self._model, self._tokenizer

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        model_name = settings.MODEL_NAME
        model_path = settings.MODEL_PATH
        adapter_path = settings.ADAPTER_PATH
        dtype = torch.float16 if settings.TORCH_DTYPE == "float16" else torch.bfloat16

        model_id = os.path.join(model_path, model_name) if os.path.exists(
            os.path.join(model_path, model_name)) else model_name

        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=dtype,
            device_map="auto",
        )

        # Load LoRA adapter if available
        adapter_dir = os.path.join(adapter_path, model_name)
        if os.path.exists(adapter_dir):
            from peft import PeftModel
            model = PeftModel.from_pretrained(model, adapter_dir)
            logger.info("Loaded LoRA adapter from %s", adapter_dir)

        self._model = model
        self._tokenizer = tokenizer
        return model, tokenizer

    def generate(self, nlp_result: "NLPResult") -> LandingPageJSON:
        """Generate structured JSON. Retries up to MAX_RETRIES times."""
        last_error: Exception | None = None
        temperature = 0.7

        for attempt in range(MAX_RETRIES + 1):
            try:
                raw = self._run_inference(nlp_result, temperature)
                data = self._parse_json(raw)
                self.validate_json(data)
                return self._build_result(data)
            except (GenerationFailedError, JSONSchemaValidationError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
                logger.warning("Generation attempt %d failed: %s", attempt + 1, exc)
                temperature = min(temperature + 0.1, 1.0)

        raise GenerationFailedError(
            f"Geração falhou após {MAX_RETRIES + 1} tentativas: {last_error}"
        )

    def _run_inference(self, nlp_result: "NLPResult", temperature: float) -> str:
        prompt = self._build_prompt(nlp_result)
        try:
            model, tokenizer = self._load_model()
            import torch
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=1024,
                    temperature=temperature,
                    do_sample=True,
                    pad_token_id=tokenizer.eos_token_id,
                )
            generated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            return generated
        except Exception as exc:
            # Fallback: return template-based JSON when model is not available
            logger.warning("Model inference failed (%s). Using template fallback.", exc)
            return self._template_fallback(nlp_result)

    def _build_prompt(self, nlp_result: "NLPResult") -> str:
        return (
            f"Gere um JSON estruturado para uma landing page com as seguintes características:\n"
            f"- Nicho: {nlp_result.niche}\n"
            f"- Intenção: {nlp_result.intention}\n"
            f"- Estilo visual: {nlp_result.visual_style}\n"
            f"- Tom: {nlp_result.communication_tone}\n\n"
            f"O JSON deve conter: headline, subtitle, sections (mínimo 3), ctas (mínimo 2).\n"
            f"Responda APENAS com o JSON válido, sem explicações.\n\nJSON:"
        )

    def _template_fallback(self, nlp_result: "NLPResult") -> str:
        niche = nlp_result.niche.capitalize()
        return json.dumps({
            "headline": f"Soluções em {niche} para o seu sucesso",
            "subtitle": f"Descubra como podemos transformar seu negócio de {niche}",
            "sections": [
                {"component": "Hero", "content": {"title": f"Bem-vindo ao melhor de {niche}"}},
                {"component": "Features", "content": {"items": ["Qualidade", "Confiança", "Resultados"]}},
                {"component": "Testimonials", "content": {"quote": f"Excelente serviço em {niche}!"}},
                {"component": "CTA", "content": {"text": "Comece agora"}},
                {"component": "Footer", "content": {"company": niche}},
            ],
            "ctas": ["Solicitar proposta", "Saiba mais"],
            "metadata": {"niche": nlp_result.niche, "style": nlp_result.visual_style},
        })

    def _parse_json(self, raw: str) -> dict:
        # Extract JSON block if wrapped in markdown
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(raw)

    def validate_json(self, data: dict) -> bool:
        try:
            jsonschema.validate(instance=data, schema=_LANDING_PAGE_SCHEMA)
            return True
        except jsonschema.ValidationError as exc:
            raise JSONSchemaValidationError(f"JSON inválido: {exc.message}") from exc

    def _build_result(self, data: dict) -> LandingPageJSON:
        sections = [SectionJSON(component=s["component"], content=s["content"]) for s in data["sections"]]
        return LandingPageJSON(
            headline=data["headline"],
            subtitle=data["subtitle"],
            sections=sections,
            ctas=data["ctas"],
            metadata=data.get("metadata", {}),
        )


import re  # noqa: E402 (needed for _parse_json)
