"""
NLP Service — uses local Ollama (llama3.2:3b) with few-shot learning.

Flow:
1. Regex parser detects niche (fast, deterministic)
2. Few-shot examples for that niche are fetched from validated training_data
3. Examples are injected into the Ollama system prompt
4. Ollama learns IN-CONTEXT from real approved examples — no fine-tuning needed
5. Result is merged with regex output

CPU timing: llama3.2:3b ~40-70s depending on prompt+examples size.
Strategy: parallel thread, 45s timeout, regex fallback.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = 90
OLLAMA_KEEP_ALIVE = "10m"

# ── Base system prompt ────────────────────────────────────────────────────────
BASE_SYSTEM_PROMPT = """Você extrai informações de prompts para criação de landing pages em português brasileiro. Retorne APENAS JSON válido, sem texto extra, sem markdown.

CAMPOS OBRIGATÓRIOS (extraia com atenção a cada detalhe do prompt):

Negócio:
- business_name: nome exato do negócio entre aspas ou mencionado explicitamente (string ou null)
- niche: nicho em português minúsculas. Ex: "odontologia", "fitness", "farmacia", "loja construcao", "barbearia", "crossfit", "advocacia" (string)
- business_type: descrição do tipo de negócio. Ex: "Farmácia", "Clínica Odontológica", "Academia de CrossFit" (string)
- services: produtos ou serviços mencionados explicitamente (array de strings, max 6)
- differentials: diferenciais competitivos mencionados. Ex: "10 anos de experiência", "atendimento 24h", "garantia de satisfação" (array, max 5)
- target_audience: público-alvo descrito. Se disser "todos" retorne "público geral" (string)

Contato e localização:
- address: endereço completo se mencionado (string ou null)
- location: cidade ou bairro (string ou null)
- phone: número de telefone (string ou null)
- email: endereço de email (string ou null)
- whatsapp: número WhatsApp (string ou null)
- instagram: @ do instagram SEM o @ (string ou null)
- schedule: horários de funcionamento como array de {day, time, event}. Ex: [{day:"Segunda a Sexta", time:"08:00 às 18:00", event:""}] (array ou [])

Estilo visual:
- visual_style: "moderno", "corporativo", "minimalista" ou "agressivo". Escolha baseado no tipo de negócio e palavras-chave do prompt (string)
- tone: "formal" se o negócio for profissional/saúde/jurídico, "informal" se for jovem/esporte/entretenimento (string)
- primary_color: cor principal mencionada em português. Ex: "azul", "verde", "vermelho" (string ou null)
- accent_color: cor secundária mencionada (string ou null)

Intenção e seções:
- intention: "captar leads", "vender produto", "divulgar evento" ou "vender curso" (string)
- wants_form: true se formulário, contato, cadastro, agendamento ou WhatsApp mencionado (boolean)
- wants_faq: true se FAQ, perguntas frequentes, dúvidas mencionado (boolean)
- wants_pricing: true se preços, planos, tabela, valores mencionado (boolean)
- wants_gallery: true se galeria, fotos, portfólio, antes e depois mencionado (boolean)
- wants_map: true se endereço, mapa, localização, "como chegar" mencionado (boolean)
- wants_video: true se vídeo, youtube, apresentação em vídeo mencionado (boolean)
- wants_countdown: true se contador, urgência, oferta limitada, vagas limitadas mencionado (boolean)
- wants_about: true se "sobre nós", "sobre a empresa", "quem somos", "história" mencionado (boolean)
- wants_partners: true se parceiros, clientes, certificações, selos mencionado (boolean)
- testimonial_count: quantos depoimentos pediu (integer, padrão 3, máximo 6)
- banner_count: quantos banners/heroes pediu (integer, padrão 1, máximo 4)
- sections_requested: lista de seções explicitamente pedidas. Ex: ["formulario", "faq", "galeria", "mapa", "sobre"] (array)

Extra:
- extra_info: qualquer informação relevante não capturada acima. Ex: promoções, história, diferenciais únicos (string ou null)

REGRAS IMPORTANTES:
- Se o prompt mencionar "remédio", "medicamento" → services inclua "Medicamentos"
- Se mencionar "perfumaria", "higiene" → services inclua "Perfumaria e Higiene"
- Se mencionar "todos" como público → target_audience = "público geral"
- Extraia TUDO que está no prompt, não invente nada que não foi dito
- Horários como "Segunda a Sexta: 08h às 18h" → schedule: [{day:"Segunda a Sexta", time:"08:00 às 18:00", event:""}]

Retorne APENAS o JSON, sem explicações."""

COLOR_NAMES = {
    "azul": "#1A56DB", "vermelho": "#C53030", "verde": "#276749",
    "amarelo": "#D69E2E", "laranja": "#C05621", "roxo": "#6B46C1",
    "rosa": "#B83280", "preto": "#1A202C", "dourado": "#B7791F",
    "cinza": "#718096", "branco": "#F7FAFC", "marrom": "#744210",
    "bege": "#D4A574", "turquesa": "#0694A2", "coral": "#E05252",
    "lilas": "#9061F9", "vinho": "#7B2D8B", "navy": "#1A365D",
    "nude": "#E8C9A0", "tiffany": "#0ABAB5",
}


# ── Few-shot example loading ──────────────────────────────────────────────────

def _load_few_shot_examples(niche: str, limit: int = 2) -> list[dict]:
    """
    Load top approved training examples for the given niche from the DB.
    Threshold lowered to 0.65 to include default-score (0.7) entries
    until human feedback pushes scores higher.
    """
    if not niche or niche == "negocios":
        return []

    try:
        from app.database import get_db_session
        from app.models.training_data import TrainingData

        with get_db_session() as db:
            rows = (
                db.query(TrainingData)
                .filter(
                    TrainingData.is_validated == True,
                    TrainingData.quality_score >= 0.65,  # was 0.8 — too restrictive
                    TrainingData.prompt.ilike(f"%{niche}%"),
                )
                .order_by(TrainingData.quality_score.desc(), TrainingData.created_at.desc())
                .limit(limit)
                .all()
            )

            examples = []
            for row in rows:
                try:
                    comp = json.loads(row.completion)
                    examples.append({
                        "prompt":   row.prompt[:300],
                        "niche":    comp.get("niche", niche),
                        "headline": comp.get("headline", ""),
                        "sections": comp.get("sections", []),
                        "style":    comp.get("style", ""),
                    })
                except (json.JSONDecodeError, Exception):
                    pass

            return examples

    except Exception as e:
        logger.debug("Could not load few-shot examples: %s", e)
        return []


def _load_pattern_examples(niche: str) -> dict[str, list[str]]:
    """
    Load top patterns from pattern_cache for a given niche using
    the same diversity score as get_learned_patterns().
    """
    if not niche or niche == "negocios":
        return {}

    try:
        import math
        from app.database import get_db_session
        from app.models.pattern_cache import PatternCache

        with get_db_session() as db:
            rows = (
                db.query(PatternCache)
                .filter(PatternCache.niche == niche)
                .order_by(PatternCache.avg_rating.desc().nullslast())
                .limit(40)
                .all()
            )

            # Re-rank by diversity score
            def diversity_score(row) -> float:
                rating = row.avg_rating if row.avg_rating is not None else 1.0
                freq = max(row.frequency, 1)
                return rating * (1.0 / math.log2(freq + 2))

            ranked = sorted(rows, key=diversity_score, reverse=True)

            patterns: dict[str, list[str]] = {}
            for row in ranked:
                if row.pattern_type not in patterns:
                    patterns[row.pattern_type] = []
                if len(patterns[row.pattern_type]) < 5:
                    patterns[row.pattern_type].append(row.value)

            return patterns

    except Exception as e:
        logger.debug("Could not load pattern examples: %s", e)
        return {}


def _build_system_prompt(niche: str) -> str:
    """
    Build an enriched system prompt with few-shot examples for the detected niche.
    More examples → better extraction → better landing pages.
    """
    base = BASE_SYSTEM_PROMPT

    # Load real examples from approved generations
    examples = _load_few_shot_examples(niche, limit=2)
    patterns = _load_pattern_examples(niche)

    if not examples and not patterns:
        return base

    enrichment_parts = []

    # Add few-shot examples (most powerful learning signal)
    if examples:
        enrichment_parts.append(
            f"\n\nExemplos reais aprovados de usuários para o nicho '{niche}':"
        )
        for i, ex in enumerate(examples, 1):
            enrichment_parts.append(
                f"\nExemplo {i}:"
                f"\n  Prompt: {ex['prompt']}"
                f"\n  Niche detectado: {ex['niche']}"
                f"\n  Headline gerada: {ex['headline']}"
                f"\n  Seções: {', '.join(ex['sections'][:5])}"
            )
        enrichment_parts.append(
            "\nUse esses exemplos como referência para extrair o contexto do novo prompt."
        )

    # Add learned patterns (top services, differentials for this niche)
    if patterns.get("service"):
        top_svcs = patterns["service"][:5]
        enrichment_parts.append(
            f"\n\nServiços mais comuns aprovados por usuários para '{niche}': "
            f"{', '.join(top_svcs)}"
        )

    if patterns.get("differential"):
        top_diffs = patterns["differential"][:3]
        enrichment_parts.append(
            f"\nDiferenciais mais mencionados para '{niche}': "
            f"{', '.join(top_diffs)}"
        )

    if enrichment_parts:
        return base + "".join(enrichment_parts) + "\n\nRetorne APENAS o JSON."
    return base


# ── Core LLM call ─────────────────────────────────────────────────────────────

def extract_context_with_llm(
    prompt: str,
    niche_hint: str = "",
) -> dict[str, Any] | None:
    """
    Send the prompt to Ollama with few-shot context for the detected niche.
    niche_hint comes from the fast regex parser and guides example selection.
    """
    system_prompt = _build_system_prompt(niche_hint)
    had_examples = "Exemplos reais" in system_prompt or "Serviços mais comuns" in system_prompt

    if had_examples:
        logger.info("Using few-shot prompt for niche '%s'", niche_hint)
    else:
        logger.info("No few-shot examples for niche '%s' — using base prompt", niche_hint)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "num_predict": 1024,
            "num_thread": 8,
        },
    }

    try:
        with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
            resp = client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data.get("response", "").strip()

        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if not json_match:
            logger.warning("Ollama response has no JSON: %s", raw_text[:200])
            return None

        parsed = json.loads(json_match.group(0))
        logger.info(
            "Ollama extraction OK — niche: %s%s",
            parsed.get("niche", "?"),
            " (few-shot)" if had_examples else ""
        )
        return parsed

    except httpx.ConnectError:
        logger.warning("Ollama not available — using regex fallback")
        return None
    except httpx.TimeoutException:
        logger.warning("Ollama timed out after %ds — using regex fallback", OLLAMA_TIMEOUT)
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Ollama JSON parse error: %s — using regex fallback", e)
        return None
    except Exception as e:
        logger.error("Ollama unexpected error: %s — using regex fallback", e)
        return None


def is_ollama_available() -> bool:
    try:
        with httpx.Client(timeout=3) as client:
            resp = client.get(f"{OLLAMA_URL}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


def normalize_llm_context(llm_ctx: dict, original_prompt: str) -> dict[str, Any]:
    """Normalize LLM output to match generation pipeline format.
    Handles all fields from the improved BASE_SYSTEM_PROMPT including
    wants_gallery, wants_video, wants_countdown, wants_about, sections_requested,
    banner_count, and color names.
    """

    def safe_str(val, default="") -> str:
        return str(val).strip() if val and str(val).strip() not in ("null", "None", "") else default

    def safe_list(val, default=None) -> list:
        if isinstance(val, list):
            return [str(x).strip() for x in val if x and str(x).strip()]
        return default or []

    def safe_bool(val, default=False) -> bool:
        if isinstance(val, bool): return val
        if isinstance(val, str): return val.lower() in ("true", "yes", "1", "sim")
        return bool(val) if val is not None else default

    def safe_int(val, default=3) -> int:
        try: return int(val)
        except (TypeError, ValueError): return default

    # ── Schedule ──────────────────────────────────────────────────────────
    schedule = []
    for item in safe_list(llm_ctx.get("schedule")):
        if isinstance(item, dict):
            schedule.append({
                "day":   safe_str(item.get("day"), ""),
                "time":  safe_str(item.get("time"), ""),
                "event": safe_str(item.get("event"), ""),
            })

    # ── Colors — accept hex or portuguese name ─────────────────────────────
    primary_color = safe_str(llm_ctx.get("primary_color"))
    accent_color  = safe_str(llm_ctx.get("accent_color"))
    if primary_color and not primary_color.startswith("#"):
        primary_color = COLOR_NAMES.get(primary_color.lower(), "")
    if accent_color and not accent_color.startswith("#"):
        accent_color = COLOR_NAMES.get(accent_color.lower(), "")

    # ── Form fields — infer from prompt ───────────────────────────────────
    form_fields = ["Nome", "E-mail"]
    pl = original_prompt.lower()
    if any(w in pl for w in ["telefone", "celular", "whatsapp", "fone", "zap"]):
        form_fields.append("Telefone/WhatsApp")
    if any(w in pl for w in ["empresa", "cnpj"]):
        form_fields.append("Empresa")
    if any(w in pl for w in ["mensagem", "assunto", "duvida", "comentario"]):
        form_fields.append("Mensagem")
    if any(w in pl for w in ["data", "horario", "agendamento", "consulta"]):
        form_fields.append("Data preferida")
    if any(w in pl for w in ["cidade", "estado", "regiao"]):
        form_fields.append("Cidade")

    # ── sections_requested — from LLM + prompt keywords ───────────────────
    sections_requested = safe_list(llm_ctx.get("sections_requested"))
    # Also detect from flags the LLM set
    if safe_bool(llm_ctx.get("wants_about")) and "about" not in sections_requested:
        sections_requested.append("about")
    if safe_bool(llm_ctx.get("wants_partners")) and "partners" not in sections_requested:
        sections_requested.append("partners")
    if safe_bool(llm_ctx.get("wants_countdown")) and "countdown" not in sections_requested:
        sections_requested.append("countdown")
    if safe_bool(llm_ctx.get("wants_video")) and "video" not in sections_requested:
        sections_requested.append("video")

    return {
        "business_name":      safe_str(llm_ctx.get("business_name")),
        "niche":              safe_str(llm_ctx.get("niche"), "negocios"),
        "business_type":      safe_str(llm_ctx.get("business_type"), "Empresa"),
        "services":           safe_list(llm_ctx.get("services"))[:6],
        "address":            safe_str(llm_ctx.get("address")),
        "schedule":           schedule,
        "phone":              safe_str(llm_ctx.get("phone")),
        "email":              safe_str(llm_ctx.get("email")),
        "wa":                 re.sub(r'\D', '', safe_str(llm_ctx.get("whatsapp", ""))) or "",
        "ig":                 safe_str(llm_ctx.get("instagram", "")).lstrip("@"),
        "location":           safe_str(llm_ctx.get("location")),
        "visual_style":       safe_str(llm_ctx.get("visual_style"), "moderno"),
        "communication_tone": safe_str(llm_ctx.get("tone"), "formal"),
        "colors":             [c for c in [primary_color, accent_color] if c],
        "audience":           safe_str(llm_ctx.get("target_audience"), "pessoas que buscam qualidade"),
        "differentials":      safe_list(llm_ctx.get("differentials"))[:5],
        "wants_map":          safe_bool(llm_ctx.get("wants_map")) or bool(safe_str(llm_ctx.get("address"))),
        "wants_form":         safe_bool(llm_ctx.get("wants_form"), True),
        "wants_faq":          safe_bool(llm_ctx.get("wants_faq")),
        "wants_gallery":      safe_bool(llm_ctx.get("wants_gallery")),
        "wants_pricing":      safe_bool(llm_ctx.get("wants_pricing")),
        "wants_video":        safe_bool(llm_ctx.get("wants_video")),
        "wants_countdown":    safe_bool(llm_ctx.get("wants_countdown")),
        "intention":          safe_str(llm_ctx.get("intention"), "captar leads"),
        "testimonial_count":  safe_int(llm_ctx.get("testimonial_count"), 3),
        "banner_count":       min(safe_int(llm_ctx.get("banner_count"), 1), 4),
        "form_fields":        form_fields,
        "sections_requested": sections_requested,
        "extra_info":         safe_str(llm_ctx.get("extra_info")),
        "past_patterns":      [],
        "original_prompt":    original_prompt,
    }

    schedule = []
    for item in safe_list(llm_ctx.get("schedule")):
        if isinstance(item, dict):
            schedule.append({
                "day": safe_str(item.get("day"), ""),
                "time": safe_str(item.get("time"), ""),
                "event": safe_str(item.get("event"), ""),
            })

    primary_color = safe_str(llm_ctx.get("primary_color"))
    accent_color = safe_str(llm_ctx.get("accent_color"))
    if primary_color and not primary_color.startswith("#"):
        primary_color = COLOR_NAMES.get(primary_color.lower(), "")
    if accent_color and not accent_color.startswith("#"):
        accent_color = COLOR_NAMES.get(accent_color.lower(), "")

    form_fields = ["Nome", "E-mail"]
    pl = original_prompt.lower()
    if any(w in pl for w in ["telefone", "celular", "whatsapp", "fone", "zap"]):
        form_fields.append("Telefone/WhatsApp")
    if any(w in pl for w in ["empresa", "cnpj"]):
        form_fields.append("Empresa")
    if any(w in pl for w in ["mensagem", "assunto", "duvida"]):
        form_fields.append("Mensagem")
    if any(w in pl for w in ["data", "horario", "agendamento"]):
        form_fields.append("Data preferida")

    return {
        "business_name": safe_str(llm_ctx.get("business_name")),
        "niche": safe_str(llm_ctx.get("niche"), "negocios"),
        "business_type": safe_str(llm_ctx.get("business_type"), "Empresa"),
        "services": safe_list(llm_ctx.get("services"))[:6],
        "address": safe_str(llm_ctx.get("address")),
        "schedule": schedule,
        "phone": safe_str(llm_ctx.get("phone")),
        "email": safe_str(llm_ctx.get("email")),
        "wa": re.sub(r'\D', '', safe_str(llm_ctx.get("whatsapp", ""))) or "",
        "ig": safe_str(llm_ctx.get("instagram", "")).lstrip("@"),
        "location": safe_str(llm_ctx.get("location")),
        "visual_style": safe_str(llm_ctx.get("visual_style"), "moderno"),
        "communication_tone": safe_str(llm_ctx.get("tone"), "formal"),
        "colors": [c for c in [primary_color, accent_color] if c],
        "audience": safe_str(llm_ctx.get("target_audience"), "pessoas que buscam qualidade"),
        "differentials": safe_list(llm_ctx.get("differentials"))[:4],
        "wants_map": safe_bool(llm_ctx.get("wants_map")) or bool(safe_str(llm_ctx.get("address"))),
        "wants_form": safe_bool(llm_ctx.get("wants_form"), True),
        "wants_faq": safe_bool(llm_ctx.get("wants_faq")),
        "wants_gallery": safe_bool(llm_ctx.get("wants_gallery")),
        "wants_pricing": safe_bool(llm_ctx.get("wants_pricing")),
        "intention": safe_str(llm_ctx.get("intention"), "captar leads"),
        "testimonial_count": safe_int(llm_ctx.get("testimonial_count"), 3),
        "form_fields": form_fields,
        "banner_count": 1,
        "sections_requested": [],
        "extra_info": safe_str(llm_ctx.get("extra_info")),
        "past_patterns": [],
        "original_prompt": original_prompt,
    }


def extract_context_async(
    prompt: str,
    result_holder: list,
    niche_hint: str = "",
    timeout: float = 85.0,
) -> threading.Thread:
    """
    Run LLM extraction in a background thread with few-shot context.
    niche_hint is passed from the regex parser to guide example selection.
    """
    def _run():
        try:
            raw = extract_context_with_llm(prompt, niche_hint=niche_hint)
            if raw:
                result_holder.append(normalize_llm_context(raw, prompt))
        except Exception as e:
            logger.warning("Async LLM extraction error: %s", e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
