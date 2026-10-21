"""
WTech Landing Page Generator - Intelligent Generation Worker
Reads the full prompt, learns from past generations, builds unique landing pages.
"""
from __future__ import annotations
import json, logging, re, uuid
from datetime import datetime, timezone
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.generation_worker.run_generation_pipeline",
    bind=True, max_retries=2, default_retry_delay=30, queue="generation_jobs",
)
def run_generation_pipeline(self, job_id, prompt, project_id, brand_color=None, accent_color=None, logo_url=None, user_id=None):
    from app.database import get_db_session
    with get_db_session() as db:
        _upd(db, job_id, "processing", "interpretando", 0.10)
        try:
            # ── Step 1: Parse prompt (regex + LLM in parallel) ────────────
            _upd(db, job_id, "processing", "analisando prompt com IA", 0.15)
            ctx = _parse_prompt_smart(prompt)

            # ── Step 2: Check if free-form LLM generation is better ───────
            from app.services.llm_html_generator import is_free_form_prompt, generate_html_free_form
            if is_free_form_prompt(prompt, ctx.get("niche", "negocios")):
                _upd(db, job_id, "processing", "gerando pagina com IA (modo livre)", 0.30)
                logger.info("Free-form LLM generation for niche='%s'", ctx.get("niche"))
                result = generate_html_free_form(prompt, brand_color, accent_color, logo_url)
                if result:
                    html, css = result
                    # Build a minimal structured record for training/analytics
                    name = ctx.get("business_name") or ctx.get("business_type") or "Pagina"
                    structured = {
                        "headline": name,
                        "sections": ["free-form"],
                        "niche": ctx.get("niche", "negocios"),
                        "style": ctx.get("visual_style", "moderno"),
                        "mode": "llm_free_form",
                    }
                    _save(db, job_id, project_id, structured, html, css)
                    _save_training(db, prompt, json.dumps(structured))
                    _upd(db, job_id, "completed", "concluido", 1.0)
                    try:
                        from app.services.analytics_service import record_event
                        record_event(db, "generation_completed", user_id=user_id,
                                     project_id=project_id, job_id=job_id)
                    except Exception:
                        pass
                    return {"job_id": job_id, "status": "completed", "mode": "llm_free_form"}
                else:
                    logger.info("Free-form LLM unavailable — falling back to template pipeline")

            # ── Step 3: Template pipeline (known niches) ──────────────────
            _upd(db, job_id, "processing", "consultando base de conhecimento", 0.35)
            past = _load_past(db, ctx["niche"])
            learned = _load_learned_patterns(db, ctx["niche"])
            ctx["past_patterns"] = past
            ctx["learned_patterns"] = learned
            _upd(db, job_id, "processing", "gerando conteudo", 0.40)
            copy = generate_copy(ctx)
            design = generate_design(ctx, brand_color, accent_color)
            _upd(db, job_id, "processing", "montando layout", 0.60)
            sections = build_sections(ctx)
            _upd(db, job_id, "processing", "renderizando", 0.80)
            html, css = render_html(ctx, copy, design, sections, logo_url=logo_url)
            structured = {"headline": copy["headline"], "sections": [s["type"] for s in sections],
                          "niche": ctx["niche"], "style": ctx["visual_style"]}
            _save(db, job_id, project_id, structured, html, css)
            _save_training(db, prompt, json.dumps(structured))
            _upd(db, job_id, "completed", "concluido", 1.0)
            try:
                from app.services.analytics_service import record_event
                record_event(db, "generation_completed", user_id=user_id, project_id=project_id, job_id=job_id)
            except Exception:
                pass
            return {"job_id": job_id, "status": "completed"}
        except Exception as exc:
            logger.error("Generation failed %s: %s", job_id, exc, exc_info=True)
            _upd(db, job_id, "failed", error=str(exc))
            try:
                raise self.retry(exc=exc)
            except self.MaxRetriesExceededError:
                raise


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT PARSER
# ══════════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════════
# NICHE TAXONOMY — 150+ sub-niches mapped to ~60 categories
# Ordered most-specific → most-generic so first match wins.
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# NICHE TAXONOMY — 150+ sub-niches mapped to ~60 categories
# Ordered most-specific → most-generic so first match wins.
# ══════════════════════════════════════════════════════════════════════════════
NICHES: list[tuple[str, str, str]] = [
    # SAÚDE
    (r"ortodont|aparelho\s+dental|invisalign|braces", "ortodontia", "Ortodontista"),
    (r"harmoniza[cç][aã]o\s+facial|bichectomia|preenchimento\s+labial|toxina\s+botul", "harmonizacao facial", "Clinica de Harmonizacao Facial"),
    (r"odontolog|dentist|implante\s+dent|clareamento\s+dent|faceta|canal\s+dent|protese\s+dent", "odontologia", "Clinica Odontologica"),
    (r"dermatolog|acne|botox\s+medic|laser\s+medic|tratamento\s+capilar\s+medic", "dermatologia", "Dermatologista"),
    (r"psiquiatr|medicamento\s+psiquiatric|transtorno\s+mental|tdah|bipolar", "psiquiatria", "Psiquiatra"),
    (r"psicolog|terapia\s+cognitiva|psicanalis|saude\s+mental|ansiedade|depressao|burnout", "psicologia", "Psicologo"),
    (r"fisioterapia|fisioterapeuta|reabilita[cç][aã]o|lesao\s+esportiva|coluna", "fisioterapia", "Clinica de Fisioterapia"),
    (r"quiroprax|quiropraxia|ajuste\s+vertebral", "quiropraxia", "Quiropraxista"),
    (r"nutricion|nutri[cç][aã]o|dieta|emagrecimento|plano\s+alimentar", "nutricao", "Nutricionista"),
    (r"pediatr|crianca\s+medic|saude\s+infantil", "pediatria", "Pediatra"),
    (r"cardiolog|cora[cç][aã]o|hipertens[aã]o|arritmia", "cardiologia", "Cardiologista"),
    (r"ginecolog|obstetr|prenatal|parto|ginecologia", "ginecologia", "Ginecologista"),
    (r"oftalmolog|visao|olhos|miopia|catarata|glaucoma", "oftalmologia", "Oftalmologista"),
    (r"fertilidade|reprodu[cç][aã]o\s+assistida|fiv|insemina[cç][aã]o", "fertilidade", "Clinica de Fertilidade"),
    (r"acupuntura|medicina\s+tradicional\s+chinesa|auriculoterapia", "acupuntura", "Acupunturista"),
    (r"rpg\s+fisio|reeducacao\s+postural", "rpg", "Clinica de RPG"),
    (r"pilates\s+clinico|pilates\s+reabilita", "pilates clinico", "Studio de Pilates Clinico"),
    (r"terapia\s+alternativa|homeopatia|florais|reiki|ayurveda", "terapias alternativas", "Terapeuta Alternativo"),
    (r"laboratorio|exame\s+laboratorial|analise\s+clinica|coleta\s+de\s+sangue", "laboratorio", "Laboratorio de Analises"),
    (r"clinica\s+popular|consulta\s+popular", "clinica popular", "Clinica Popular"),
    (r"medico|hospital|clinica|consulta\s+medica|exame\s+medico|saude", "saude", "Clinica de Saude"),
    # ESTÉTICA / BELEZA
    (r"lash\s+design|cilios|extensao\s+de\s+cilios", "lash design", "Lash Designer"),
    (r"nail\s+design|unhas\s+gel|unhas\s+acrilicas|nail\s+art", "nail design", "Nail Designer"),
    (r"sobrancelha|design\s+de\s+sobrancelha|micropigmenta[cç][aã]o", "sobrancelhas", "Designer de Sobrancelhas"),
    (r"maquiadora|maquiagem|make\s+up|maquiagem\s+profissional", "maquiagem", "Maquiadora Profissional"),
    (r"barbearia|barba|barbeiro|corte\s+masculino", "barbearia", "Barbearia"),
    (r"bronzeamento|cama\s+solar|autobronzeador", "bronzeamento", "Studio de Bronzeamento"),
    (r"depila[cç][aã]o|laser\s+depila|cera\s+depila", "depilacao", "Studio de Depilacao"),
    (r"estetica\s+corporal|massagem\s+modeladora|drenagem|celulite|gordura\s+localizada", "estetica corporal", "Clinica de Estetica Corporal"),
    (r"botox\s+estetico|preenchimento\s+estetico|procedimento\s+facial|skincare\s+clinica", "procedimentos esteticos", "Clinica Estetica"),
    (r"skincare|cuidados\s+com\s+a\s+pele|rotina\s+de\s+beleza|cosmetico", "skincare", "Marca de Skincare"),
    (r"farmacia|drogaria|medicamento\s+loja|remedio\s+loja|manipulacao\s+farmac|farmaceut", "farmacia", "Farmacia"),
    (r"perfumaria|perfume|fragranc", "perfumaria", "Perfumaria"),
    (r"spa\b|massagem\s+relaxante|day\s+spa|bem.estar", "spa", "Spa"),
    (r"salao|cabeleireiro|cabelo|coloracao|escova|progressiva|manicure|pedicure", "beleza", "Salao de Beleza"),
    # FITNESS
    (r"crossfit\b|box\s+crossfit|wod\b", "crossfit", "Box de CrossFit"),
    (r"pilates\s+studio|studio\s+de\s+pilates|pilates\b", "pilates", "Studio de Pilates"),
    (r"yoga\b|meditacao|mindfulness", "yoga", "Studio de Yoga"),
    (r"personal\s+trainer|treinamento\s+personalizado|coach\s+fitness", "personal trainer", "Personal Trainer"),
    (r"nutri[cç][aã]o\s+esportiva|suplemento|whey|creatina|loja\s+suplemento", "suplementos", "Loja de Suplementos"),
    (r"corrida|running|maratona|trail\s+run", "corrida", "Assessoria de Corrida"),
    (r"ciclismo|bike|mtb|speed\b", "ciclismo", "Assessoria de Ciclismo"),
    (r"jiu.jitsu|bjj\b|jiu\s+jitsu", "jiu-jitsu", "Academia de Jiu-Jitsu"),
    (r"boxe\b|muay\s+thai|kickboxing", "boxe", "Academia de Boxe"),
    (r"artes\s+marciais|karate|judo|taekwondo|mma\b", "artes marciais", "Academia de Artes Marciais"),
    (r"academia|fitness|musculacao|ginastica|funcional\b|hiit\b", "fitness", "Academia"),
    # IMOBILIÁRIO
    (r"alto\s+padr[aã]o\s+imovel|imovel\s+luxo|mansao|cobertura", "imoveis alto padrao", "Imobiliaria de Alto Padrao"),
    (r"lancamento\s+imovel|imovel\s+na\s+planta|construtora\s+imovel", "lancamentos imoveis", "Lancamentos Imobiliarios"),
    (r"aluguel\s+temporada|airbnb|temporada\s+imovel", "aluguel temporada", "Aluguel por Temporada"),
    (r"consorcio\s+imovel|consorcio\s+imobiliario", "consorcio imovel", "Consorcio Imobiliario"),
    (r"imovel|apartamento|corretor|imobiliaria|aluguel|casa\s+a\s+venda|terreno", "imoveis", "Imobiliaria"),
    # FINANCEIRO
    (r"bpo\s+financeiro|terceirizacao\s+financeira", "bpo financeiro", "BPO Financeiro"),
    (r"holding\s+patrimonial|holding\s+familiar|planejamento\s+patrimonial", "holding", "Holding Patrimonial"),
    (r"imposto\s+de\s+renda|declaracao\s+ir|restituicao\s+ir", "imposto de renda", "Consultoria de IR"),
    (r"seguro\s+de\s+vida|seguro\s+auto|seguro\s+residencial|corretora\s+seguro", "seguros", "Corretora de Seguros"),
    (r"investimento|renda\s+fixa|acoes|bolsa\s+de\s+valores|tesouro\s+direto", "investimentos", "Consultoria de Investimentos"),
    (r"credito|emprestimo|financiamento\s+pessoal|consignado", "credito", "Financeira"),
    (r"contabilidade|contador|fiscal|tributario|imposto|folha\s+de\s+pagamento|abertura\s+empresa", "contabilidade", "Escritorio Contabil"),
    (r"planejamento\s+financeiro|educacao\s+financeira|coach\s+financeiro", "financas pessoais", "Consultoria Financeira Pessoal"),
    (r"financeiro|investimento|financas|credito|emprestimo", "financas", "Consultoria Financeira"),
    # TECNOLOGIA
    (r"saas\b|software\s+como\s+servico|plataforma\s+digital", "saas", "Empresa SaaS"),
    (r"chatbot|automacao\s+whatsapp|bot\s+atendimento", "chatbots", "Automacao com Chatbots"),
    (r"inteligencia\s+artificial|\bia\s+generativa|\bllm\b|machine\s+learning|deep\s+learning", "ia", "Empresa de IA"),
    (r"cybersecurity|seguranca\s+digital|pentest|lgpd", "cybersecurity", "Empresa de Cybersecurity"),
    (r"cloud\s+computing|aws\b|azure\b|gcp\b|infraestrutura\s+cloud", "cloud", "Empresa de Cloud"),
    (r"devops|ci.cd|kubernetes|docker\b", "devops", "Consultoria DevOps"),
    (r"blockchain|criptomoeda|web3|nft\b|defi\b", "blockchain", "Empresa de Blockchain"),
    (r"erp\b|crm\b|sistema\s+de\s+gestao|software\s+empresarial", "erp crm", "Software de Gestao"),
    (r"desenvolvimento\s+web|site\s+profissional|agencia\s+web", "desenvolvimento web", "Agencia Web"),
    (r"aplicativo|app\s+mobile|desenvolvimento\s+mobile|flutter|react\s+native", "app mobile", "Desenvolvimento Mobile"),
    (r"software\s+house|fabrica\s+de\s+software|desenvolvimento\s+software", "software house", "Software House"),
    (r"\btecnologia\b|\bsoftware\b|\bsistema\b|\bdesenvolvimento\b|\bprogramacao\b", "tecnologia", "Empresa de Tecnologia"),
    # EDUCAÇÃO
    (r"enem\b|vestibular|cursinho|pre.vestibular", "enem vestibular", "Cursinho Pre-Vestibular"),
    (r"concurso\s+publico|preparatorio\s+concurso|oab\b|residencia\s+medica", "concursos", "Preparatorio para Concursos"),
    (r"idioma|ingles|espanhol|frances|alemao|japones|mandarim", "idiomas", "Escola de Idiomas"),
    (r"ead\b|ensino\s+a\s+distancia|plataforma\s+ead", "ead", "Plataforma EAD"),
    (r"curso\s+online|infoproduto\s+educacional|curso\s+digital", "curso online", "Produtor de Cursos Online"),
    (r"mentoria\b|coaching\s+profissional|coach\s+de\s+carreira", "mentoria", "Mentor Profissional"),
    (r"treinamento\s+corporativo|capacitacao\s+empresarial", "treinamento corporativo", "Treinamento Corporativo"),
    (r"escola\b|colegio\b|ensino\s+fundamental|ensino\s+medio", "escola", "Escola"),
    (r"faculdade|universidade|pos.graduacao|mba\b|especializacao", "faculdade", "Faculdade"),
    (r"aula\s+particular|professor\s+particular|reforco\s+escolar", "aulas particulares", "Professor Particular"),
    (r"educacao|escola|faculdade|treinamento|mentoria|aula\s+de", "educacao", "Escola"),
    # MARKETING
    (r"gestao\s+de\s+trafego|trafego\s+pago|google\s+ads|meta\s+ads|facebook\s+ads", "trafego pago", "Gestor de Trafego"),
    (r"social\s+media|gestao\s+redes\s+sociais|instagram\s+marketing", "social media", "Gestao de Redes Sociais"),
    (r"copywriting|copy\b|redacao\s+publicitaria", "copywriting", "Copywriter"),
    (r"branding|identidade\s+visual|marca\s+profissional", "branding", "Agencia de Branding"),
    (r"seo\b|otimizacao\s+para\s+buscadores|posicionamento\s+google", "seo", "Consultoria SEO"),
    (r"producao\s+de\s+video|videomaker|edicao\s+de\s+video", "video marketing", "Producao de Video"),
    (r"growth\s+hacking|growth\s+marketing|growth\b", "growth", "Growth Marketing"),
    (r"lancamento\s+digital|lancamento\s+produto|funil\s+de\s+vendas", "lancamentos", "Especialista em Lancamentos"),
    (r"marketing|agencia\s+digital|publicidade", "marketing", "Agencia de Marketing"),
    # JURÍDICO
    (r"direito\s+previdenciario|inss\b|aposentadoria\s+juridica|beneficio\s+inss", "direito previdenciario", "Advogado Previdenciario"),
    (r"direito\s+trabalhista|reclamacao\s+trabalhista|rescisao\s+contrato", "direito trabalhista", "Advogado Trabalhista"),
    (r"direito\s+tributario|planejamento\s+tributario\s+juridico", "direito tributario", "Advogado Tributarista"),
    (r"direito\s+criminal|defesa\s+criminal|advogado\s+criminal", "direito criminal", "Advogado Criminalista"),
    (r"direito\s+familia|divorcio|guarda\s+filhos|pensao\s+alimenticia", "direito familia", "Advogado de Familia"),
    (r"direito\s+empresarial|contrato\s+empresarial|societario", "direito empresarial", "Advogado Empresarial"),
    (r"holding\s+familiar\s+juridica|planejamento\s+sucessorio", "holding familiar", "Holding Familiar"),
    (r"advocacia|advogado|juridico|direito", "juridico", "Escritorio de Advocacia"),
    # AUTOMOTIVO
    (r"estetica\s+automotiva|polimento|vitrificacao|cristalizacao", "estetica automotiva", "Estetica Automotiva"),
    (r"insulfilm|peliculas\s+automotivas|blindagem", "insulfilm", "Instalacao de Insulfilm"),
    (r"som\s+automotivo|multimidia\s+automotiva|alarme\s+carro", "som automotivo", "Som Automotivo"),
    (r"martelinho\s+de\s+ouro|funilaria\s+sem\s+pintura", "martelinho ouro", "Martelinho de Ouro"),
    (r"funilaria|pintura\s+automotiva|lataria", "funilaria", "Funilaria e Pintura"),
    (r"auto\s+eletrica|eletrica\s+automotiva|injecao\s+eletronica", "auto eletrica", "Auto Eletrica"),
    (r"lava\s+rapido|lavagem\s+automotiva|higienizacao\s+interna", "lava rapido", "Lava Rapido"),
    (r"rastreamento|rastreador\s+veicular|monitoramento\s+frota", "rastreamento", "Rastreamento Veicular"),
    (r"guincho|reboque|socorro\s+mecanico", "guincho", "Guincho e Socorro"),
    (r"locadora|aluguel\s+de\s+carro|rent\s+a\s+car", "locadora", "Locadora de Veiculos"),
    (r"venda\s+de\s+veiculo|concessionaria|seminovo|usados", "venda veiculos", "Concessionaria"),
    (r"oficina|mecanica|revisao\s+carro|troca\s+oleo|pneu", "oficina", "Oficina Mecanica"),
    # CONSTRUÇÃO CIVIL
    (r"energia\s+solar|painel\s+solar|fotovoltaico|placa\s+solar", "energia solar", "Energia Solar"),
    (r"piscina|construcao\s+piscina|reforma\s+piscina", "piscinas", "Construcao de Piscinas"),
    (r"marcenaria|moveis\s+sob\s+medida|marceneiro", "marcenaria", "Marcenaria"),
    (r"moveis\s+planejados|cozinha\s+planejada|closet\s+planejado", "moveis planejados", "Moveis Planejados"),
    (r"marmoraria|granito|marmore|pedra\s+natural", "marmoraria", "Marmoraria"),
    (r"vidracaria|vidro\s+temperado|esquadria\s+aluminio", "vidracaria", "Vidracaria"),
    (r"pintura\s+predial|pintura\s+residencial|pintor", "pintura", "Pintura Residencial"),
    (r"eletrica\s+residencial|instalacao\s+eletrica|eletricista", "eletrica", "Eletricista"),
    (r"hidraulica|encanamento|encanador|instalacao\s+hidraulica", "hidraulica", "Hidraulica"),
    (r"reforma\s+residencial|reforma\s+comercial|reformas", "reformas", "Empresa de Reformas"),
    (r"designer\s+de\s+interiores|decoracao\s+de\s+interiores|arquitetura\s+de\s+interiores", "design interiores", "Designer de Interiores"),
    (r"material(?:is)?\s+(?:de\s+)?constru[cç][aã]o|loja\s+constru[cç][aã]o|ferragem|cimento\s+loja|tijolo\s+loja|loja\s+de\s+materiais", "loja construcao", "Loja de Materiais de Construcao"),
    (r"arquitetura|arquiteto|projeto\s+arquitetonico", "arquitetura", "Escritorio de Arquitetura"),
    (r"engenharia|construcao|construtora|obra\b", "construcao", "Construtora"),
    # CASA / SERVIÇOS DOMÉSTICOS
    (r"dedetizacao|controle\s+de\s+pragas|fumigacao", "dedetizacao", "Dedetizadora"),
    (r"limpeza\s+residencial|faxina|diarista|limpeza\s+comercial", "limpeza", "Empresa de Limpeza"),
    (r"jardinagem|paisagismo|jardim\s+vertical|grama", "jardinagem", "Jardinagem e Paisagismo"),
    (r"mudanca|transportadora\s+residencial|frete\s+mudanca", "mudancas", "Empresa de Mudancas"),
    (r"seguranca\s+residencial|alarme\s+residencial|camera\s+seguranca", "seguranca residencial", "Seguranca Residencial"),
    (r"automacao\s+residencial|casa\s+inteligente|smart\s+home", "automacao residencial", "Automacao Residencial"),
    (r"decoracao\s+residencial|decoradora|home\s+staging", "decoracao", "Decoracao Residencial"),
    (r"organizacao\s+residencial|personal\s+organizer", "organizacao", "Personal Organizer"),
    # EVENTOS
    (r"casamento|wedding\s+planner|cerimonial\s+casamento", "casamentos", "Cerimonial de Casamentos"),
    (r"formatura|festa\s+de\s+formatura|colacao\s+de\s+grau", "formaturas", "Cerimonial de Formaturas"),
    (r"\bdj\b|disc\s+jockey|sonorizacao\s+evento", "dj", "DJ Profissional"),
    (r"buffet\b|catering\s+evento|gastronomia\s+evento", "buffet", "Buffet de Eventos"),
    (r"fotografo\s+evento|fotografia\s+evento|ensaio\s+fotografico", "fotografia", "Fotografo"),
    (r"filmagem\s+evento|videomaker\s+evento|cinematografia", "filmagem", "Filmagem de Eventos"),
    (r"decoracao\s+festa|decoracao\s+evento|baloes|cenografia", "decoracao festas", "Decoracao de Festas"),
    (r"evento\s+corporativo|congresso|conferencia\s+evento|summit\b", "eventos corporativos", "Eventos Corporativos"),
    (r"cerimonial|assessoria\s+evento|organizacao\s+evento", "cerimonial", "Cerimonial de Eventos"),
    # ALIMENTAÇÃO
    (r"hamburgueria|hamburguer\s+artesanal|smash\s+burger", "hamburgueria", "Hamburgueria"),
    (r"pizzaria|pizza\s+artesanal|pizza\s+napolitana", "pizzaria", "Pizzaria"),
    (r"delivery\b|marmita|comida\s+congelada|refeicao\s+delivery", "delivery", "Delivery de Comida"),
    (r"cafeteria|cafe\s+especial|coffee\s+shop|barista", "cafeteria", "Cafeteria"),
    (r"doceria|confeitaria|bolo\s+personalizado|cake\s+design", "confeitaria", "Confeitaria"),
    (r"sorveteria|gelato|acai\b", "sorveteria", "Sorveteria"),
    (r"food\s+truck|trailer\s+de\s+comida", "food truck", "Food Truck"),
    (r"restaurante|gastronomia|almoco|jantar|culinaria", "gastronomia", "Restaurante"),
    # E-COMMERCE / MODA — must come AFTER all specific store types
    (r"moda\s+feminina|roupa\s+feminina|vestido|blusa\s+feminina", "moda feminina", "Loja de Moda Feminina"),
    (r"moda\s+masculina|roupa\s+masculina|camisa\s+masculina", "moda masculina", "Loja de Moda Masculina"),
    (r"moda\s+infantil|roupa\s+infantil|kids\s+fashion|bebe\s+roupa", "moda infantil", "Loja de Moda Infantil"),
    (r"dropshipping|loja\s+dropship|revenda\s+online", "dropshipping", "Loja Dropshipping"),
    (r"marketplace|shopify|loja\s+virtual|e.commerce|venda\s+online", "e-commerce", "Loja Online"),
    (r"roupa|vestuario|fashion|boutique|moda\b|calcado|tenis|sapato|bolsa", "moda", "Loja de Moda"),
    # LOJAS ESPECIALIZADAS — must come before generic \bloja\b
    (r"auto\s*pe[cç]a|autopeca|peça\s+automotiva|acessorio\s+automotivo\s+loja", "autopecas", "Loja de Autopeças"),
    (r"farmacia|drogaria|medicamento\s+loja|remedio\s+loja", "farmacia", "Farmácia"),
    (r"papelaria|material\s+escolar|artigo\s+escritorio\s+loja", "papelaria", "Papelaria"),
    (r"livraria|livro\s+loja|literatura\s+loja", "livraria", "Livraria"),
    (r"informatica\s+loja|computador\s+loja|notebook\s+loja|celular\s+loja", "loja informatica", "Loja de Informática"),
    (r"floricult|flores\s+loja|arranjo\s+floral|buque", "floricultura", "Floricultura"),
    (r"optica|oculista|oculos\s+loja|lente\s+de\s+contato\s+loja", "optica", "Ótica"),
    (r"relojoaria|relogio\s+loja|joalheria|joias\s+loja|bijuteria\s+loja", "joalheria", "Joalheria"),
    (r"moveis\s+loja|loja\s+de\s+moveis|decoracao\s+loja|utilidade\s+domestica", "loja moveis", "Loja de Móveis"),
    (r"material\s+esportivo|equipamento\s+esportivo|loja\s+esport", "loja esportes", "Loja de Esportes"),
    (r"loja\s+de\s+brinquedo|brinquedo\s+loja|artigo\s+infantil\s+loja", "loja brinquedos", "Loja de Brinquedos"),
    (r"sex\s*shop|adult\s+store|produto\s+erotico", "sex shop", "Sex Shop"),
    # PET
    (r"hotel\s+pet|hospedagem\s+pet|creche\s+pet", "hotel pet", "Hotel para Pets"),
    (r"adestramento|adestrador|comportamento\s+animal", "adestramento", "Adestramento Animal"),
    (r"banho\s+e\s+tosa|pet\s+shop|grooming", "petshop", "Pet Shop"),
    (r"veterinario|clinica\s+veterinaria|cirurgia\s+veterinaria", "veterinaria", "Clinica Veterinaria"),
    # TURISMO
    (r"turismo\s+luxo|viagem\s+premium|resort\s+luxo", "turismo luxo", "Turismo de Luxo"),
    (r"intercambio|estudo\s+exterior|viagem\s+estudo", "intercambio", "Agencia de Intercambio"),
    (r"excursao|passeio\s+turistico|tour\s+guiado", "excursoes", "Agencia de Excursoes"),
    (r"pousada|hostel|hotel\b|hospedagem\b", "hospedagem", "Hospedagem"),
    (r"viagem|turismo|agencia\s+de\s+viagem|pacote\s+viagem", "turismo", "Agencia de Viagens"),
    # RH / INDUSTRIA
    (r"recrutamento|selecao|headhunter|rh\s+terceirizado|bpo\s+rh", "rh", "Consultoria de RH"),
    (r"logistica|transporte\s+carga|frete\s+carga|distribuidora", "logistica", "Logistica e Transporte"),
    (r"agronegocio|agricultura|fazenda|producao\s+rural|agro\b", "agronegocio", "Agronegocio"),
    (r"metalurgica|industria\s+metal|usinagem|soldagem", "metalurgica", "Metalurgica"),
    # INFOPRODUTOS / CRIADORES
    (r"ebook\b|livro\s+digital|material\s+digital", "ebook", "Produtor de Ebook"),
    (r"comunidade\s+online|grupo\s+pago|membership", "comunidade", "Comunidade Online"),
    (r"newsletter\s+premium|substack|boletim\s+pago", "newsletter", "Newsletter Premium"),
    (r"infoproduto|produto\s+digital|curso\s+online|mentoria\s+digital", "infoprodutos", "Produtor de Infoprodutos"),
    (r"youtuber|canal\s+youtube|criador\s+youtube", "youtube", "Canal do YouTube"),
    (r"podcaster|podcast\b", "podcast", "Podcast"),
    # RELIGIOSO
    (r"igreja\b|ministerio\b|congregacao|culto\b|evangelizacao", "igreja", "Igreja"),
    (r"curso\s+biblico|escola\s+biblica|teologia", "curso biblico", "Curso Biblico"),
    (r"musica\s+gospel|banda\s+gospel|cantor\s+gospel", "musica gospel", "Musica Gospel"),
    # GENÉRICO
    (r"consultoria|consultor|gestao\s+empresarial", "consultoria", "Consultoria"),
    (r"\bloja\b|e-commerce|venda\s+online", "e-commerce", "Loja Online"),
]

# Niche → default visual style
NICHE_DEFAULT_STYLE: dict[str, str] = {
    "odontologia": "corporativo", "ortodontia": "corporativo",
    "harmonizacao facial": "corporativo", "dermatologia": "corporativo",
    "psiquiatria": "minimalista", "psicologia": "minimalista",
    "fisioterapia": "corporativo", "saude": "corporativo",
    "cardiologia": "corporativo", "ginecologia": "corporativo",
    "fertilidade": "corporativo", "pediatria": "corporativo",
    "oftalmologia": "corporativo", "laboratorio": "corporativo",
    "lash design": "moderno", "nail design": "moderno",
    "sobrancelhas": "moderno", "maquiagem": "moderno",
    "barbearia": "agressivo", "bronzeamento": "moderno",
    "skincare": "minimalista", "spa": "minimalista",
    "beleza": "moderno", "estetica corporal": "moderno",
    "crossfit": "agressivo", "boxe": "agressivo",
    "jiu-jitsu": "agressivo", "artes marciais": "agressivo",
    "fitness": "agressivo", "personal trainer": "agressivo",
    "pilates": "minimalista", "yoga": "minimalista",
    "imoveis alto padrao": "corporativo", "imoveis": "corporativo",
    "contabilidade": "corporativo", "financas": "corporativo",
    "holding": "corporativo", "investimentos": "corporativo",
    "seguros": "corporativo", "bpo financeiro": "corporativo",
    "saas": "moderno", "tecnologia": "moderno",
    "ia": "moderno", "cybersecurity": "corporativo",
    "software house": "moderno", "desenvolvimento web": "moderno",
    "juridico": "corporativo", "direito trabalhista": "corporativo",
    "direito previdenciario": "corporativo",
    "oficina": "agressivo", "funilaria": "agressivo",
    "estetica automotiva": "moderno",
    "energia solar": "moderno", "construcao": "corporativo",
    "arquitetura": "minimalista", "design interiores": "minimalista",
    "moveis planejados": "minimalista",
    "gastronomia": "moderno", "hamburgueria": "agressivo",
    "pizzaria": "moderno", "cafeteria": "minimalista",
    "confeitaria": "moderno", "sorveteria": "moderno",
    "moda feminina": "moderno", "moda masculina": "moderno",
    "moda": "moderno",
    "infoprodutos": "moderno", "curso online": "moderno",
    "mentoria": "corporativo", "lancamentos": "agressivo",
    "igreja": "minimalista", "musica gospel": "moderno",
    "casamentos": "minimalista", "fotografia": "minimalista",
    "turismo luxo": "corporativo", "turismo": "moderno",
}

# Niche → default audience
NICHE_AUDIENCE: dict[str, str] = {
    "odontologia": "pacientes que valorizam saude bucal e estetica",
    "ortodontia": "pacientes que buscam alinhamento dental",
    "harmonizacao facial": "pessoas que buscam realcar a beleza natural",
    "dermatologia": "pessoas que cuidam da saude e estetica da pele",
    "psicologia": "pessoas que buscam equilibrio emocional e saude mental",
    "psiquiatria": "pacientes que precisam de suporte psiquiatrico especializado",
    "fisioterapia": "pacientes em reabilitacao e prevencao de lesoes",
    "nutricao": "pessoas que buscam saude atraves da alimentacao",
    "saude": "pacientes que buscam saude e qualidade de vida",
    "fitness": "pessoas que buscam saude, estetica e performance",
    "crossfit": "atletas e entusiastas de alta performance",
    "personal trainer": "pessoas que buscam resultados rapidos e personalizados",
    "pilates": "pessoas que buscam saude postural e bem-estar",
    "yoga": "pessoas que buscam equilibrio corpo e mente",
    "beleza": "pessoas que valorizam cuidados pessoais e autoestima",
    "barbearia": "homens que valorizam grooming e estilo",
    "lash design": "mulheres que valorizam olhar marcante",
    "skincare": "pessoas que investem em cuidados com a pele",
    "imoveis": "pessoas e familias que buscam o imovel ideal",
    "imoveis alto padrao": "investidores e compradores de alto padrao",
    "contabilidade": "empresas e profissionais autonomos",
    "financas": "pessoas e empresas que buscam saude financeira",
    "investimentos": "investidores que buscam rentabilidade e seguranca",
    "seguros": "pessoas e empresas que buscam protecao patrimonial",
    "tecnologia": "empresas e empreendedores digitais",
    "saas": "empresas que buscam solucoes digitais escalaveis",
    "ia": "empresas que querem automatizar e inovar com IA",
    "educacao": "profissionais em busca de crescimento e qualificacao",
    "curso online": "pessoas que querem aprender no proprio ritmo",
    "idiomas": "pessoas que querem se comunicar em outro idioma",
    "marketing": "empresas que querem crescer no digital",
    "trafego pago": "empresas que querem mais clientes via anuncios",
    "juridico": "pessoas e empresas que precisam de suporte juridico",
    "oficina": "proprietarios de veiculos que buscam qualidade e confianca",
    "construcao": "pessoas e empresas que precisam de obras de qualidade",
    "loja construcao": "construtores, engenheiros, arquitetos e autoempreendedores",
    "autopecas": "proprietarios de veiculos, mecanicos e frotas",
    "farmacia": "pessoas que buscam saude, bem-estar e cosmeticos",
    "optica": "pessoas que precisam de oculos de grau ou sol",
    "floricultura": "pessoas que querem presentear ou decorar com flores",
    "loja moveis": "pessoas que estao montando ou renovando seus espacos",
    "arquitetura": "pessoas que buscam projetos funcionais e esteticamente belos",
    "energia solar": "proprietarios que querem economizar na conta de luz",
    "gastronomia": "pessoas que apreciam boa gastronomia",
    "hamburgueria": "amantes de hamburguer artesanal de qualidade",
    "moda feminina": "mulheres que valorizam estilo e qualidade",
    "moda masculina": "homens que valorizam estilo e qualidade",
    "e-commerce": "compradores online que buscam qualidade e praticidade",
    "infoprodutos": "pessoas que querem aprender e transformar suas vidas",
    "lancamentos": "pessoas prontas para investir em transformacao",
    "turismo": "viajantes que buscam experiencias inesqueciveis",
    "casamentos": "noivos que sonham com o casamento perfeito",
    "fotografia": "pessoas que querem eternizar momentos especiais",
    "veterinaria": "tutores que tratam seus pets como familia",
    "petshop": "tutores que buscam o melhor para seus pets",
    "igreja": "pessoas que buscam fe, comunidade e proposito",
}

# Niche → default differentials
NICHE_DIFFS: dict[str, list[str]] = {
    "odontologia": ["tecnologia de ponta", "profissionais especializados"],
    "ortodontia": ["tratamento personalizado", "tecnologia digital"],
    "harmonizacao facial": ["resultados naturais", "profissionais certificados"],
    "dermatologia": ["diagnostico preciso", "tratamentos avancados"],
    "psicologia": ["ambiente acolhedor", "abordagem humanizada"],
    "psiquiatria": ["atendimento sigiloso", "tratamento individualizado"],
    "fisioterapia": ["reabilitacao completa", "equipamentos modernos"],
    "nutricao": ["plano 100% personalizado", "acompanhamento continuo"],
    "saude": ["profissionais experientes", "atendimento humanizado"],
    "fitness": ["equipamentos modernos", "instrutores certificados"],
    "crossfit": ["coaches certificados", "comunidade motivadora"],
    "personal trainer": ["treino 100% personalizado", "resultados comprovados"],
    "pilates": ["instrutores certificados", "metodo original"],
    "yoga": ["ambiente tranquilo", "instrutores experientes"],
    "beleza": ["produtos de qualidade", "profissionais especializados"],
    "barbearia": ["ambiente masculino exclusivo", "produtos premium"],
    "skincare": ["formulacao dermatologicamente testada", "ingredientes ativos"],
    "imoveis": ["carteira exclusiva de imoveis", "atendimento personalizado"],
    "imoveis alto padrao": ["exclusividade e privacidade", "atendimento VIP"],
    "contabilidade": ["conformidade fiscal garantida", "atendimento especializado"],
    "financas": ["planejamento personalizado", "resultados comprovados"],
    "investimentos": ["carteira diversificada", "gestao profissional"],
    "seguros": ["melhor custo-beneficio", "atendimento 24h"],
    "tecnologia": ["solucoes inovadoras", "suporte especializado"],
    "saas": ["escalabilidade garantida", "suporte dedicado"],
    "ia": ["tecnologia de ponta", "resultados mensuraveis"],
    "marketing": ["resultados mensuraveis", "estrategia personalizada"],
    "trafego pago": ["ROI comprovado", "gestao transparente"],
    "lancamentos": ["metodologia comprovada", "resultados expressivos"],
    "juridico": ["experiencia comprovada", "atendimento personalizado"],
    "oficina": ["diagnostico preciso", "garantia nos servicos"],
    "energia solar": ["economia garantida", "instalacao certificada"],
    "loja construcao": ["Cimento e Argamassa", "Tijolos e Blocos", "Ferragens e Parafusos",
        "Tintas e Revestimentos", "Madeiras e Compensados", "Material Eletrico e Hidraulico",
        "Ferramentas e Equipamentos", "Telhas e Coberturas"],
    "autopecas": ["Pecas de Motor", "Freios e Suspensao", "Eletrica Automotiva",
        "Filtros e Oleos", "Embreagem e Cambio", "Acessorios Automotivos", "Pneus e Rodas"],
    "farmacia": ["Medicamentos Sob Receita", "Medicamentos OTC", "Perfumaria e Cosmeticos",
        "Vitaminas e Suplementos", "Produtos para Bebe", "Manipulacao de Formulas"],
    "optica": ["Oculos de Grau", "Oculos de Sol", "Lentes de Contato",
        "Exame de Vista", "Armacoes Premium", "Lentes Progressivas"],
    "floricultura": ["Arranjos Florais", "Buques para Presente", "Plantas Ornamentais",
        "Flores para Casamento", "Decoracao Floral Corporativa"],
    "loja moveis": ["Sala de Estar", "Quarto Casal", "Cozinha Planejada",
        "Escritorio", "Colchoes e Box", "Decoracao e Utilidades"],
    "construcao": ["Construcao Residencial", "Construcao Comercial", "Reforma Completa",
        "Projeto Estrutural", "Gerenciamento de Obra", "Fundacao e Estrutura"],
    "papelaria": ["Material Escolar", "Material de Escritorio", "Impressao e Copia",
        "Embalagens", "Artigos para Presente", "Plotter e Plotagem"],
    "loja esportes": ["Roupas Esportivas", "Calcados para Esporte", "Equipamentos Academia",
        "Futebol e Society", "Natacao e Corrida", "Artes Marciais"],
    "arquitetura": ["projetos exclusivos", "atencao aos detalhes"],
    "gastronomia": ["ingredientes frescos", "receitas exclusivas"],
    "moda feminina": ["pecas exclusivas", "qualidade premium"],
    "e-commerce": ["entrega rapida", "compra segura"],
    "infoprodutos": ["metodologia comprovada", "suporte completo"],
    "turismo": ["roteiros exclusivos", "atendimento personalizado"],
    "casamentos": ["dia perfeito garantido", "atencao a cada detalhe"],
    "fotografia": ["fotos que contam historias", "equipamentos profissionais"],
    "veterinaria": ["equipe especializada", "ambiente seguro e acolhedor"],
    "petshop": ["produtos premium", "profissionais que amam animais"],
    "educacao": ["metodologia comprovada", "professores qualificados"],
    "idiomas": ["metodo comunicativo", "professores nativos"],
    "igreja": ["comunidade acolhedora", "mensagem transformadora"],
    "consultoria": ["experiencia de mercado", "resultados mensuraveis"],
}

# Niche → services
SERVICE_DB: dict[str, list[str]] = {
    "odontologia": ["Implante Dentario", "Clareamento Dental", "Ortodontia", "Protese Dentaria", "Limpeza Dental", "Faceta de Porcelana", "Tratamento de Canal"],
    "ortodontia": ["Aparelho Metalico", "Aparelho Estetico", "Invisalign", "Contencao Dental", "Expansao Palatina"],
    "harmonizacao facial": ["Toxina Botulinica", "Preenchimento Labial", "Bichectomia", "Rinomodelacao", "Fios de PDO", "Bioestimuladores"],
    "dermatologia": ["Tratamento de Acne", "Peeling Quimico", "Laser CO2", "Botox Medico", "Tratamento de Manchas", "Dermatoscopia"],
    "psicologia": ["Psicoterapia Individual", "Terapia de Casal", "Terapia Infantil", "Terapia Cognitivo-Comportamental", "Terapia Online"],
    "psiquiatria": ["Consulta Psiquiatrica", "Tratamento de Ansiedade", "Tratamento de Depressao", "TDAH Adulto", "Telepsiquiatria"],
    "fisioterapia": ["Fisioterapia Ortopedica", "Fisioterapia Esportiva", "RPG", "Pilates Clinico", "Dry Needling", "Reabilitacao Pos-Cirurgica"],
    "nutricao": ["Consulta Nutricional", "Plano Alimentar Personalizado", "Nutricao Esportiva", "Emagrecimento Saudavel", "Reeducacao Alimentar"],
    "saude": ["Consulta Medica", "Check-up Completo", "Exames Laboratoriais", "Telemedicina", "Prevencao e Saude"],
    "cardiologia": ["Consulta Cardiologica", "Eletrocardiograma", "Ecocardiograma", "Holter 24h", "Teste Ergometrico"],
    "ginecologia": ["Consulta Ginecologica", "Pre-natal", "Colposcopia", "Ultrassom Obstetrico", "Planejamento Familiar"],
    "pediatria": ["Consulta Pediatrica", "Puericultura", "Vacinacao", "Desenvolvimento Infantil", "Telemedicina Pediatrica"],
    "oftalmologia": ["Consulta Oftalmologica", "Cirurgia Refrativa", "Tratamento de Glaucoma", "Catarata", "Lentes de Contato"],
    "fertilidade": ["FIV", "Inseminacao Artificial", "Congelamento de Ovulos", "Diagnostico de Infertilidade", "Estimulacao Ovariana"],
    "acupuntura": ["Acupuntura Tradicional", "Auriculoterapia", "Moxabustao", "Acupuntura Estetica", "Acupuntura para Dor"],
    "laboratorio": ["Hemograma Completo", "Exames Hormonais", "PCR e Sorologias", "Exames de Urina", "Coleta Domiciliar"],
    "lash design": ["Extensao de Cilios Fio a Fio", "Volume Russo", "Mega Volume", "Lash Lifting", "Coloracao de Cilios"],
    "nail design": ["Unhas em Gel", "Unhas Acrilicas", "Nail Art", "Manicure Classica", "Pedicure Spa"],
    "sobrancelhas": ["Design de Sobrancelha", "Micropigmentacao", "Henna de Sobrancelha", "Laminacao de Sobrancelha", "Brow Lifting"],
    "maquiagem": ["Maquiagem para Noivas", "Maquiagem para Festas", "Maquiagem Artistica", "Maquiagem Airbrush", "Curso de Maquiagem"],
    "barbearia": ["Corte Masculino", "Barba Completa", "Pigmentacao de Barba", "Hidratacao Capilar", "Sobrancelha Masculina"],
    "beleza": ["Corte de Cabelo", "Coloracao", "Luzes e Mechas", "Escova Progressiva", "Manicure e Pedicure", "Tratamento Capilar"],
    "spa": ["Massagem Relaxante", "Massagem Pedras Quentes", "Aromaterapia", "Esfoliacao Corporal", "Tratamento Facial"],
    "estetica corporal": ["Drenagem Linfatica", "Massagem Modeladora", "Radiofrequencia", "Criolipólise", "Ultrassom Focalizado"],
    "procedimentos esteticos": ["Botox Estetico", "Preenchimento Facial", "Bioestimuladores", "Peeling", "Microagulhamento"],
    "skincare": ["Rotina de Skincare", "Hidratante Facial", "Protetor Solar", "Serum Vitamina C", "Acido Hialuronico"],
    "depilacao": ["Depilacao a Laser", "Depilacao com Cera", "Depilacao com Linha", "Depilacao Definitiva", "Depilacao Masculina"],
    "fitness": ["Musculacao", "Funcional", "HIIT", "Spinning", "Aulas Coletivas", "Avaliacao Fisica"],
    "crossfit": ["WOD Diario", "Olimpico", "Ginastica", "Levantamento de Peso", "Endurance", "Fundamentos CrossFit"],
    "pilates": ["Pilates Solo", "Pilates Aparelhos", "Pilates para Gestantes", "Pilates Clinico", "Pilates Online"],
    "yoga": ["Hatha Yoga", "Vinyasa Flow", "Yin Yoga", "Meditacao Guiada", "Yoga para Iniciantes"],
    "personal trainer": ["Treino Personalizado", "Avaliacao Fisica", "Planilha de Treino", "Acompanhamento Online", "Emagrecimento"],
    "suplementos": ["Whey Protein", "Creatina", "Pre-Treino", "BCAA", "Vitaminas e Minerais", "Proteina Vegana"],
    "corrida": ["Planilha de Corrida", "Assessoria Presencial", "Assessoria Online", "Preparacao para Maratona"],
    "jiu-jitsu": ["Jiu-Jitsu para Iniciantes", "Jiu-Jitsu Avancado", "Jiu-Jitsu Infantil", "Competicao", "Defesa Pessoal"],
    "boxe": ["Boxe para Iniciantes", "Muay Thai", "Kickboxing", "Boxe Feminino", "Boxe Infantil"],
    "artes marciais": ["Karate", "Judo", "Taekwondo", "MMA", "Defesa Pessoal", "Artes Marciais Infantil"],
    "imoveis": ["Venda de Imoveis", "Aluguel Residencial", "Avaliacao de Imoveis", "Financiamento Imobiliario", "Imoveis Comerciais"],
    "imoveis alto padrao": ["Apartamentos de Luxo", "Coberturas", "Casas em Condominio Fechado", "Consultoria Premium"],
    "contabilidade": ["Contabilidade Empresarial", "Declaracao de IR", "Abertura de Empresa", "Planejamento Tributario", "Folha de Pagamento"],
    "financas": ["Consultoria Financeira", "Planejamento Financeiro", "Investimentos", "Credito Pessoal", "Previdencia Privada"],
    "investimentos": ["Renda Fixa", "Acoes e FIIs", "Tesouro Direto", "Previdencia Privada", "Carteira Diversificada"],
    "seguros": ["Seguro de Vida", "Seguro Auto", "Seguro Residencial", "Seguro Empresarial", "Plano de Saude"],
    "bpo financeiro": ["Contas a Pagar e Receber", "Conciliacao Bancaria", "Relatorios Gerenciais", "Fluxo de Caixa"],
    "holding": ["Holding Patrimonial", "Holding Familiar", "Planejamento Sucessorio", "Protecao de Patrimonio"],
    "tecnologia": ["Desenvolvimento Web", "Aplicativo Mobile", "Sistema ERP", "Automacao de Processos", "Consultoria TI"],
    "saas": ["Plataforma SaaS", "Integracao via API", "Dashboard Analitico", "Automacao de Fluxos", "Suporte Dedicado"],
    "ia": ["Automacao com IA", "Chatbot Inteligente", "Analise de Dados", "Machine Learning", "IA Generativa"],
    "cybersecurity": ["Pentest", "Analise de Vulnerabilidades", "LGPD e Compliance", "SOC Gerenciado", "Treinamento em Seguranca"],
    "desenvolvimento web": ["Site Institucional", "Landing Page", "E-commerce", "Portal Web", "SEO Tecnico"],
    "app mobile": ["App iOS e Android", "App React Native", "App Flutter", "Prototipagem", "Publicacao nas Lojas"],
    "marketing": ["Gestao de Redes Sociais", "Trafego Pago", "SEO", "Branding", "Email Marketing", "Producao de Conteudo"],
    "trafego pago": ["Google Ads", "Meta Ads", "TikTok Ads", "Remarketing", "Otimizacao de Campanhas"],
    "social media": ["Gestao do Instagram", "Criacao de Conteudo", "Reels e Stories", "Calendario Editorial"],
    "seo": ["Auditoria SEO", "Otimizacao On-Page", "Link Building", "SEO Local", "SEO Tecnico"],
    "branding": ["Identidade Visual", "Logotipo", "Manual de Marca", "Naming", "Posicionamento de Marca"],
    "lancamentos": ["Funil de Vendas", "Lancamento Semente", "Lancamento Interno", "Lancamento Externo", "Webinar de Vendas"],
    "infoprodutos": ["Curso Online", "Ebook", "Mentoria em Grupo", "Comunidade Paga", "Assinatura Digital"],
    "juridico": ["Consultoria Juridica", "Processo Trabalhista", "Direito Civil", "Contratos", "Defesa Criminal"],
    "direito trabalhista": ["Reclamacao Trabalhista", "Rescisao Indireta", "Horas Extras", "Assedio Moral", "FGTS"],
    "direito previdenciario": ["Aposentadoria por Tempo", "Aposentadoria por Invalidez", "BPC/LOAS", "Revisao de Beneficio"],
    "oficina": ["Revisao Completa", "Troca de Oleo", "Alinhamento e Balanceamento", "Freios", "Suspensao"],
    "estetica automotiva": ["Polimento Tecnico", "Vitrificacao", "Cristalizacao", "Higienizacao Interna", "Lavagem Detalhada"],
    "energia solar": ["Projeto Solar Residencial", "Projeto Solar Comercial", "Instalacao de Paineis", "Monitoramento Online"],
    "construcao": ["Construcao Residencial", "Construcao Comercial", "Reforma Completa", "Projeto Estrutural"],
    "arquitetura": ["Projeto Arquitetonico", "Projeto de Interiores", "Projeto 3D", "Reforma e Ampliacao"],
    "design interiores": ["Projeto de Interiores", "Decoracao Residencial", "Decoracao Comercial", "Projeto 3D"],
    "moveis planejados": ["Cozinha Planejada", "Closet Planejado", "Home Office Planejado", "Dormitorio Planejado"],
    "gastronomia": ["Almoco Executivo", "Jantar a La Carte", "Delivery", "Buffet", "Experiencia Gastronomica"],
    "hamburgueria": ["Hamburguer Artesanal", "Smash Burger", "Combo Especial", "Batata Frita Artesanal", "Delivery"],
    "pizzaria": ["Pizza Artesanal", "Pizza Napolitana", "Pizza no Forno a Lenha", "Borda Recheada", "Delivery"],
    "cafeteria": ["Cafe Especial", "Cappuccino", "Cold Brew", "Croissant", "Brunch"],
    "confeitaria": ["Bolo Personalizado", "Cake Design", "Doces Finos", "Bem-Casados", "Cupcakes"],
    "moda feminina": ["Vestidos", "Blusas Femininas", "Calcas e Shorts", "Moda Praia", "Acessorios Femininos"],
    "moda masculina": ["Camisas Masculinas", "Calcas Jeans", "Ternos e Blazers", "Moda Casual", "Calcados Masculinos"],
    "moda infantil": ["Roupas para Bebes", "Roupas para Criancas", "Calcados Infantis", "Acessorios Infantis"],
    "moda": ["Roupas Femininas", "Roupas Masculinas", "Moda Infantil", "Calcados", "Acessorios"],
    "e-commerce": ["Produtos Online", "Entrega Rapida", "Frete Gratis", "Catalogo Digital", "Compra Segura"],
    "veterinaria": ["Consulta Veterinaria", "Vacinacao", "Cirurgia Veterinaria", "Exames Laboratoriais", "Emergencia 24h"],
    "petshop": ["Banho e Tosa", "Tosa Artistica", "Hidratacao Pet", "Perfumaria Pet", "Acessorios Pet"],
    "hotel pet": ["Hospedagem Individual", "Hospedagem em Suite", "Passeios Diarios", "Webcam ao Vivo"],
    "adestramento": ["Adestramento Basico", "Adestramento Avancado", "Correcao de Comportamento", "Adestramento Online"],
    "turismo": ["Pacotes de Viagem", "Passagens Aereas", "Hospedagem", "Roteiros Personalizados", "Seguro Viagem"],
    "turismo luxo": ["Viagens Exclusivas", "Resorts 5 Estrelas", "Cruzeiros de Luxo", "Concierge 24h"],
    "casamentos": ["Cerimonial Completo", "Assessoria de Casamento", "Decoracao", "Buffet", "Fotografia e Filmagem"],
    "fotografia": ["Ensaio Fotografico", "Fotografia de Casamento", "Fotografia Corporativa", "Book Fotografico"],
    "rh": ["Recrutamento e Selecao", "Headhunting", "BPO de RH", "Avaliacao de Competencias", "Treinamento e Desenvolvimento"],
    "educacao": ["Curso Online", "Treinamento", "Workshop", "Mentoria", "Aulas Particulares", "Certificacao"],
    "idiomas": ["Ingles", "Espanhol", "Frances", "Alemao", "Japones", "Preparatorio TOEFL/IELTS"],
    "curso online": ["Curso Gravado", "Curso ao Vivo", "Mentoria em Grupo", "Comunidade de Alunos", "Certificado Digital"],
    "enem vestibular": ["Preparatorio ENEM", "Simulados", "Redacao", "Matematica", "Ciencias da Natureza"],
    "concursos": ["Preparatorio Concurso", "Simulados", "Legislacao", "Portugues para Concursos"],
    "igreja": ["Cultos Presenciais", "Cultos Online", "Escola Biblica", "Grupos de Celula", "Eventos Especiais"],
    "consultoria": ["Consultoria Estrategica", "Gestao Empresarial", "Planejamento", "Analise de Mercado"],
    "construcao": ["Construcao Residencial", "Construcao Comercial", "Reforma Completa",
        "Projeto Estrutural", "Gerenciamento de Obra", "Fundacao e Estrutura"],
    "loja construcao": ["Cimento e Argamassa", "Tijolos e Blocos", "Ferragens e Parafusos",
        "Tintas e Revestimentos", "Madeiras e Compensados", "Material Eletrico e Hidraulico",
        "Ferramentas e Equipamentos", "Telhas e Coberturas"],
    "autopecas": ["Pecas de Motor", "Freios e Suspensao", "Eletrica Automotiva",
        "Filtros e Oleos", "Embreagem e Cambio", "Acessorios Automotivos", "Pneus e Rodas"],
    "farmacia": ["Medicamentos Sob Receita", "Medicamentos OTC", "Perfumaria e Cosmeticos",
        "Vitaminas e Suplementos", "Produtos para Bebe", "Manipulacao de Formulas"],
    "optica": ["Oculos de Grau", "Oculos de Sol", "Lentes de Contato",
        "Exame de Vista", "Armacoes Premium", "Lentes Progressivas"],
    "floricultura": ["Arranjos Florais", "Buques para Presente", "Plantas Ornamentais",
        "Flores para Casamento", "Decoracao Floral Corporativa"],
    "loja moveis": ["Sala de Estar", "Quarto Casal", "Cozinha Planejada",
        "Escritorio", "Colchoes e Box", "Decoracao e Utilidades"],
    "papelaria": ["Material Escolar", "Material de Escritorio", "Impressao e Copia",
        "Embalagens", "Artigos para Presente", "Plotter e Plotagem"],
    "loja esportes": ["Roupas Esportivas", "Calcados para Esporte", "Equipamentos Academia",
        "Futebol e Society", "Natacao e Corrida", "Artes Marciais"],
}


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT PARSER
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# SMART PROMPT PARSER — LLM first, regex fallback
# ══════════════════════════════════════════════════════════════════════════════

def _parse_prompt_smart(prompt: str) -> dict:
    """
    Parse prompt using LLM + regex in parallel, with few-shot learning.
    - Regex detects niche immediately (fast, deterministic)
    - Niche hint passed to Ollama so it loads few-shot examples for that niche
    - The more approved generations exist, the better Ollama performs over time
    """
    from app.services.nlp_service import extract_context_async, is_ollama_available

    # Run regex first to get the niche hint for few-shot selection
    regex_ctx = parse_prompt(prompt)
    niche_hint = regex_ctx.get("niche", "")

    llm_result = []
    llm_thread = None
    if is_ollama_available():
        llm_thread = extract_context_async(prompt, llm_result, niche_hint=niche_hint)
        logger.info("Ollama extraction started (niche hint: %s)", niche_hint)

    if llm_thread is None:
        logger.info("Ollama not available — using regex only (niche: %s)", niche_hint)
        return regex_ctx

    # Wait up to 45s for LLM
    llm_thread.join(timeout=45.0)

    if llm_result:
        merged = _merge_contexts(regex_ctx, llm_result[0])
        logger.info("LLM enrichment applied — niche: %s", merged.get("niche"))
        return merged

    logger.info("LLM timed out — using regex context (niche: %s)", niche_hint)
    return regex_ctx


def _merge_contexts(regex_ctx: dict, llm_ctx: dict) -> dict:
    """
    Merge regex and LLM contexts.
    Strategy: regex wins for NICHE (most reliable pattern matching),
    LLM wins for semantic/free-text fields.
    """
    merged = dict(regex_ctx)  # start with regex as base

    # ── NICHE: regex ALWAYS wins — it has 179 specific patterns ──────────────
    # LLM often generalizes (e.g. "loja de construção" → "e-commerce")
    # Only use LLM niche if regex returned the generic fallback "negocios"
    if regex_ctx.get("niche", "negocios") == "negocios":
        llm_niche = llm_ctx.get("niche", "")
        if llm_niche and llm_niche != "negocios":
            merged["niche"] = llm_niche
            merged["business_type"] = llm_ctx.get("business_type", regex_ctx.get("business_type", "Empresa"))

    # ── Business name: LLM is better at extracting quoted names ──────────────
    llm_name = llm_ctx.get("business_name", "")
    regex_name = regex_ctx.get("business_name", "")
    if llm_name and (not regex_name or len(llm_name) > len(regex_name)):
        merged["business_name"] = llm_name

    # ── Semantic fields: LLM wins when it has non-default values ─────────────
    LLM_SEMANTIC = ["audience", "extra_info"]
    for key in LLM_SEMANTIC:
        llm_val = llm_ctx.get(key)
        if llm_val and llm_val not in ("", "pessoas que buscam qualidade e resultados"):
            merged[key] = llm_val

    # ── Tone and intention: LLM wins if it has specific values ───────────────
    for key in ["communication_tone", "intention"]:
        llm_val = llm_ctx.get(key, "")
        if llm_val and llm_val not in ("formal", "captar leads"):
            merged[key] = llm_val

    # ── Visual style: only override if user explicitly mentioned style ────────
    llm_style = llm_ctx.get("visual_style", "")
    if llm_style and llm_style != "moderno" and not regex_ctx.get("colors"):
        merged["visual_style"] = llm_style

    # ── Address and schedule: use whichever is more complete ──────────────────
    if llm_ctx.get("address") and not regex_ctx.get("address"):
        merged["address"] = llm_ctx["address"]
    elif llm_ctx.get("address") and len(str(llm_ctx["address"])) > len(str(regex_ctx.get("address", ""))):
        merged["address"] = llm_ctx["address"]

    if llm_ctx.get("schedule") and len(llm_ctx["schedule"]) > len(regex_ctx.get("schedule", [])):
        merged["schedule"] = llm_ctx["schedule"]

    # ── Services: merge but ensure niche-relevant services win ───────────────
    # Only add LLM services if they don't contradict the regex niche
    llm_svcs = llm_ctx.get("services", [])
    regex_svcs = regex_ctx.get("services", [])
    if llm_svcs and regex_svcs:
        # Add LLM services that don't look like generic e-commerce/online terms
        GENERIC_TERMS = {"produtos online", "entrega rapida", "frete gratis",
                         "catalogo digital", "compra segura", "troca facil",
                         "loja virtual", "e-commerce", "venda online"}
        filtered_llm = [s for s in llm_svcs
                        if s.lower() not in GENERIC_TERMS and len(s) > 3]
        combined = list({s.lower(): s for s in (regex_svcs + filtered_llm)}.values())
        merged["services"] = combined[:6]
    elif llm_svcs and not regex_svcs:
        merged["services"] = llm_svcs[:6]

    # ── Differentials: OR merge ───────────────────────────────────────────────
    llm_diffs = llm_ctx.get("differentials", [])
    regex_diffs = regex_ctx.get("differentials", [])
    if llm_diffs:
        combined_diffs = list({d.lower(): d for d in (regex_diffs + llm_diffs)}.values())
        merged["differentials"] = combined_diffs[:4]

    # ── Boolean flags: OR merge ───────────────────────────────────────────────
    for flag in ["wants_map", "wants_form", "wants_faq", "wants_gallery",
                 "wants_pricing", "wants_video"]:
        merged[flag] = regex_ctx.get(flag, False) or llm_ctx.get(flag, False)

    # ── Contact: regex wins (better at structured patterns) ──────────────────
    for field in ["phone", "email", "wa", "ig"]:
        if not merged.get(field) and llm_ctx.get(field):
            merged[field] = llm_ctx[field]

    # ── Location: use whichever is more specific ──────────────────────────────
    if llm_ctx.get("location") and not regex_ctx.get("location"):
        merged["location"] = llm_ctx["location"]

    # ── Colors: regex wins (already hex) ─────────────────────────────────────
    if not merged.get("colors") and llm_ctx.get("colors"):
        merged["colors"] = llm_ctx["colors"]

    # ── Testimonial count: take max ───────────────────────────────────────────
    merged["testimonial_count"] = max(
        regex_ctx.get("testimonial_count", 3),
        llm_ctx.get("testimonial_count", 3),
    )

    # Auto-enable map if address found
    if merged.get("address"):
        merged["wants_map"] = True

    return merged

def parse_prompt(prompt: str) -> dict:
    p = prompt.strip()
    pl = p.lower()

    name = _extract_name(p, pl)

    niche, btype = "negocios", "Empresa"
    for pattern, n, bt in NICHES:
        if re.search(pattern, pl):
            niche, btype = n, bt
            break

    CITIES = {
        "sao paulo": "Sao Paulo", "rio de janeiro": "Rio de Janeiro",
        "belo horizonte": "Belo Horizonte", "curitiba": "Curitiba",
        "porto alegre": "Porto Alegre", "salvador": "Salvador",
        "fortaleza": "Fortaleza", "recife": "Recife", "manaus": "Manaus",
        "brasilia": "Brasilia", "goiania": "Goiania", "campinas": "Campinas",
        "florianopolis": "Florianopolis", "natal": "Natal", "maceio": "Maceio",
        "teresina": "Teresina", "campo grande": "Campo Grande",
        "joao pessoa": "Joao Pessoa", "belem": "Belem", "guarulhos": "Guarulhos",
        "osasco": "Osasco", "ribeirao preto": "Ribeirao Preto",
        "franca": "Franca", "sorocaba": "Sorocaba", "uberlandia": "Uberlandia",
        "contagem": "Contagem", "feira de santana": "Feira de Santana",
        "joinville": "Joinville", "londrina": "Londrina",
        "sao jose dos campos": "Sao Jose dos Campos", "santos": "Santos",
        "piracicaba": "Piracicaba", "jundiai": "Jundiai",
        "maringa": "Maringa", "cascavel": "Cascavel",
        "vitoria": "Vitoria", "vila velha": "Vila Velha",
        "aracaju": "Aracaju", "palmas": "Palmas",
    }
    location = next((v for k, v in CITIES.items() if k in pl), "")

    style = NICHE_DEFAULT_STYLE.get(niche, "moderno")
    if re.search(r"premium|luxo|elegante|sofisticado|exclusivo|alto\s+padrao", pl): style = "corporativo"
    elif re.search(r"minimalista|simples|clean|minimalismo", pl): style = "minimalista"
    elif re.search(r"agressivo|impactante|forte|bold|dinamico|energetico", pl): style = "agressivo"
    elif re.search(r"moderno|contemporaneo|inovador|digital", pl): style = "moderno"

    tone = "formal"
    if re.search(r"informal|descontraido|jovem|casual|divertido|animado|irreverente", pl): tone = "informal"

    intention = "captar leads"
    if re.search(r"vender|comprar|produto|loja|e-commerce|carrinho|checkout", pl): intention = "vender produto"
    elif re.search(r"evento|conferencia|workshop|palestra|webinar|inscricao|ingresso", pl): intention = "divulgar evento"
    elif re.search(r"apresentar|portfolio|sobre nos|institucional|quem somos|historia", pl): intention = "apresentar servico"
    elif re.search(r"curso|mentoria|treinamento|aula|ead|infoproduto", pl): intention = "vender curso"

    COLOR_MAP = {
        "azul": "#1A56DB", "vermelho": "#C53030", "verde": "#276749",
        "amarelo": "#D69E2E", "laranja": "#C05621", "roxo": "#6B46C1",
        "rosa": "#B83280", "preto": "#1A202C", "dourado": "#B7791F",
        "cinza": "#718096", "prata": "#A0AEC0", "branco": "#F7FAFC",
        "marrom": "#744210", "bege": "#D4A574", "turquesa": "#0694A2",
        "coral": "#E05252", "lilas": "#9061F9", "vinho": "#7B2D8B",
        "salmao": "#FC8181", "terracota": "#C05621", "navy": "#1A365D",
        "tiffany": "#0ABAB5", "nude": "#E8C9A0",
    }
    colors = [hex_val for kw, hex_val in COLOR_MAP.items() if kw in pl]

    services = _extract_services(p, pl, niche, location)
    differentials = _extract_differentials(pl)
    audience = _extract_audience(pl, niche)
    sections_req = _extract_sections(pl)

    banner_count = 1
    m = re.search(r'(\d+)\s*banner', pl)
    if m: banner_count = min(int(m.group(1)), 4)

    testimonial_count = 3
    m = re.search(r'(\d+)\s*(?:depoimento|testemunho|avaliacao)', pl)
    if m: testimonial_count = min(int(m.group(1)), 6)

    form_fields = ["Nome", "E-mail"]
    if re.search(r"telefone|celular|whatsapp|fone|zap", pl): form_fields.append("Telefone/WhatsApp")
    if re.search(r"empresa|cnpj|razao\s+social", pl): form_fields.append("Empresa")
    if re.search(r"mensagem|assunto|duvida|comentario|descricao", pl): form_fields.append("Mensagem")
    if re.search(r"data|horario|agendamento|consulta", pl): form_fields.append("Data preferida")
    if re.search(r"cidade|estado|regiao", pl): form_fields.append("Cidade")

    phone_m = re.search(r'(?:telefone|fone|tel|celular|cel)[^\d]*(\(?\d{2}\)?\s*\d{4,5}[\-\s]?\d{4})', pl)
    phone = re.sub(r'\s', '', phone_m.group(1)) if phone_m else ""
    email_m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', p)
    email = email_m.group(0) if email_m else ""
    wa_m = re.search(r'whatsapp[^\d]*(\d[\d\s\-\(\)]{8,14})', pl)
    wa = re.sub(r'\D', '', wa_m.group(1)) if wa_m else ""
    ig_m = re.search(r'@([\w.]{3,30})', p)
    ig = ig_m.group(1) if ig_m else ""

    # ── Address extraction ────────────────────────────────────────────────────
    address = _extract_address(p, pl)

    # ── Schedule/hours extraction ─────────────────────────────────────────────
    schedule = _extract_schedule(p, pl)

    # ── Custom free-text info (anything after "informacoes:" or similar) ──────
    custom_info = _extract_custom_info(p, pl)

    # Auto-enable map if address found
    wants_map_auto = bool(address)

    return {
        "original_prompt": p, "business_name": name, "niche": niche,
        "business_type": btype, "services": services, "differentials": differentials,
        "audience": audience, "visual_style": style, "communication_tone": tone,
        "intention": intention, "location": location, "colors": colors,
        "sections_requested": sections_req, "banner_count": banner_count,
        "form_fields": form_fields, "testimonial_count": testimonial_count,
        "wants_pricing": bool(re.search(r"preco|plano|tabela|valor|pricing|pacote|investimento", pl)),
        "wants_faq": bool(re.search(r"faq|perguntas|duvidas|frequentes", pl)),
        "wants_gallery": bool(re.search(r"galeria|fotos|imagens|portfolio|trabalhos|antes\s+e\s+depois", pl)),
        "wants_video": bool(re.search(r"video|youtube|apresentacao\s+em\s+video", pl)),
        "wants_form": bool(re.search(r"formulario|form|contato|cadastro|inscricao|lead|whatsapp|agendamento", pl)) or intention in ("captar leads", "vender curso"),
        "phone": phone, "email": email, "wa": wa, "ig": ig,
        "address": address, "schedule": schedule, "custom_info": custom_info,
        "wants_map": bool(re.search(r"mapa|endereco|localizacao|como\s+chegar|onde\s+fica|presencial", pl)) or wants_map_auto,
        "past_patterns": [],
    }



def _extract_address(p: str, pl: str) -> str:
    """Extract full street address from prompt."""
    # Pattern: "Avenida/Rua/Alameda/Travessa/Rodovia X, number" or "endereco: X"
    patterns = [
        r'(?:avenida|av\.?|rua|r\.?|alameda|al\.?|travessa|tv\.?|rodovia|br-?\d+|estrada|praca|pc\.?)\s+[^,\.\n]{3,60},?\s*\d+[^,\.\n]{0,30}',
        r'(?:endereco|endereço)[:\s]+([^,\.\n]{5,80})',
        r'(?:localizado|localizada|fica|situad[ao])\s+(?:na|no|em)\s+([^,\.\n]{5,80})',
    ]
    for pat in patterns:
        m = re.search(pat, p, re.IGNORECASE)
        if m:
            addr = m.group(0).strip()
            # Clean up prefix words
            addr = re.sub(r'^(?:endereco|endereço)[:\s]+', '', addr, flags=re.IGNORECASE).strip()
            addr = re.sub(r'^(?:localizado|localizada|fica|situad[ao])\s+(?:na|no|em)\s+', '', addr, flags=re.IGNORECASE).strip()
            if len(addr) > 5:
                return addr.title()
    return ""


def _extract_schedule(p: str, pl: str) -> list[dict]:
    """Extract event/service schedule from prompt (day + time + optional event name)."""
    schedules = []
    DAY_MAP = {
        "segunda": "Segunda-feira", "terca": "Terça-feira", "quarta": "Quarta-feira",
        "quinta": "Quinta-feira", "sexta": "Sexta-feira", "sabado": "Sábado",
        "domingo": "Domingo", "seg": "Segunda-feira", "ter": "Terça-feira",
        "qua": "Quarta-feira", "qui": "Quinta-feira", "sex": "Sexta-feira",
        "sab": "Sábado", "dom": "Domingo",
    }
    # Pattern: "dia de quarta as 19:30" / "sextas as 20h" / "domingo 19:00"
    time_pattern = r'(\d{1,2}[h:]\d{0,2}(?:hs?)?)'
    day_pattern = r'(segunda|terca|quarta|quinta|sexta|sabado|domingo|seg|ter|qua|qui|sex|sab|dom)'
    # Find all "day ... time" occurrences
    combined = re.finditer(
        rf'{day_pattern}[^.\n]{{0,40}}?{time_pattern}',
        pl, re.IGNORECASE
    )
    for m in combined:
        day_raw = m.group(1).lower()
        time_raw = m.group(2)
        day_name = DAY_MAP.get(day_raw, day_raw.capitalize())
        # Normalize time: "19h30" / "19:30" / "19h" → "19:30" / "19:00"
        time_clean = re.sub(r'(\d{1,2})h(\d{2})?s?', lambda x: f"{x.group(1)}:{x.group(2) or '00'}", time_raw)
        time_clean = time_clean.rstrip('hs').strip()
        # Try to find event name near this match
        context = pl[max(0, m.start()-60):m.end()+60]
        event = ""
        for kw in ["culto", "missa", "vigilia", "vigília", "reuniao", "reunião",
                   "celula", "célula", "encontro", "servico", "serviço", "oracao", "oração",
                   "conferencia", "conferência", "louvor", "pregacao", "pregação"]:
            if kw in context:
                event = kw.capitalize()
                break
        schedules.append({"day": day_name, "time": time_clean, "event": event})

    # Deduplicate
    seen = set()
    unique = []
    for s in schedules:
        key = (s["day"], s["time"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def _extract_custom_info(p: str, pl: str) -> list[str]:
    """Extract any explicit custom info lines the user provided."""
    info = []
    # Phone numbers not caught by phone_m
    phones = re.findall(r'\(?\d{2}\)?[\s-]?\d{4,5}[\s-]?\d{4}', p)
    for ph in phones[:2]:
        clean = re.sub(r'\s', '', ph)
        if len(clean) >= 10:
            info.append(f"📞 {clean}")
    return info

def _extract_name(p: str, pl: str) -> str:
    FORBIDDEN = {"landing", "page", "site", "criar", "quero", "preciso", "fazer",
                 "formulario", "depoimento", "tabela", "plano", "faq", "banner",
                 "especializada", "especializado", "especialista", "conjuntos",
                 "verao", "inverno", "infantil", "infantis", "crianca", "bebe",
                 "loja", "empresa", "negocio", "servico", "produto", "anos",
                 "franca", "sao", "paulo", "rio", "curitiba", "campinas",
                 "moderno", "premium", "digital", "online", "profissional"}
    patterns = [
        r'"([^"]{2,40})"', r"'([^']{2,40})'",
        r'(?:loja|empresa|clinica|academia|escritorio|studio|salao|restaurante|agencia|marca|barbearia|consultorio|instituto|centro)\s+([A-Z][^\s,\.]{2,30})',
        r'\b([A-Z][a-z]+[A-Z][a-zA-Z]{2,})\b',
        r'para\s+(?:a\s+|o\s+)?([A-Z][a-zA-Z\s]{2,30})(?:\s*,|\s+especializ)',
        r'(?:chamad[ao]|nome[d]?\s+(?:e|eh))\s+([A-Z][^\s,\.]{2,30})',
    ]
    for pat in patterns:
        m = re.search(pat, p)
        if m:
            candidate = m.group(1).strip()
            words = candidate.lower().split()
            if len(candidate) > 2 and not any(w in FORBIDDEN for w in words) and not re.search(r'\d', candidate):
                return candidate
    return ""


def _extract_services(p: str, pl: str, niche: str, location: str) -> list[str]:
    BLACKLIST = {
        "app", "whatsapp", "instagram", "facebook", "tiktok", "youtube",
        "landing", "page", "site", "criar", "quero", "preciso", "fazer",
        "formulario", "depoimento", "tabela", "plano", "faq", "banner",
        "nome", "email", "telefone", "contato", "anos", "experiencia",
        "qualidade", "confianca", "resultado", "resultados",
    }
    if location:
        BLACKLIST.update(location.lower().split())

    # Alias map: prompt keywords → SERVICE_DB entry names
    # Handles cases where user writes informally (remedio → Medicamentos, etc.)
    NICHE_ALIASES: dict[str, list[tuple[str, str]]] = {
        "farmacia": [
            (r"remedio|medicamento|med\b|receita", "Medicamentos Sob Receita"),
            (r"perfum|cosmetico|beleza\s+prod", "Perfumaria e Cosmeticos"),
            (r"higiene\s+pessoal|higiene|sabonete|shampoo", "Perfumaria e Cosmeticos"),
            (r"vitamina|suplemento|mineral", "Vitaminas e Suplementos"),
            (r"bebe|infantil|fralda|crianca\s+prod", "Produtos para Bebe"),
            (r"manipula|formula\s+personalizada", "Manipulacao de Formulas"),
        ],
        "loja construcao": [
            (r"cimento|argamassa|reboco", "Cimento e Argamassa"),
            (r"tijolo|bloco|ceramica", "Tijolos e Blocos"),
            (r"ferragem|parafuso|preg|fixacao", "Ferragens e Parafusos"),
            (r"tinta|revestimento|verniz|selador", "Tintas e Revestimentos"),
            (r"madeira|compensado|mdf\b|pinus", "Madeiras e Compensados"),
            (r"eletrico|fio|cabo|disjuntor|tomada", "Material Eletrico e Hidraulico"),
            (r"ferramenta|equipamento|furadeira|marreta", "Ferramentas e Equipamentos"),
            (r"telha|cobertura|calha|rufo", "Telhas e Coberturas"),
        ],
        "autopecas": [
            (r"motor|pistao|junta|rolamento", "Pecas de Motor"),
            (r"freio|pastilha|disco\s+freio|fluido", "Freios e Suspensao"),
            (r"suspensao|amortecedor|barra", "Freios e Suspensao"),
            (r"eletrica|bateria|alternador|partida", "Eletrica Automotiva"),
            (r"filtro|oleo\s+lubr|lubrificante", "Filtros e Oleos"),
            (r"pneu|roda|aro\b", "Pneus e Rodas"),
        ],
        "optica": [
            (r"oculos\s+grau|lente\s+grau|grau\b", "Oculos de Grau"),
            (r"oculos\s+sol|lente\s+escura|sol\b", "Oculos de Sol"),
            (r"lente\s+contato|lente\s+de\s+contato", "Lentes de Contato"),
            (r"exame\s+vista|consulta\s+optometria|optometria", "Exame de Vista"),
            (r"armacao|armação|aro\s+oculos", "Armacoes Premium"),
            (r"progressiva|bifocal|multifocal", "Lentes Progressivas"),
        ],
        "moda feminina": [
            (r"vestido|blusa|camisa\s+fem", "Vestidos"),
            (r"calca|bermuda|short", "Calcas e Shorts"),
            (r"acessorio|brinco|colar|pulseira", "Acessorios Femininos"),
            (r"moda\s+praia|biquini|maio", "Moda Praia"),
        ],
        "gastronomia": [
            (r"almoco|self.service|executivo", "Almoco Executivo"),
            (r"jantar|a\s+la\s+carte|carte", "Jantar a La Carte"),
            (r"delivery|entrega\s+gastr", "Delivery"),
            (r"buffet|eventos\s+gastr|catering", "Buffet"),
        ],
    }

    found = []
    niche_services = SERVICE_DB.get(niche, [])

    # 1) Try alias matching first (most accurate for informal prompts)
    if niche in NICHE_ALIASES:
        for pattern, svc_name in NICHE_ALIASES[niche]:
            if re.search(pattern, pl) and svc_name not in found:
                found.append(svc_name)

    # 2) Word-match against SERVICE_DB entries
    for svc in niche_services:
        if svc in found:
            continue
        words = [w for w in svc.lower().split() if len(w) > 4]
        if words and any(w in pl for w in words):
            found.append(svc)

    # 3) "especializado em X" pattern
    spec_m = re.search(r'especializ\w+\s+em\s+([^,\.]+?)(?:\s*,|\s+em\s+|\s+(?:e\s+em|para|com|quero|localiz|em\s+[A-Z])|\.|$)', pl)
    if spec_m:
        for part in re.split(r'\s+e\s+', spec_m.group(1).strip()):
            part_clean = part.strip().title()
            part_words = part.strip().lower().split()
            if len(part_clean) > 3 and not any(w in BLACKLIST for w in part_words) and part_clean not in found:
                found.append(part_clean)

    # 4) Fallback to first 3 from SERVICE_DB
    if not found:
        found = niche_services[:3] if niche_services else ["Atendimento Especializado", "Qualidade Garantida", "Suporte Completo"]
    return found[:5]


def _extract_differentials(pl: str) -> list[str]:
    diffs = []
    DIFF_MAP = [
        (r"premium|exclusiv", "Atendimento Premium"),
        (r"\bpersonalizado\b", "Totalmente Personalizado"),
        (r"entrega\s+rapid|agilidade\s+na\s+entrega", "Entrega Rapida"),
        (r"\bgarantia\b", "Garantia de Satisfacao"),
        (r"\d+\s*anos?\s+(?:de\s+)?(?:experiencia|mercado)", "Anos de Experiencia"),
        (r"especialista\s+certificad|profissional\s+certificad|cro\b|cfm\b|cref\b", "Profissionais Certificados"),
        (r"tecnologia\s+de\s+ponta|solucao\s+inovadora|equipamento\s+moderno", "Tecnologia de Ponta"),
        (r"resultado\s+(?:comprovado|garantido|real)", "Resultados Comprovados"),
        (r"24\s*h\b|24\s*horas\b|plantao\b", "Disponivel 24h"),
        (r"atendimento\s+online|100%\s+online|telemedicina|teleconsulta", "Atendimento Online"),
        (r"gratis|gratuito|sem\s+custo|consulta\s+gratis", "Consulta Gratuita"),
        (r"sem\s+fidelidade|sem\s+contrato|sem\s+mensalidade", "Sem Fidelidade"),
        (r"parcelamento|parcelado\s+em|cartao\s+de\s+credito", "Parcelamento Disponivel"),
        (r"frete\s+gratis|entrega\s+gratis|entrega\s+gratuita", "Frete Gratis"),
        (r"antes\s+e\s+depois|resultado\s+visivel|transformacao", "Resultados Visiveis"),
        (r"sigilo|confidencialidade|privacidade\s+garantida", "Total Sigilo"),
        (r"primeira\s+consulta\s+gratis|avaliacao\s+gratis", "Primeira Consulta Gratis"),
    ]
    for pattern, diff in DIFF_MAP:
        if re.search(pattern, pl):
            diffs.append(diff)
    return diffs[:4]


def _extract_audience(pl: str, niche: str) -> str:
    # "todos" / "publico geral" overrides everything
    if re.search(r'\btodos\b|p[úu]blico\s+geral|qualquer\s+pessoa|todas\s+as\s+idades|todas\s+as\s+pessoas', pl):
        return NICHE_AUDIENCE.get(niche, "pessoas de todas as idades")
    if re.search(r"empresa|b2b|corporativo|negocio|cnpj", pl): return "empresas e profissionais"
    if re.search(r"jovem|universitario|estudante|adolescente", pl): return "jovens e estudantes"
    if re.search(r"familia|familiar|crianca|filho|infantil|kids|bebe|gestante|gravida", pl): return "familias com criancas"
    if re.search(r"mulher|feminino\b|ela\b", pl): return "mulheres"
    if re.search(r"homem|masculino\b|ele\b", pl): return "homens"
    if re.search(r"idoso|terceira\s+idade|senior|60\s+anos", pl): return "pessoas da terceira idade"
    if re.search(r"atleta|esportista|competidor", pl): return "atletas e esportistas"
    if re.search(r"empreendedor|empresario|dono\s+de\s+negocio", pl): return "empreendedores e empresarios"
    return NICHE_AUDIENCE.get(niche, "pessoas que buscam qualidade e resultados")


def _extract_sections(pl: str) -> list[str]:
    req = []
    if re.search(r"hero|banner\s+principal|cabecalho|topo", pl): req.append("hero")
    if re.search(r"servico|produto|o\s+que\s+oferec|o\s+que\s+faz|diferenciais", pl): req.append("features")
    if re.search(r"depoimento|testemunho|avaliacao|cliente\s+diz|review", pl): req.append("testimonials")
    if re.search(r"preco|plano|tabela|valor|pricing|pacote|investimento", pl): req.append("pricing")
    if re.search(r"faq|perguntas|duvidas|frequentes", pl): req.append("faq")
    if re.search(r"galeria|fotos|imagens|portfolio|trabalhos|antes\s+e\s+depois", pl): req.append("gallery")
    if re.search(r"formulario|form|contato|cadastro|inscricao|lead", pl): req.append("form")
    if re.search(r"mapa|endereco|localizacao|como\s+chegar|onde\s+fica", pl): req.append("map")
    if re.search(r"sobre|quem\s+somos|historia|equipe|time|fundador", pl): req.append("about")
    if re.search(r"contador|urgencia|tempo|oferta|prazo|vagas\s+limitadas", pl): req.append("countdown")
    if re.search(r"video|youtube|apresentacao\s+em\s+video", pl): req.append("video")
    if re.search(r"parceiro|cliente\s+logo|marca\s+parceira|certificacao", pl): req.append("partners")
    return req


# ══════════════════════════════════════════════════════════════════════════════
# LEARNING FROM PAST GENERATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _load_past(db, niche: str, limit: int = 5) -> list[dict]:
    try:
        from app.models.training_data import TrainingData
        rows = (db.query(TrainingData)
                .filter(TrainingData.prompt.ilike(f"%{niche}%"))
                .filter(TrainingData.is_validated == True)
                .order_by(TrainingData.created_at.desc())
                .limit(limit).all())
        patterns = []
        for row in rows:
            try:
                data = json.loads(row.completion)
                patterns.append({"headline": data.get("headline", ""), "sections": data.get("sections", [])})
            except Exception:
                pass
        return patterns
    except Exception:
        return []


def _load_learned_patterns(db, niche: str) -> dict[str, list[str]]:
    """
    Load top patterns from pattern_cache for the given niche.
    Returns dict with keys: services, differentials, headlines, ctas
    Falls back to empty lists if table doesn't exist yet.
    """
    try:
        from app.workers.learning_worker import get_learned_patterns
        return {
            "services":      get_learned_patterns(db, niche, "service", 5),
            "differentials": get_learned_patterns(db, niche, "differential", 3),
            "headlines":     get_learned_patterns(db, niche, "headline", 3),
            "ctas":          get_learned_patterns(db, niche, "cta", 2),
        }
    except Exception:
        return {"services": [], "differentials": [], "headlines": [], "ctas": []}


def _save_training(db, prompt: str, completion: str):
    try:
        from app.models.training_data import TrainingData
        row = TrainingData(
            id=uuid.uuid4(), prompt=prompt[:2000], completion=completion[:10000],
            source="api", quality_score=0.7, is_validated=True,
            created_at=datetime.now(tz=timezone.utc),
        )
        db.add(row)
        db.commit()
    except Exception as e:
        logger.warning("Could not save training data: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# COPY GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_copy(ctx: dict) -> dict:
    name = ctx["business_name"] or ctx["business_type"]
    niche = ctx["niche"]
    services = list(ctx["services"])
    diffs = list(ctx["differentials"])
    audience = ctx["audience"]
    tone = ctx["communication_tone"]
    intention = ctx["intention"]
    location = ctx["location"]
    past = ctx.get("past_patterns", [])
    learned = ctx.get("learned_patterns", {})

    loc = f" em {location}" if location else ""

    # Enrich with learned patterns from pattern_cache
    learned_svcs = learned.get("services", [])
    if learned_svcs:
        merged = list({s.lower(): s for s in (services + learned_svcs)}.values())
        services = merged[:6]
        ctx["services"] = services
    learned_diffs = learned.get("differentials", [])
    if learned_diffs and len(diffs) < 2:
        diffs = (diffs + [d for d in learned_diffs if d not in diffs])[:4]

    svc_str = ", ".join(services[:2]) if services else niche
    default_diffs = NICHE_DIFFS.get(niche, ["qualidade comprovada", "atendimento especializado"])
    diff_str = " e ".join(diffs[:2]) if diffs else " e ".join(default_diffs)

    used_headlines = [p.get("headline", "") for p in past]
    variants = _headline_variants(name, niche, intention, tone, loc, services)
    headline = next((h for h in variants if h not in used_headlines), variants[0])

    # Extract experience years from prompt if mentioned
    exp_match = re.search(r'(\d+)\s*anos?\s+(?:de\s+)?(?:experiencia|mercado|atuacao)', ctx.get("original_prompt", "").lower())
    exp_str = f" Sao {exp_match.group(1)} anos de experiencia no mercado." if exp_match else ""

    # Niches that SELL products (not services) — different copy language
    PRODUCT_NICHES = {"farmacia", "autopecas", "loja construcao", "optica", "floricultura",
                      "loja moveis", "papelaria", "loja esportes", "moda feminina", "moda masculina",
                      "moda infantil", "moda", "e-commerce", "petshop", "perfumaria", "joalheria",
                      "loja informatica", "loja brinquedos", "suplementos"}

    # Build contextual subtitle using real prompt data
    if niche in PRODUCT_NICHES:
        svc_label = "produtos" if not services else ", ".join(s.lower() for s in services[:2])
        if tone == "formal":
            subtitle = (f"Encontre {svc_label} com {diff_str}. "
                        f"Atendemos {audience}{loc} com qualidade, variedade e os melhores precos.{exp_str}")
            ctas = _ctas_formal(intention, niche)
        else:
            subtitle = (f"Aqui voce encontra {svc_label} com {diff_str}. "
                        f"Pra {audience}{loc} que quer qualidade e preco justo!{exp_str}")
            ctas = _ctas_informal(intention, niche)
    elif tone == "formal":
        subtitle = (f"Oferecemos {svc_str} com {diff_str}. "
                    f"Atendemos {audience} que buscam resultados reais e duradouros{loc}.{exp_str}")
        ctas = _ctas_formal(intention, niche)
    else:
        subtitle = (f"A gente oferece {svc_str} com {diff_str}. "
                    f"Feito para {audience} que querem resultados de verdade{loc}!{exp_str}")
        ctas = _ctas_informal(intention, niche)

    features = _build_features(services, diffs, niche, audience)
    testimonials = _build_testimonials(ctx)
    pricing = _build_pricing(ctx) if ctx["wants_pricing"] else []
    faq = _build_faq(ctx) if ctx["wants_faq"] else []

    # SEO with real data
    seo_title = f"{name} - {niche.capitalize()}{loc}"
    seo_title = (seo_title[:57] + "...") if len(seo_title) > 60 else seo_title
    svc_seo = services[0].lower() if services else niche
    seo_desc = f"Conheca o {name}, especialista em {niche}{loc}. {svc_seo.capitalize()} com {diff_str}. {ctas[0]}."
    seo_desc = (seo_desc[:157] + "...") if len(seo_desc) > 160 else seo_desc

    return {
        "headline": headline, "headline_variations": variants,
        "subtitle": subtitle, "ctas": ctas,
        "features": features, "testimonials": testimonials,
        "pricing": pricing, "faq": faq,
        "seo_title": seo_title.strip(), "seo_description": seo_desc.strip(),
        "display_name": name,
    }

def _headline_variants(name: str, niche: str, intention: str, tone: str, loc: str, services: list) -> list:
    svc = services[0].lower() if services else niche
    NICHE_H: dict = {
        "odontologia": [f"{name}: O Sorriso que Voce Sempre Sonhou{loc}", f"Transforme seu Sorriso com {name}"],
        "ortodontia": [f"{name}: Alinhamento Dental com Precisao e Conforto{loc}", f"Sorria com Confianca — {name}"],
        "harmonizacao facial": [f"{name}: Realce sua Beleza Natural com Harmonizacao Facial", f"Resultados Naturais e Seguros — {name}{loc}"],
        "psicologia": [f"{name}: Cuidando da sua Saude Mental com Acolhimento", f"Voce Merece se Sentir Bem — Terapia com {name}", f"{name}: Sua Jornada de Autoconhecimento Comeca Aqui"],
        "fisioterapia": [f"{name}: Reabilitacao Completa para Voce Voltar a Viver Bem", f"Livre-se da Dor com {name}{loc}"],
        "nutricao": [f"{name}: Transforme sua Saude Atraves da Alimentacao", f"Emagrecimento Saudavel e Definitivo com {name}"],
        "fitness": [f"{name}: Transforme seu Corpo e sua Vida{loc}", f"Resultados Reais com {name} — Academia que Muda Vidas"],
        "crossfit": [f"{name}: Supere seus Limites no CrossFit{loc}", f"Comunidade, Forca e Resultado — {name}"],
        "personal trainer": [f"{name}: Treino 100% Personalizado para seus Objetivos", f"Alcance seus Resultados Mais Rapido com {name}"],
        "pilates": [f"{name}: Equilibrio, Postura e Bem-Estar com Pilates", f"Transforme seu Corpo com o Metodo Pilates — {name}"],
        "beleza": [f"{name}: Realce sua Beleza com Quem Entende do Assunto", f"Voce Merece se Sentir Incrivel — {name}{loc}"],
        "barbearia": [f"{name}: Estilo e Precisao para o Homem Moderno", f"Corte, Barba e Atitude — {name}{loc}"],
        "imoveis": [f"{name}: Encontre o Imovel dos seus Sonhos{loc}", f"Seu Novo Lar esta Aqui — {name}"],
        "imoveis alto padrao": [f"{name}: Imoveis Exclusivos para Quem Exige o Melhor{loc}", f"Luxo, Privacidade e Exclusividade — {name}"],
        "contabilidade": [f"{name}: Contabilidade Inteligente para sua Empresa Crescer", f"Reduza Impostos e Aumente Lucros com {name}"],
        "tecnologia": [f"{name}: Solucoes Tecnologicas que Transformam Negocios", f"Inovacao e Resultado com {name}"],
        "saas": [f"{name}: A Plataforma que sua Empresa Precisa para Crescer", f"Automatize, Escale e Lucre com {name}"],
        "ia": [f"{name}: Inteligencia Artificial que Transforma seu Negocio", f"Automatize com IA e Multiplique seus Resultados — {name}"],
        "marketing": [f"{name}: Mais Clientes, Mais Vendas, Mais Resultado", f"Escale seu Negocio com {name} — Marketing que Converte"],
        "trafego pago": [f"{name}: Anuncios que Geram Clientes de Verdade", f"ROI Comprovado com {name} — Gestao de Trafego Pago"],
        "lancamentos": [f"{name}: Lancamentos Digitais que Geram Resultados Expressivos", f"Transforme seu Conhecimento em Receita com {name}"],
        "infoprodutos": [f"{name}: Aprenda, Transforme e Conquiste seus Objetivos", f"O Conhecimento que Muda sua Vida esta em {name}"],
        "juridico": [f"{name}: Seus Direitos Defendidos com Experiencia e Dedicacao", f"Justica ao seu Lado — {name}"],
        "direito previdenciario": [f"{name}: Conquiste sua Aposentadoria com Quem Entende do INSS", f"Seus Direitos Previdenciarios Garantidos — {name}"],
        "direito trabalhista": [f"{name}: Defenda seus Direitos Trabalhistas com Especialistas", f"Justica Trabalhista ao seu Lado — {name}"],
        "energia solar": [f"{name}: Economize na Conta de Luz com Energia Solar", f"Energia Limpa e Economia Real — {name}{loc}"],
        "loja construcao": [f"{name}: Tudo que Sua Obra Precisa em Um So Lugar{loc}", f"Do Cimento a Telha — {name} tem o que voce precisa{loc}", f"{name}: Qualidade e Preco Justo para sua Construcao"],
        "construcao": [f"{name}: Construindo Sonhos com Qualidade e Prazo Garantido", f"Sua Obra nas Maos de Quem Entende — {name}"],
        "arquitetura": [f"{name}: Projetos que Transformam Espacos em Experiencias", f"Arquitetura que Inspira — {name}"],
        "gastronomia": [f"{name}: Uma Experiencia Gastronomica Inesquecivel{loc}", f"Sabor, Qualidade e Ambiente — {name}"],
        "hamburgueria": [f"{name}: O Hamburguer Artesanal que Voce Estava Esperando", f"Sabor Real em Cada Mordida — {name}"],
        "cafeteria": [f"{name}: O Cafe Especial que Transforma seu Dia", f"Momentos Especiais Comecem com {name}"],
        "turismo": [f"{name}: Viagens que Criam Memorias Inesqueciveis", f"Explore o Mundo com {name} — Roteiros Exclusivos"],
        "turismo luxo": [f"{name}: Viagens de Luxo para Quem Exige o Melhor", f"Experiencias Exclusivas ao Redor do Mundo — {name}"],
        "casamentos": [f"{name}: O Casamento dos seus Sonhos Realizado com Perfeicao", f"Cada Detalhe Importa — {name}"],
        "curso online": [f"{name}: Aprenda no seu Ritmo e Transforme sua Carreira", f"Conhecimento que Gera Resultado — {name}"],
        "idiomas": [f"{name}: Fale o Mundo com Confianca e Fluencia", f"Aprenda {svc.capitalize()} de Verdade com {name}"],
        "enem vestibular": [f"{name}: Sua Aprovacao Comeca Aqui", f"Prepare-se para o ENEM com Quem Aprova — {name}"],
        "igreja": [f"{name}: Uma Comunidade que Transforma Vidas", f"Fe, Proposito e Comunidade — {name}"],
        "veterinaria": [f"{name}: Cuidado e Amor para o seu Pet{loc}", f"Saude e Bem-Estar para seu Melhor Amigo — {name}"],
        "petshop": [f"{name}: Tudo que seu Pet Precisa em um so Lugar", f"Amor e Cuidado para seu Pet — {name}"],
        "oficina": [f"{name}: Seu Carro nas Maos de Quem Entende{loc}", f"Qualidade e Confianca em Cada Servico — {name}"],
        "estetica automotiva": [f"{name}: Seu Carro Merece o Melhor Tratamento", f"Polimento e Protecao de Nivel Profissional — {name}"],
    }
    if niche in NICHE_H:
        base = NICHE_H[niche]
        if tone == "formal":
            base += [f"{name}: Excelencia em {niche.capitalize()}{loc}", f"Qualidade e Confianca: Conheca o {name}"]
        else:
            base += [f"{name}: {niche.capitalize()} que transforma sua vida{loc}!", f"Descubra por que {name} e o melhor em {niche}{loc}"]
        return base[:5]
    if tone == "formal":
        return [
            f"{name}: Excelencia em {niche.capitalize()}{loc}",
            f"Transforme seus Resultados com {name} — Especialistas em {niche.capitalize()}",
            f"{name} — A Solucao Completa em {svc.capitalize()} que Voce Precisa",
            f"Qualidade e Confianca em {niche.capitalize()}: Conheca o {name}",
            f"{name}: Referencia em {niche.capitalize()} com Resultados Comprovados{loc}",
        ]
    return [
        f"{name}: {niche.capitalize()} que transforma sua vida{loc}!",
        f"Chega de {niche} mediano — conheca o {name}",
        f"O {name} que voce precisava em {svc} esta aqui!",
        f"Descubra por que {name} e o melhor em {niche}{loc}",
        f"{name}: Porque voce merece o melhor em {niche}!",
    ]


def _ctas_formal(intention: str, niche: str = "") -> list:
    NICHE_CTAS: dict = {
        "odontologia": ["Agendar Avaliacao Gratuita", "Quero Meu Sorriso Perfeito"],
        "ortodontia": ["Agendar Consulta", "Quero Alinhar Meu Sorriso"],
        "harmonizacao facial": ["Agendar Avaliacao", "Quero Minha Avaliacao Gratuita"],
        "psicologia": ["Agendar Primeira Sessao", "Quero Iniciar Minha Terapia"],
        "psiquiatria": ["Agendar Consulta", "Quero Atendimento Especializado"],
        "fisioterapia": ["Agendar Avaliacao", "Quero Me Reabilitar"],
        "nutricao": ["Agendar Consulta Nutricional", "Quero Meu Plano Alimentar"],
        "fitness": ["Agendar Visita Gratuita", "Quero Comecar Agora"],
        "crossfit": ["Agendar Aula Experimental", "Quero Minha Aula Gratis"],
        "personal trainer": ["Agendar Avaliacao Fisica", "Quero Meu Treino Personalizado"],
        "pilates": ["Agendar Aula Experimental", "Quero Comecar o Pilates"],
        "beleza": ["Agendar Horario", "Quero Meu Agendamento"],
        "barbearia": ["Agendar Corte", "Reservar Meu Horario"],
        "imoveis": ["Agendar Visita", "Quero Ver Imoveis"],
        "imoveis alto padrao": ["Solicitar Atendimento VIP", "Quero Conhecer os Imoveis"],
        "contabilidade": ["Solicitar Diagnostico Gratuito", "Quero Reduzir Meus Impostos"],
        "tecnologia": ["Solicitar Demonstracao", "Quero Uma Proposta"],
        "saas": ["Testar Gratis por 14 Dias", "Solicitar Demonstracao"],
        "ia": ["Solicitar Demonstracao", "Quero Automatizar meu Negocio"],
        "marketing": ["Solicitar Diagnostico Gratuito", "Quero Mais Clientes"],
        "trafego pago": ["Solicitar Auditoria Gratuita", "Quero Mais Vendas"],
        "lancamentos": ["Quero Participar", "Garantir Minha Vaga"],
        "infoprodutos": ["Quero Comecar Agora", "Acessar o Curso"],
        "juridico": ["Agendar Consulta Juridica", "Quero Minha Consulta"],
        "direito previdenciario": ["Verificar Meu Direito Gratuitamente", "Quero Minha Aposentadoria"],
        "direito trabalhista": ["Verificar Meu Caso Gratuitamente", "Quero Meus Direitos"],
        "energia solar": ["Solicitar Orcamento Gratuito", "Quero Economizar na Luz"],
        "construcao": ["Solicitar Orcamento", "Quero Comecar Minha Obra"],
        "arquitetura": ["Solicitar Consulta", "Quero Meu Projeto"],
        "gastronomia": ["Fazer Reserva", "Ver Cardapio"],
        "hamburgueria": ["Fazer Pedido", "Ver Cardapio"],
        "cafeteria": ["Visitar a Cafeteria", "Ver Cardapio"],
        "turismo": ["Solicitar Orcamento", "Quero Meu Roteiro"],
        "turismo luxo": ["Solicitar Proposta Exclusiva", "Quero Planejar Minha Viagem"],
        "casamentos": ["Agendar Reuniao", "Quero Planejar Meu Casamento"],
        "curso online": ["Quero Me Inscrever", "Acessar o Curso"],
        "idiomas": ["Agendar Aula Experimental", "Quero Aprender Agora"],
        "enem vestibular": ["Quero Me Matricular", "Fazer Aula Experimental"],
        "concursos": ["Quero Me Matricular", "Conhecer o Preparatorio"],
        "igreja": ["Quero Conhecer a Igreja", "Participar do Proximo Culto"],
        "veterinaria": ["Agendar Consulta", "Quero Cuidar do Meu Pet"],
        "petshop": ["Agendar Banho e Tosa", "Quero Meu Agendamento"],
        "oficina": ["Agendar Revisao", "Quero Orcamento Gratuito"],
        "estetica automotiva": ["Agendar Polimento", "Quero Orcamento"],
    }
    if niche in NICHE_CTAS:
        return NICHE_CTAS[niche]
    m = {"captar leads": ["Agendar Consulta Gratuita", "Solicitar Proposta"],
         "vender produto": ["Comprar Agora", "Ver Catalogo Completo"],
         "divulgar evento": ["Garantir Minha Vaga", "Ver Programacao"],
         "apresentar servico": ["Solicitar Proposta", "Conhecer Nossos Servicos"],
         "vender curso": ["Quero Me Inscrever", "Acessar o Curso"]}
    return m.get(intention, ["Entrar em Contato", "Saiba Mais"])


def _ctas_informal(intention: str, niche: str = "") -> list:
    NICHE_CTAS_INF: dict = {
        "fitness": ["Quero comecar agora!", "Me mostra a academia"],
        "crossfit": ["Quero minha aula gratis!", "Bora treinar!"],
        "barbearia": ["Quero agendar meu corte!", "Reservar horario"],
        "beleza": ["Quero agendar!", "Me conta mais"],
        "gastronomia": ["Quero fazer reserva!", "Ver o cardapio"],
        "hamburgueria": ["Quero pedir agora!", "Ver o cardapio"],
        "infoprodutos": ["Quero entrar agora!", "Me mostra o curso"],
        "lancamentos": ["Quero participar!", "Garantir minha vaga"],
        "turismo": ["Quero minha viagem!", "Ver roteiros"],
        "petshop": ["Agendar banho e tosa!", "Quero saber mais"],
        "veterinaria": ["Agendar consulta!", "Quero cuidar do meu pet"],
        "oficina": ["Agendar revisao!", "Quero orcamento"],
        "estetica automotiva": ["Quero polir meu carro!", "Ver servicos"],
    }
    if niche in NICHE_CTAS_INF:
        return NICHE_CTAS_INF[niche]
    m = {"captar leads": ["Quero agendar agora!", "Me conta mais"],
         "vender produto": ["Quero comprar!", "Ver produtos"],
         "divulgar evento": ["Quero participar!", "Ver detalhes"],
         "apresentar servico": ["Quero uma proposta!", "Ver servicos"],
         "vender curso": ["Quero entrar agora!", "Ver o curso"]}
    return m.get(intention, ["Falar com a gente!", "Saiba mais"])


def _build_features(services: list, diffs: list, niche: str, audience: str) -> list:
    ICONS = ["⭐", "🏆", "💎", "🎯", "✅", "🚀", "💡", "🔥", "👑", "🌟", "❤️", "🎪"]
    NICHE_ICONS: dict = {
        "odontologia": ["🦷", "😁", "✨", "🏆", "💎", "🎯"],
        "ortodontia": ["🦷", "😁", "✨", "🎯", "💎", "🏆"],
        "harmonizacao facial": ["✨", "💆", "💎", "🌟", "👑", "🎯"],
        "psicologia": ["🧠", "💚", "🌱", "❤️", "🌟", "🎯"],
        "fisioterapia": ["💪", "🏃", "✅", "🎯", "🌟", "❤️"],
        "nutricao": ["🥗", "💪", "✅", "🌱", "🎯", "🌟"],
        "fitness": ["💪", "🏋️", "🔥", "🎯", "🏆", "⚡"],
        "crossfit": ["🔥", "💪", "⚡", "🏆", "🎯", "🚀"],
        "pilates": ["🧘", "💚", "✨", "🌟", "🎯", "❤️"],
        "yoga": ["🧘", "🌿", "☮️", "💚", "🌟", "✨"],
        "beleza": ["💅", "✨", "💄", "👑", "🌟", "💎"],
        "barbearia": ["✂️", "🪒", "💈", "👑", "🎯", "🏆"],
        "imoveis": ["🏠", "🔑", "💎", "🏆", "🎯", "✅"],
        "imoveis alto padrao": ["🏰", "💎", "👑", "🔑", "✨", "🌟"],
        "tecnologia": ["💻", "🚀", "⚡", "🔧", "🎯", "🌐"],
        "saas": ["☁️", "🚀", "⚡", "🔧", "📊", "🎯"],
        "ia": ["🤖", "🧠", "⚡", "🚀", "💡", "🎯"],
        "marketing": ["📈", "🎯", "🚀", "💡", "🔥", "⭐"],
        "trafego pago": ["📈", "💰", "🎯", "🚀", "⚡", "🔥"],
        "juridico": ["⚖️", "🏛️", "📋", "🎯", "✅", "🏆"],
        "gastronomia": ["🍽️", "👨‍🍳", "⭐", "🌟", "❤️", "🏆"],
        "hamburgueria": ["🍔", "🔥", "⭐", "😋", "🏆", "❤️"],
        "cafeteria": ["☕", "🌟", "❤️", "✨", "🎯", "🏆"],
        "turismo": ["✈️", "🌍", "🏖️", "⭐", "🎯", "🌟"],
        "turismo luxo": ["✈️", "💎", "👑", "🌟", "🏆", "✨"],
        "casamentos": ["💍", "💐", "✨", "❤️", "🌟", "👑"],
        "veterinaria": ["🐾", "❤️", "🏥", "✅", "🌟", "🎯"],
        "petshop": ["🐾", "❤️", "✨", "🌟", "🎯", "💎"],
        "energia solar": ["☀️", "⚡", "💰", "🌱", "✅", "🏆"],
        "infoprodutos": ["📚", "🚀", "💡", "🎯", "🏆", "⭐"],
        "lancamentos": ["🚀", "🔥", "💰", "🎯", "⚡", "🏆"],
        "igreja": ["✝️", "❤️", "🙏", "🌟", "💚", "🕊️"],
        "oficina": ["🔧", "🚗", "✅", "🏆", "🎯", "⚡"],
        "estetica automotiva": ["✨", "🚗", "💎", "🏆", "🎯", "⭐"],
    }
    icons = NICHE_ICONS.get(niche, ICONS)

    # Rich service descriptions by niche — specific copy per service type
    NICHE_SVC_DESCS: dict[str, dict[str, str]] = {
        "odontologia": {
            "Implante Dentario": "Reponha dentes perdidos com implantes de titanio de alta durabilidade, resultado natural e funcional.",
            "Clareamento Dental": "Clinique seu sorriso em ate 8 tons com tecnologia LED de ultima geracao, sem sensibilidade.",
            "Ortodontia": "Aparelhos metalicos, esteticos ou alinhadores invisaveis para um sorriso alinhado e harmonioso.",
            "Faceta de Porcelana": "Restaure a estetica dos seus dentes com facetas ultrafinas e aspecto 100% natural.",
            "Tratamento de Canal": "Procedimento indolor com tecnologia moderna para salvar seu dente e eliminar a dor.",
            "Limpeza Dental": "Remocao de tartaro e manchas com ultrassom para manter sua saude bucal em dia.",
        },
        "ortodontia": {
            "Aparelho Metalico": "Tratamento ortodontico classico e eficaz para alinhar e corrigir a mordida.",
            "Invisalign": "Alinhadores invisiveis e removiveis para corrigir o sorriso discretamente e com conforto.",
            "Aparelho Estetico": "Aparelhos ceramicos ou de safira, quase invisiveis, sem abrir mao da eficiencia.",
        },
        "harmonizacao facial": {
            "Toxina Botulinica": "Suavize linhas de expressao e previna o envelhecimento com aplicacao precisa e natural.",
            "Preenchimento Labial": "Defina e volumize os labios com acido hialuronico para resultado natural e harmonioso.",
            "Bichectomia": "Afine o rosto e realce os zigomas com procedimento minimamente invasivo.",
            "Rinomodelacao": "Corrija imperfeicoes do nariz sem cirurgia com tecnica de preenchimento avancada.",
        },
        "psicologia": {
            "Psicoterapia Individual": "Espaco seguro e acolhedor para voce se conhecer, superar bloqueios e transformar sua vida.",
            "Terapia de Casal": "Fortaleça sua relacao com tecnicas de comunicacao e resolucao de conflitos.",
            "Terapia Online": "Atendimento psicologico pelo computador ou celular, sem sair de casa, com total sigilo.",
            "Terapia Cognitivo-Comportamental": "Metodo cientifico e eficaz para tratar ansiedade, depressao e outros transtornos.",
        },
        "fisioterapia": {
            "Fisioterapia Ortopedica": "Reabilitacao completa de lesoes musculares, osseas e articulares com protocolo personalizado.",
            "Fisioterapia Esportiva": "Recupere-se mais rapido e volte ao esporte com seguranca e desempenho otimizado.",
            "Pilates Clinico": "Fortaleça o core, melhore a postura e alivie dores crônicas com metodo original.",
            "Dry Needling": "Tecnica de agulhamento seco para alivio rapido de dores musculares e pontos de tensao.",
        },
        "nutricao": {
            "Consulta Nutricional": "Avaliacao completa do seu perfil alimentar com plano personalizado para seus objetivos.",
            "Plano Alimentar Personalizado": "Cardapio adaptado ao seu estilo de vida, metabolismo e preferencias alimentares.",
            "Nutricao Esportiva": "Maximize seu desempenho e recuperacao com estrategia nutricional para atletas.",
            "Emagrecimento Saudavel": "Perca peso com saude, sem restricoes absurdas, com acompanhamento contínuo.",
        },
        "fitness": {
            "Musculacao": "Treinamento com pesos para ganho de massa muscular, forca e definicao corporal.",
            "Funcional": "Treinos dinamicos que trabalham o corpo de forma integrada, melhorando condicao fisica geral.",
            "HIIT": "Alta intensidade em menos tempo: queime gordura e melhore o condicionamento cardiovascular.",
            "Aulas Coletivas": "Treinos em grupo com energia contagiante, diversao e resultado garantido.",
            "Avaliacao Fisica": "Mapeamento completo do seu corpo para tracar o melhor plano de treino.",
        },
        "crossfit": {
            "WOD Diario": "Treino do dia variado e desafiador, desenvolvido por coaches certificados.",
            "Fundamentos CrossFit": "Programa de iniciacao completo para aprender os movimentos com seguranca e tecnica.",
            "Levantamento de Peso": "Tecnica de olimpico com coaches especializados para forca e potencia maximas.",
            "Endurance": "Desenvolvimento da resistencia metabolica com treinos especificos de capacidade aerobica.",
        },
        "beleza": {
            "Coloracao": "Tecnicas exclusivas de coloracao com produtos de alta performance e menor agressao.",
            "Luzes e Mechas": "Do babylights ao ombre hair, tecnicas personalizadas para realcar sua cor natural.",
            "Escova Progressiva": "Alise com durabilidade de ate 6 meses com formulas sem formol.",
            "Manicure e Pedicure": "Cuidado completo para maos e pes com esmaltacao duradoura e design personalizado.",
            "Tratamento Capilar": "Reconstrucao profunda para cabelos danificados, ressecados ou com queda.",
        },
        "barbearia": {
            "Corte Masculino": "Corte personalizado ao seu estilo com navalha, maquina e acabamento impecavel.",
            "Barba Completa": "Modelagem, alinhamento e hidratacao da barba com produtos premium e tecnica precisa.",
            "Pigmentacao de Barba": "Disfarce falhas e realce o visual da barba com pigmentacao profissional.",
            "Hidratacao Capilar": "Tratamento intensivo para cabelos ressecados ou danificados pelo calor.",
        },
        "lash design": {
            "Extensao de Cilios Fio a Fio": "Alongamento natural e personalizado para realcar seu olhar com elegancia.",
            "Volume Russo": "Efeito dramático e volumoso com aplicacao de multiplos fios por cilio natural.",
            "Mega Volume": "Olhar intenso e marcante com o maximo de volume e curvatura.",
            "Lash Lifting": "Curvatura permanente dos cilios naturais, sem extensao, para olhar aberto e descansado.",
        },
        "imoveis": {
            "Venda de Imoveis": "Encontre o imovel ideal com nossa carteira exclusiva e avaliacao profissional.",
            "Aluguel Residencial": "Locacao segura com suporte juridico e gestao completa do imovel.",
            "Financiamento Imobiliario": "Orientacao completa para conseguir o melhor financiamento e realizar seu sonho.",
            "Avaliacao de Imoveis": "Laudo tecnico preciso do valor real do seu imovel para venda ou locacao.",
        },
        "contabilidade": {
            "Abertura de Empresa": "Abertura de MEI, ME, LTDA e SA com todo o suporte juridico e fiscal.",
            "Planejamento Tributario": "Reducao legal da carga tributaria com analise do melhor regime para seu negocio.",
            "Declaracao de IR": "Declaracao do Imposto de Renda pessoa fisica e juridica sem erros e no prazo.",
            "Folha de Pagamento": "Gestao completa da folha, esocial, FGTS e obrigacoes trabalhistas.",
        },
        "tecnologia": {
            "Desenvolvimento Web": "Sites institucionais, landing pages e portais modernos, rapidos e responsivos.",
            "Aplicativo Mobile": "Apps iOS e Android com experiencia de usuario intuitiva e performance elevada.",
            "Sistema ERP": "Sistemas integrados de gestao para automatizar processos e ganhar escala.",
            "Automacao de Processos": "Eliminacao de tarefas manuais com RPA e integracao de sistemas.",
        },
        "marketing": {
            "Gestao de Redes Sociais": "Estrategia, criacao de conteudo e publicacao em todas as plataformas relevantes.",
            "Trafego Pago": "Campanhas no Google, Meta e TikTok com gestao de orcamento para maximo ROI.",
            "SEO": "Posicionamento organico no Google para atrair clientes que ja estao buscando voce.",
            "Producao de Conteudo": "Textos, imagens, videos e reels que engajam e convertem seguidores em clientes.",
        },
        "gastronomia": {
            "Almoco Executivo": "Prato principal + sobremesa + bebida em ambiente agradavel e servico agil.",
            "Jantar a La Carte": "Pratos exclusivos preparados com ingredientes frescos e sazonais.",
            "Delivery": "Entrega rapida com embalagem especial para manter sabor e temperatura perfeitos.",
            "Experiencia Gastronomica": "Menu degustacao com harmonizacao de bebidas para uma noite inesquecivel.",
        },
        "hamburgueria": {
            "Hamburguer Artesanal": "Blend exclusivo de carnes nobres, grelhado na chapa e montado na hora.",
            "Smash Burger": "Tecnica americana que cria crosta crocante e interior suculento inigualavel.",
            "Batata Frita Artesanal": "Batata cortada na hora, frita duas vezes para maximo crocante.",
            "Combo Especial": "Hamburguer + batata frita + bebida com desconto exclusivo.",
        },
        "energia solar": {
            "Projeto Solar Residencial": "Dimensionamento e instalacao de paineis fotovoltaicos para sua casa, com economia de ate 95%.",
            "Projeto Solar Comercial": "Solucoes para empresas e industrias com maior consumo e maior retorno.",
            "Monitoramento Online": "Acompanhe em tempo real a geracao de energia pelo app, 24h por dia.",
            "Instalacao Certificada": "Equipe credenciada pela ANEEL com normas ABNT e garantia de 25 anos nos paineis.",
        },
        "loja construcao": {
            "Cimento e Argamassa": "Marcas lideres como Votoran, Votorantim e Itambe, sempre em estoque completo.",
            "Ferragens e Parafusos": "Mais de 5.000 itens em estoque para qualquer necessidade de fixacao e acabamento.",
            "Tintas e Revestimentos": "Suvinil, Coral e marcas premium para acabamento interno e externo com durabilidade.",
            "Material Eletrico e Hidraulico": "Fios, disjuntores, tubos e conexoes de marcas aprovadas por eletricistas e encanadores.",
            "Ferramentas e Equipamentos": "Ferramentas manuais e eletricas para profissionais e autoempreendedores.",
            "Telhas e Coberturas": "Telhas ceramicas, de fibrocimento e metalicas com entrega em obra.",
        },
        "autopecas": {
            "Pecas de Motor": "Pistoes, juntas, rolamentos e componentes originais e paralelos de alta qualidade.",
            "Freios e Suspensao": "Pastilhas, discos, amortecedores e componentes para seguranca e conforto maximos.",
            "Filtros e Oleos": "Linha completa de filtros e oleos lubrificantes para todas as marcas e modelos.",
            "Eletrica Automotiva": "Baterias, alternadores, motores de arranque e componentes eletricos variados.",
        },
        "farmacia": {
            "Medicamentos Sob Receita": "Atendimento farmaceutico especializado com orientacao sobre posologia e interacoes.",
            "Perfumaria e Cosmeticos": "Marcas nacionais e importadas de cuidados com a pele, cabelo e higiene pessoal.",
            "Vitaminas e Suplementos": "Linha completa de vitaminas, minerais e suplementos para saude e bem-estar.",
            "Produtos para Bebe": "Fraldas, higiene e cuidados especificos para recém-nascidos e criancas.",
        },
        "veterinaria": {
            "Consulta Veterinaria": "Atendimento clinico completo com anamnese detalhada e diagnostico preciso.",
            "Vacinacao": "Protocolo vacinal completo para caes e gatos, com carteirinha atualizada.",
            "Cirurgia Veterinaria": "Centro cirurgico equipado para procedimentos eletivos e emergenciais.",
            "Emergencia 24h": "Equipe de plantao 24 horas para atender seu pet em qualquer situacao urgente.",
        },
        "petshop": {
            "Banho e Tosa": "Banho completo com shampoo especifico, secagem e acabamento com perfume.",
            "Tosa Artistica": "Corte personalizado por tosadores especializados em todas as racas.",
            "Hidratacao Pet": "Tratamento intensivo para pelagem seca, opaca ou com excesso de queda.",
            "Acessorios Pet": "Coleiras, roupinhas, brinquedos e produtos para o conforto e diversao do seu pet.",
        },
        "turismo": {
            "Pacotes de Viagem": "Roteiros completos com voo, hotel e passeios inclusos para os melhores destinos.",
            "Roteiros Personalizados": "Viagens feitas sob medida para seus interesses, orcamento e datas.",
            "Seguro Viagem": "Protecao completa para imprevistos medicos e cancelamentos durante sua viagem.",
            "Passagens Aereas": "Melhores tarifas monitoradas 24h para nacionais e internacionais.",
        },
        "casamentos": {
            "Cerimonial Completo": "Coordenacao total do evento, do planejamento ao ultimo detalhe no dia do casamento.",
            "Decoracao": "Conceito visual exclusivo com flores, iluminacao e cenografia para seu estilo.",
            "Buffet": "Cardapio personalizado com opcoes gourmets, veganas e infantis.",
            "Fotografia e Filmagem": "Registro profissional com edicao cinematografica para eternizar cada momento.",
        },
        "educacao": {
            "Curso Online": "Aulas gravadas e ao vivo com professores especialistas e certificado reconhecido.",
            "Mentoria": "Acompanhamento individualizado para acelerar seu desenvolvimento profissional.",
            "Workshop": "Aprendizado intensivo e pratico em formato presencial ou online.",
            "Certificacao": "Diploma e certificado reconhecido pelo mercado para valorizar seu curriculo.",
        },
        "idiomas": {
            "Ingles": "Do basico ao avancado com metodo comunicativo e professores nativos ou certificados.",
            "Espanhol": "Espanhol europeu ou latino-americano com foco em conversacao rapida.",
            "Preparatorio TOEFL/IELTS": "Preparacao intensiva para certificacoes internacionais reconhecidas mundialmente.",
        },
        "juridico": {
            "Consultoria Juridica": "Analise do seu caso com orientacao clara sobre direitos, riscos e melhores caminhos.",
            "Processo Trabalhista": "Defesa ou ajuizamento de acoes trabalhistas com expertise comprovada.",
            "Direito Civil": "Contratos, familia, heranca e responsabilidade civil com atuacao estrategica.",
            "Defesa Criminal": "Defesa tecnica e comprometida em todas as fases do processo penal.",
        },
        "infoprodutos": {
            "Curso Online": "Conteudo gravado, didatico e atualizado, acessivel para sempre apos a compra.",
            "Mentoria em Grupo": "Reunioes ao vivo com especialista, tira-duvidas e comunidade ativa.",
            "Comunidade Paga": "Acesso a grupo exclusivo com conteudo diario, networking e suporte dos membros.",
            "Ebook": "Material didatico completo em PDF para estudo no seu ritmo, onde quiser.",
        },
        "oficina": {
            "Revisao Completa": "Checagem de 50 itens do veiculo com relatorio detalhado e orcamento transparente.",
            "Troca de Oleo": "Oleo original + filtro + revisao basica com os melhores lubrificantes do mercado.",
            "Alinhamento e Balanceamento": "Precisao milimetrica para pneus mais duradouros e direcao mais segura.",
            "Freios": "Substituicao de pastilhas, discos e fluido com garantia de servico.",
        },
        "estetica automotiva": {
            "Polimento Tecnico": "Remocao de arranhoes, oxidacao e imperfeicoes para pintura espelhada.",
            "Vitrificacao": "Protecao ceramica de alta dureza contra raios UV, chuva acida e riscos leves.",
            "Higienizacao Interna": "Limpeza profunda de estofados, tapetes, plasticos e desinfeccao completa.",
            "Lavagem Detalhada": "Lavagem externa com shampoo neutro, descontaminacao e secagem manual.",
        },
        "arquitetura": {
            "Projeto Arquitetonico": "Projeto completo com plantas baixas, cortes, elevacoes e perspectivas 3D.",
            "Projeto de Interiores": "Conceito, layout de moveis, paleta de cores e selecao de materiais.",
            "Projeto 3D": "Visualizacao fotorrealista do espaco antes da execucao para validar cada escolha.",
            "Reforma e Ampliacao": "Projeto de reforma com solucoes criativas dentro do orcamento disponivel.",
        },
        "instagram": {},  # fallback para nicho generico
    }

    svc_descs = NICHE_SVC_DESCS.get(niche, {})
    features = []
    for i, svc in enumerate(services[:4]):
        desc = svc_descs.get(svc) or f"{svc} com qualidade e atendimento especializado para {audience}."
        features.append({"icon": icons[i % len(icons)], "title": svc, "desc": desc})
    remaining = max(0, 4 - len(features))
    for i, diff in enumerate(diffs[:remaining]):
        diff_descs = {
            "Atendimento Premium": "Voce recebe atencao exclusiva e personalizada em cada etapa do atendimento.",
            "Totalmente Personalizado": "Solucao 100% adaptada ao seu perfil, objetivos e necessidades especificas.",
            "Entrega Rapida": "Agilidade sem abrir mao da qualidade — entregamos no prazo combinado.",
            "Garantia de Satisfacao": "Se nao ficar satisfeito, trabalhamos ate resolver. Sua satisfacao e nossa prioridade.",
            "Anos de Experiencia": "Decadas de mercado com centenas de clientes atendidos e resultados comprovados.",
            "Profissionais Certificados": "Equipe com formacao, especializacoes e certificacoes reconhecidas na area.",
            "Tecnologia de Ponta": "Equipamentos e sistemas de ultima geracao para os melhores resultados.",
            "Resultados Comprovados": "Cases reais, depoimentos e metricas que comprovam a eficacia do nosso trabalho.",
            "Disponivel 24h": "Suporte e atendimento disponiveis 24 horas por dia, 7 dias por semana.",
            "Atendimento Online": "Atendemos de onde voce estiver — presencial ou 100% digital conforme sua preferencia.",
            "Consulta Gratuita": "Primeira consulta sem custo para voce conhecer nosso trabalho sem compromisso.",
            "Parcelamento Disponivel": "Parcele sem juros e facilite o acesso ao servico que voce precisa.",
            "Frete Gratis": "Entrega gratuita para sua regiao, sem custo adicional.",
        }
        desc = diff_descs.get(diff, f"{diff} para garantir sua total satisfacao e resultado esperado.")
        features.append({"icon": icons[(len(features)) % len(icons)], "title": diff, "desc": desc})
    if not features:
        niche_defaults = {
            "saude": [
                {"icon": "🏥", "title": "Equipe Especializada", "desc": "Profissionais de saude com formacao e especializacao na area."},
                {"icon": "💊", "title": "Tratamentos Modernos", "desc": "Protocolos atualizados baseados em evidencias cientificas."},
                {"icon": "❤️", "title": "Cuidado Humanizado", "desc": "Atendimento acolhedor que respeita voce e seu bem-estar."},
            ],
            "educacao": [
                {"icon": "📚", "title": "Conteudo Atualizado", "desc": "Material didatico alinhado com as exigencias atuais do mercado."},
                {"icon": "👨‍🏫", "title": "Professores Especialistas", "desc": "Instrutores com experiencia pratica e didatica comprovada."},
                {"icon": "🎓", "title": "Certificacao Reconhecida", "desc": "Diploma e certificados valorizados por recrutadores e empresas."},
            ],
            "tecnologia": [
                {"icon": "💻", "title": "Solucoes sob Medida", "desc": "Desenvolvimento personalizado para as necessidades do seu negocio."},
                {"icon": "🚀", "title": "Entrega Agil", "desc": "Metodologia agil com entregas parciais e total transparencia."},
                {"icon": "🔧", "title": "Suporte Continuo", "desc": "Equipe tecnica disponivel apos entrega para manutencao e evolucao."},
            ],
        }
        # Map niche to sector for default fallback
        NICHE_SECTOR = {
            "odontologia": "saude", "fisioterapia": "saude", "psicologia": "saude",
            "nutricao": "saude", "cardiologia": "saude", "veterinaria": "saude",
            "tecnologia": "tecnologia", "saas": "tecnologia", "ia": "tecnologia",
            "software house": "tecnologia", "desenvolvimento web": "tecnologia",
            "educacao": "educacao", "curso online": "educacao", "idiomas": "educacao",
        }
        sector = NICHE_SECTOR.get(niche, "")
        features = niche_defaults.get(sector, [
            {"icon": icons[0], "title": "Qualidade Comprovada", "desc": f"Excelencia em {niche} com metodologia testada e aprovada pelos nossos clientes."},
            {"icon": icons[1], "title": "Experiencia de Mercado", "desc": "Anos de atuacao com centenas de clientes satisfeitos em todo o Brasil."},
            {"icon": icons[2], "title": "Suporte Dedicado", "desc": "Nossa equipe esta disponivel para atender, orientar e resolver qualquer duvida."},
            {"icon": icons[3] if len(icons) > 3 else icons[0], "title": "Resultado Garantido", "desc": "Trabalhamos com metas claras e acompanhamento constante para garantir seus resultados."},
        ])
    return features


def _build_testimonials(ctx: dict) -> list:
    name = ctx["business_name"] or ctx["business_type"]
    niche = ctx["niche"]
    count = ctx["testimonial_count"]
    NICHE_T: dict = {
        "odontologia": [
            (f"Fiz meu implante no {name} e o resultado foi incrivel! Sorriso perfeito, profissionais atenciosos.", "Carla M."),
            (f"Sempre tive medo de dentista, mas o {name} mudou isso. Atendimento humanizado e sem dor.", "Pedro S."),
            (f"Clareamento dental feito no {name}: resultado em 1 sessao. Meu sorriso nunca esteve tao bonito!", "Ana L."),
        ],
        "psicologia": [
            (f"A terapia com o {name} transformou minha vida. Aprendi a lidar com a ansiedade e hoje me sinto muito mais leve.", "Julia R."),
            (f"Estava em um momento muito dificil quando comecei no {name}. O acolhimento fez toda a diferenca.", "Marcos T."),
            (f"Recomendo o {name} para todos. A terapia me ajudou a me conhecer melhor.", "Fernanda C."),
        ],
        "fisioterapia": [
            (f"Tive uma lesao no joelho e achei que nao voltaria a correr. O {name} me reabilitou completamente em 3 meses!", "Roberto A."),
            (f"Dor nas costas cronica resolvida com o tratamento do {name}. Profissionais excelentes.", "Silvia P."),
            (f"Pos-operatorio muito mais tranquilo com o acompanhamento do {name}. Recuperacao rapida.", "Carlos E."),
        ],
        "fitness": [
            (f"Perdi 15kg em 4 meses com o {name}! Os instrutores sao incriveis e a estrutura e top.", "Thiago M."),
            (f"O {name} mudou minha relacao com o exercicio. Hoje nao consigo imaginar minha vida sem treinar aqui.", "Beatriz S."),
            (f"Resultado real e rapido! O acompanhamento personalizado do {name} fez toda a diferenca.", "Lucas F."),
        ],
        "crossfit": [
            (f"O {name} e mais que uma academia, e uma familia! Os coaches sao incriveis.", "Diego R."),
            (f"Nunca imaginei que conseguiria fazer os movimentos do CrossFit. O {name} me provou que sou capaz de muito mais!", "Camila T."),
            (f"Comunidade incrivel, treinos desafiadores e resultados reais. O {name} e o melhor investimento.", "Andre L."),
        ],
        "beleza": [
            (f"Saio do {name} me sentindo uma nova pessoa! Profissionais talentosos e atendimento de primeira.", "Patricia O."),
            (f"Meu cabelo nunca esteve tao saudavel e bonito. O {name} usa produtos de qualidade.", "Renata B."),
            (f"Atendimento impecavel e resultado que supera as expectativas. O {name} e meu salao de confianca.", "Mariana V."),
        ],
        "barbearia": [
            (f"Melhor barbearia da cidade! O {name} entende exatamente o que voce quer.", "Felipe G."),
            (f"Ambiente incrivel, atendimento de primeira e corte impecavel. O {name} e minha barbearia de cabeceira.", "Rodrigo M."),
            (f"Barba e cabelo sempre perfeitos no {name}. Profissionais que realmente entendem de estilo masculino.", "Bruno C."),
        ],
        "imoveis": [
            (f"O {name} encontrou o apartamento perfeito para minha familia em tempo record.", "Claudia F."),
            (f"Processo de compra do meu primeiro imovel foi muito tranquilo com o {name}.", "Eduardo S."),
            (f"Vendi meu imovel pelo melhor preco do mercado com a ajuda do {name}.", "Lucia M."),
        ],
        "contabilidade": [
            (f"O {name} reduziu minha carga tributaria em 40%. Profissionais competentes.", "Empresa ABC"),
            (f"Desde que contratei o {name}, minha empresa cresceu com muito mais seguranca financeira.", "Joao P."),
            (f"Abertura de empresa feita em tempo record e sem dor de cabeca. O {name} cuida de tudo.", "Maria S."),
        ],
        "tecnologia": [
            (f"O {name} desenvolveu nosso sistema e transformou completamente nossa operacao. ROI em menos de 6 meses.", "Empresa XYZ"),
            (f"Parceria incrivel com o {name}. Entregaram o projeto no prazo e com qualidade excepcional.", "Startup ABC"),
            (f"O {name} entendeu exatamente nossa necessidade e criou uma solucao que superou todas as expectativas.", "Diretor TI"),
        ],
        "marketing": [
            (f"Com o {name} triplicamos nossas vendas em 3 meses. Estrategia certeira e resultados mensuraveis.", "Empresa DEF"),
            (f"O {name} transformou nossa presenca digital. Hoje somos referencia no nosso segmento.", "CEO Startup"),
            (f"ROI de 500% nas campanhas gerenciadas pelo {name}. Profissionais que entendem de performance.", "Loja Online"),
        ],
        "gastronomia": [
            (f"Melhor experiencia gastronomica que ja tive! O {name} tem um ambiente incrivel.", "Gustavo R."),
            (f"Comida deliciosa, atendimento impecavel e ambiente aconchegante. O {name} e meu restaurante favorito!", "Isabela M."),
            (f"Fiz meu aniversario no {name} e foi perfeito. Tudo impecavel, do atendimento a sobremesa.", "Familia Silva"),
        ],
        "turismo": [
            (f"A viagem organizada pelo {name} foi a melhor da minha vida! Cada detalhe foi pensado com carinho.", "Casal Oliveira"),
            (f"Roteiro perfeito, hoteis incriveis e atendimento 24h. O {name} faz a diferenca.", "Ana C."),
            (f"Ja fiz 5 viagens com o {name} e cada uma foi melhor que a anterior. Confianca total!", "Roberto F."),
        ],
        "casamentos": [
            (f"O {name} realizou o casamento dos nossos sonhos! Cada detalhe foi perfeito.", "Noivos Silva"),
            (f"Profissionalismo e dedicacao do {name} fizeram nosso casamento ser inesquecivel.", "Noivos Costa"),
            (f"Desde o primeiro contato ate o dia do casamento, o {name} nos deu total seguranca.", "Noivos Pereira"),
        ],
        "veterinaria": [
            (f"O {name} salvou a vida do meu cachorro! Equipe competente e que realmente ama os animais.", "Tutora Ana"),
            (f"Minha gata recebe o melhor cuidado no {name}. Profissionais que tratam nossos pets como familia.", "Tutor Carlos"),
            (f"Atendimento de emergencia rapido e eficiente no {name}. Meu pet se recuperou completamente!", "Tutora Maria"),
        ],
        "energia solar": [
            (f"Instalei paineis solares com o {name} e minha conta de luz caiu 90%! Investimento que se paga rapido.", "Joao S."),
            (f"Processo de instalacao rapido e sem complicacoes. O {name} cuidou de tudo.", "Empresa ABC"),
            (f"Melhor investimento que fiz! O {name} entregou um projeto de qualidade.", "Familia Oliveira"),
        ],
        "infoprodutos": [
            (f"O curso do {name} transformou minha carreira! Conteudo pratico e que gera resultado real.", "Aluno Pedro"),
            (f"Ja fiz varios cursos online, mas o {name} e diferente. Metodologia unica e suporte incrivel.", "Aluna Carla"),
            (f"Apliquei o que aprendi no {name} e em 30 dias ja vi resultados. Vale cada centavo investido!", "Aluno Lucas"),
        ],
        "oficina": [
            (f"Meu carro estava com um problema que nenhuma oficina resolvia. O {name} diagnosticou e resolveu na hora!", "Paulo R."),
            (f"Atendimento honesto e preco justo. O {name} e a unica oficina em que confio meu carro.", "Sandra M."),
            (f"Revisao completa feita com qualidade e no prazo. O {name} e referencia em mecanica.", "Carlos T."),
        ],
        "farmacia": [
            (f"Sempre que preciso de medicamento, vou ao {name}. Atendimento rapido, 24 horas e os farmaceuticos tiram todas as duvidas.", "Claudia R."),
            (f"O {name} tem tudo que preciso em um so lugar: remedio, perfumaria e higiene pessoal. Atendimento excelente e preco justo.", "Mario S."),
            (f"Me surpreendi com o atendimento farmaceutico do {name}. Explicaram direitinho sobre o meu medicamento e as interacoes. Recomendo muito!", "Patricia O."),
            (f"Farmacia que funciona 24h e ainda tem atendimento humanizado e de qualidade. O {name} e minha farmacia de confianca em Franca.", "Rafael M."),
        ],
        "autopecas": [
            (f"Encontrei a peca que nenhuma loja tinha no {name}. Atendimento rapido e preco justo. Recomendo para todos os mecanicos.", "Marcelo G."),
            (f"Compro pecas no {name} ha anos. Qualidade garantida, entrega rapida e equipe que entende do assunto.", "Carlos A."),
            (f"O {name} tem um estoque impressionante. Acabei com meu problema no mesmo dia, sem precisar encomendar.", "Rodrigo P."),
        ],
        "loja construcao": [
            (f"O {name} tem tudo que preciso para minha obra em um so lugar. Entrega rapida e preco competitivo.", "Engenheiro Rafael S."),
            (f"Como mestre de obras, sempre indico o {name} para os clientes. Material de qualidade e equipe que entende de construcao.", "Joao Mestre"),
            (f"Reformei minha casa inteira com materiais do {name}. Otimo atendimento e os produtos chegaram dentro do prazo.", "Ana Paula C."),
        ],
        "optica": [
            (f"Fiz meu exame de vista no {name} e meus novos oculos ficaram prontos no mesmo dia. Servico impecavel!", "Sandra M."),
            (f"Os optometristas do {name} foram super atenciosos e me ajudaram a escolher a armacao perfeita para meu rosto.", "Beatriz T."),
            (f"Compro meus oculos no {name} ha 5 anos. Qualidade excelente, variedade de armacoes e preco justo.", "Carlos F."),
        ],
        "veterinaria": [
            (f"O {name} salvou a vida do meu cachorro! Equipe competente, emergencia 24h e que realmente ama os animais.", "Tutora Ana"),
            (f"Minha gata recebe o melhor cuidado no {name}. Profissionais que tratam nossos pets como familia.", "Tutor Carlos"),
            (f"Atendimento de emergencia rapido e eficiente no {name}. Meu pet se recuperou completamente!", "Tutora Maria"),
        ],
        "petshop": [
            (f"Meu cachorro ama ir ao {name}! Saiu lindo, perfumado e super feliz. Os tosadores sao incriveis.", "Tutora Carla"),
            (f"Atendimento carinhoso e profissional no {name}. Minha gata fica sempre em boas maos.", "Tutor Pedro"),
            (f"O {name} tem tudo para o meu pet: banho, tosa, racao e acessorios. Ambiente limpo e equipe dedicada.", "Tutora Luciana"),
        ],
    }
    if niche in NICHE_T:
        templates = NICHE_T[niche]
    else:
        templates = [
            (f"O {name} superou todas as minhas expectativas. Profissionalismo e qualidade em {niche} que raramente se encontra!", "Maria S."),
            (f"Recomendo muito o {name}! Atendimento excelente e resultados incriveis. Voltarei com certeza.", "Joao P."),
            (f"Finalmente encontrei um {niche} de qualidade. O {name} e referencia no que faz!", "Ana C."),
            (f"Servico impecavel do {name}. Equipe dedicada e resultados que superam o esperado.", "Carlos M."),
            (f"Melhor investimento que fiz! O {name} transformou minha experiencia com {niche}.", "Fernanda L."),
            (f"Atendimento humanizado e profissional. O {name} realmente se importa com seus clientes.", "Roberto A."),
        ]
    return [{"text": t[0], "author": t[1]} for t in templates[:min(count, len(templates))]]


def _build_pricing(ctx: dict) -> list:
    niche = ctx["niche"]
    NICHE_P: dict = {
        "odontologia": [
            {"name": "Consulta", "price": "R$ 150", "features": ["Avaliacao completa", "Radiografia", "Plano de tratamento", "Orientacoes"], "highlight": False},
            {"name": "Tratamento Basico", "price": "A partir de R$ 500", "features": ["Limpeza profissional", "Restauracoes", "Fluoretacao", "Retorno incluido"], "highlight": True},
            {"name": "Tratamento Premium", "price": "Sob consulta", "features": ["Implante ou Faceta", "Clareamento", "Acompanhamento completo", "Garantia"], "highlight": False},
        ],
        "fitness": [
            {"name": "Mensal", "price": "R$ 89/mes", "features": ["Acesso ilimitado", "Aulas coletivas", "Vestiario", "Wi-Fi"], "highlight": False},
            {"name": "Trimestral", "price": "R$ 69/mes", "features": ["Tudo do Mensal", "Avaliacao fisica", "Planilha de treino", "Desconto 22%"], "highlight": True},
            {"name": "Anual", "price": "R$ 49/mes", "features": ["Tudo do Trimestral", "Personal 2x/mes", "Nutricao basica", "Desconto 45%"], "highlight": False},
        ],
        "marketing": [
            {"name": "Starter", "price": "R$ 1.500/mes", "features": ["2 redes sociais", "12 posts/mes", "Stories diarios", "Relatorio mensal"], "highlight": False},
            {"name": "Growth", "price": "R$ 3.000/mes", "features": ["4 redes sociais", "20 posts/mes", "Trafego pago incluso", "Reuniao semanal"], "highlight": True},
            {"name": "Scale", "price": "R$ 6.000/mes", "features": ["Tudo do Growth", "Producao de video", "Influencer marketing", "Gerente dedicado"], "highlight": False},
        ],
        "tecnologia": [
            {"name": "Basico", "price": "R$ 2.500", "features": ["Site institucional", "5 paginas", "Responsivo", "SEO basico"], "highlight": False},
            {"name": "Profissional", "price": "R$ 6.000", "features": ["Site + Blog", "10 paginas", "Integracao CRM", "SEO avancado"], "highlight": True},
            {"name": "Enterprise", "price": "Sob consulta", "features": ["Sistema customizado", "Integracao completa", "Suporte dedicado", "SLA garantido"], "highlight": False},
        ],
        "infoprodutos": [
            {"name": "Basico", "price": "R$ 197", "features": ["Acesso ao curso", "Material de apoio", "Certificado", "Suporte por email"], "highlight": False},
            {"name": "Completo", "price": "R$ 497", "features": ["Tudo do Basico", "Mentoria em grupo", "Comunidade exclusiva", "Atualizacoes vitalicas"], "highlight": True},
            {"name": "VIP", "price": "R$ 997", "features": ["Tudo do Completo", "Mentoria individual", "Acesso antecipado", "Bonus exclusivos"], "highlight": False},
        ],
        "saas": [
            {"name": "Starter", "price": "R$ 99/mes", "features": ["Ate 5 usuarios", "Funcionalidades basicas", "Suporte por email", "Atualizacoes"], "highlight": False},
            {"name": "Pro", "price": "R$ 299/mes", "features": ["Ate 20 usuarios", "Todas as funcionalidades", "Suporte prioritario", "API inclusa"], "highlight": True},
            {"name": "Enterprise", "price": "Sob consulta", "features": ["Usuarios ilimitados", "Customizacao", "Gerente dedicado", "SLA garantido"], "highlight": False},
        ],
    }
    if niche in NICHE_P:
        return NICHE_P[niche]
    return [
        {"name": "Basico", "price": "R$ 99/mes", "features": [f"{niche.capitalize()} essencial", "Suporte por e-mail", "1 usuario"], "highlight": False},
        {"name": "Profissional", "price": "R$ 199/mes", "features": [f"{niche.capitalize()} completo", "Suporte prioritario", "5 usuarios", "Relatorios"], "highlight": True},
        {"name": "Enterprise", "price": "Sob consulta", "features": ["Tudo do Profissional", "Usuarios ilimitados", "Gerente dedicado", "SLA garantido"], "highlight": False},
    ]


def _build_faq(ctx: dict) -> list:
    name = ctx["business_name"] or ctx["business_type"]
    niche = ctx["niche"]
    NICHE_F: dict = {
        "odontologia": [
            {"q": "A consulta de avaliacao e gratuita?", "a": f"Sim! No {name} oferecemos avaliacao inicial gratuita para que voce conheca nossos servicos sem compromisso."},
            {"q": "Voces aceitam convenio?", "a": f"Trabalhamos com os principais convenios odontologicos. Entre em contato para verificar se o seu convenio e aceito no {name}."},
            {"q": "Quanto tempo dura o tratamento?", "a": f"O tempo varia conforme o tratamento. Na avaliacao, nossa equipe do {name} apresentara um plano detalhado com prazos."},
            {"q": "O tratamento e doloroso?", "a": f"No {name} utilizamos tecnicas modernas e anestesia de ultima geracao para garantir seu conforto durante todo o tratamento."},
        ],
        "psicologia": [
            {"q": "Como funciona a primeira sessao?", "a": f"A primeira sessao e uma conversa inicial onde voce pode conhecer o terapeuta do {name} e entender como funciona o processo terapeutico."},
            {"q": "Voces atendem online?", "a": f"Sim! O {name} oferece atendimento presencial e online, para que voce possa fazer terapia de onde estiver."},
            {"q": "Quanto tempo dura cada sessao?", "a": f"As sessoes no {name} tem duracao de 50 minutos, com frequencia semanal recomendada."},
            {"q": "O sigilo e garantido?", "a": f"Absolutamente. O {name} segue rigorosamente o Codigo de Etica do CFP, garantindo total sigilo e confidencialidade."},
        ],
        "fitness": [
            {"q": "Posso fazer uma aula experimental?", "a": f"Sim! O {name} oferece aula experimental gratuita para que voce conheca nossa estrutura antes de se matricular."},
            {"q": "Tem personal trainer incluso?", "a": f"Nossos planos incluem acompanhamento de instrutores qualificados. Para treino 100% personalizado, temos planos de personal trainer."},
            {"q": "Qual o horario de funcionamento?", "a": f"O {name} funciona de segunda a sexta das 6h as 22h, sabados das 8h as 18h e domingos das 8h as 13h."},
            {"q": "Posso cancelar a qualquer momento?", "a": f"Nossos planos mensais podem ser cancelados a qualquer momento. Para planos trimestrais e anuais, consulte nossa politica."},
        ],
        "contabilidade": [
            {"q": "Voces atendem empresas de todos os portes?", "a": f"Sim! O {name} atende desde MEI e microempresas ate grandes corporacoes, com solucoes personalizadas."},
            {"q": "Como funciona a migracao do meu contador atual?", "a": f"O {name} cuida de todo o processo de migracao de forma transparente e sem interrupcao dos seus servicos."},
            {"q": "Voces fazem planejamento tributario?", "a": f"Sim! O planejamento tributario e um dos nossos principais servicos. Identificamos oportunidades legais para reduzir impostos."},
            {"q": "Qual o prazo para entrega das obrigacoes?", "a": f"O {name} garante o cumprimento de todos os prazos fiscais e contabeis, evitando multas para sua empresa."},
        ],
        "tecnologia": [
            {"q": "Qual o prazo de desenvolvimento?", "a": f"O prazo varia conforme a complexidade. O {name} apresenta um cronograma detalhado na proposta, com entregas parciais definidas."},
            {"q": "Voces oferecem suporte apos a entrega?", "a": f"Sim! O {name} oferece suporte tecnico pos-entrega, com planos de manutencao e evolucao do sistema."},
            {"q": "O projeto fica hospedado onde?", "a": f"Utilizamos infraestrutura cloud de alta disponibilidade. O {name} cuida de toda a configuracao e seguranca."},
            {"q": "Posso solicitar alteracoes durante o desenvolvimento?", "a": f"Sim! Trabalhamos com metodologia agil, permitindo ajustes ao longo do projeto com total transparencia."},
        ],
        "marketing": [
            {"q": "Em quanto tempo vejo resultados?", "a": f"Os primeiros resultados aparecem em 30-60 dias. O {name} apresenta relatorios mensais detalhados para acompanhar a evolucao."},
            {"q": "Voces criam o conteudo ou preciso fornecer?", "a": f"O {name} cuida de toda a producao de conteudo: textos, imagens, videos e estrategia. Voce so precisa aprovar."},
            {"q": "Qual o investimento minimo em anuncios?", "a": f"Recomendamos investimento minimo de R$ 1.000/mes em midia paga. O {name} gerencia o orcamento com maxima eficiencia."},
            {"q": "Posso cancelar o contrato?", "a": f"Nossos contratos sao mensais, sem fidelidade. O {name} acredita que voce deve ficar por resultado, nao por obrigacao."},
        ],
        "energia solar": [
            {"q": "Em quanto tempo o investimento se paga?", "a": f"Em media, o retorno do investimento com o {name} ocorre entre 3 e 5 anos, com economia de ate 95% na conta de luz."},
            {"q": "Preciso de autorizacao da distribuidora?", "a": f"Sim, mas o {name} cuida de toda a documentacao e aprovacao junto a distribuidora de energia da sua regiao."},
            {"q": "Os paineis funcionam em dias nublados?", "a": f"Sim! Os paineis instalados pelo {name} geram energia mesmo em dias nublados, com eficiencia reduzida mas funcional."},
            {"q": "Qual a garantia dos equipamentos?", "a": f"O {name} trabalha com equipamentos de primeira linha, com garantia de 25 anos nos paineis e 10 anos nos inversores."},
        ],
        "farmacia": [
            {"q": "Quais medicamentos voces vendem?", "a": f"O {name} trabalha com medicamentos com e sem receita, genericos, similares e de referencia. Tambem fazemos manipulacao de formulas especiais."},
            {"q": "O {name} funciona 24 horas?", "a": f"Sim! O {name} atende 24 horas por dia, 7 dias por semana, incluindo feriados, para que voce nunca fique sem o seu medicamento."},
            {"q": "Voces entregam em casa?", "a": f"Sim! O {name} oferece servico de delivery de medicamentos e produtos. Consulte nossa area de entrega e horarios disponíveis."},
            {"q": "Posso solicitar orientacao farmaceutica?", "a": f"Com certeza! No {name} contamos com farmaceuticos responsaveis disponiveis para orientar sobre medicamentos, posologia, interacoes e cuidados necessarios."},
        ],
        "autopecas": [
            {"q": "Voces trabalham com pecas originais e paralelas?", "a": f"Sim! O {name} oferece pecas originais, paralelas e recondicionadas de qualidade para todas as marcas e modelos."},
            {"q": "Tem garantia nas pecas?", "a": f"Todas as pecas vendidas pelo {name} possuem garantia do fabricante. Trabalhamos apenas com fornecedores certificados."},
            {"q": "Fazem instalacao das pecas?", "a": f"O {name} e especializado em venda de pecas. Para instalacao, podemos indicar oficinas parceiras de confianca na regiao."},
            {"q": "Qual o prazo para pecas sob encomenda?", "a": f"Pecas que nao estao no estoque podem ser encomendadas com prazo de 2 a 5 dias uteis. Fale com nossa equipe."},
        ],
        "optica": [
            {"q": "O exame de vista e gratuito?", "a": f"Sim! O {name} oferece exame de vista gratuito com nossos optometristas para te ajudar a escolher as lentes certas."},
            {"q": "Qual o prazo para ficar pronto o oculos?", "a": f"Oculos simples ficam prontos em ate 1 hora. Lentes progressivas e especiais podem levar de 3 a 7 dias uteis no {name}."},
            {"q": "Voces aceitam convenio?", "a": f"Sim! O {name} trabalha com os principais convenios de saude. Consulte nossa equipe para verificar seu plano."},
            {"q": "E possivel comprar so a armacao?", "a": f"Claro! No {name} voce pode comprar armacoes avulsas e aproveitar suas lentes atuais, ou montar o oculos completo conosco."},
        ],
        "loja construcao": [
            {"q": "Voces entregam os materiais na obra?", "a": f"Sim! O {name} oferece entrega de materiais diretamente na sua obra em Franca e regiao. Consulte prazos e areas de atendimento."},
            {"q": "Tem desconto para compras em quantidade?", "a": f"Sim! O {name} oferece tabela especial para construtores, engenheiros e compras em grande volume. Solicite orcamento."},
            {"q": "Voces tem assessoria tecnica?", "a": f"Nossa equipe do {name} esta preparada para auxiliar na escolha dos materiais certos para cada etapa da sua obra."},
            {"q": "Qual a forma de pagamento?", "a": f"O {name} aceita dinheiro, pix, cartao de debito e credito, e oferece faturamento para empresas do setor."},
        ],
        "veterinaria": [
            {"q": "Voces atendem emergencias?", "a": f"Sim! O {name} possui plantao de emergencia 24 horas para atender seu pet em situacoes urgentes."},
            {"q": "Quais especies voces atendem?", "a": f"O {name} atende caes, gatos, aves, coelhos e pequenos mamiferos. Consulte nossa equipe para outras especies."},
            {"q": "Precisao de agendamento?", "a": f"Consultas de rotina precisam de agendamento. Emergencias sao atendidas imediatamente, sem necessidade de hora marcada."},
            {"q": "Voces fazem vacinacao?", "a": f"Sim! O {name} segue o protocolo vacinal completo para caes e gatos, com carteirinha digital atualizada."},
        ],
        "petshop": [
            {"q": "Preciso agendar o banho e tosa?", "a": f"Recomendamos agendamento pelo WhatsApp ou telefone do {name} para garantir horario. Em alguns casos atendemos sem agendamento."},
            {"q": "Quanto tempo leva o banho e tosa?", "a": f"Dependendo do porte e pelagem do pet, o servico no {name} leva de 1h30 a 3 horas. Avisamos quando estiver pronto."},
            {"q": "Quais racas voces atendem?", "a": f"O {name} atende todas as racas de caes e gatos. Temos tosadores especializados em racas com tosa especifica."},
            {"q": "Os produtos usados sao seguros?", "a": f"Sim! O {name} usa apenas produtos hipoalergênicos, dermato testados e seguros para pets de todas as idades."},
        ],
    }
    if niche in NICHE_F:
        return NICHE_F[niche]

    # Smart generic fallback — avoids "serviço" language for product-based niches
    LOJA_NICHES = {"farmacia", "autopecas", "loja construcao", "optica", "floricultura",
                   "loja moveis", "papelaria", "loja esportes", "loja brinquedos",
                   "loja informatica", "moda feminina", "moda masculina", "moda infantil",
                   "moda", "e-commerce", "petshop", "perfumaria", "joalheria"}
    if niche in LOJA_NICHES:
        return [
            {"q": f"Qual o horario de funcionamento do {name}?", "a": f"Consulte nossos horarios de atendimento pelo WhatsApp ou Instagram. Estamos prontos para atender voce!"},
            {"q": "Voces fazem entrega?", "a": f"Sim! O {name} oferece opcoes de entrega. Entre em contato para saber sobre prazos e areas atendidas."},
            {"q": "Qual a forma de pagamento aceita?", "a": f"O {name} aceita dinheiro, pix, cartao de debito e credito. Parcelamento disponivel conforme a compra."},
            {"q": "Como faço para tirar duvidas sobre um produto?", "a": f"Fale diretamente com nossa equipe do {name} pelo WhatsApp. Respondemos rapido e ajudamos a encontrar o produto certo."},
        ]
    return [
        {"q": f"Como funciona o atendimento do {name}?", "a": f"E simples: entre em contato pelo formulario ou WhatsApp e nossa equipe especializada em {niche} responde rapidamente."},
        {"q": "Qual o horario de atendimento?", "a": f"Entre em contato com o {name} para conhecer nossos horarios. Temos opcoes de atendimento presencial e online."},
        {"q": "Voces atendem minha regiao?", "a": f"O {name} atende localmente e em todo o Brasil via atendimento online ou entrega. Consulte nossa equipe."},
        {"q": "Como posso entrar em contato?", "a": f"Preencha o formulario nesta pagina, fale pelo WhatsApp ou visite o {name} pessoalmente. Respondemos em breve."},
    ]


# ══════════════════════════════════════════════════════════════════════════════
# DESIGN
# ══════════════════════════════════════════════════════════════════════════════

def generate_design(ctx: dict, brand_color, accent_color) -> dict:
    style = ctx["visual_style"]
    colors = ctx["colors"]
    PALETTES = {
        "minimalista": {"primary": "#2D3748", "accent": "#4299E1", "bg": "#F7FAFC", "bg2": "#EDF2F7"},
        "corporativo":  {"primary": "#084753", "accent": "#D8AC4D", "bg": "#F7FAFC", "bg2": "#E6F4F6"},
        "moderno":      {"primary": "#084753", "accent": "#D8AC4D", "bg": "#F0F9FA", "bg2": "#D4EEF1"},
        "agressivo":    {"primary": "#C53030", "accent": "#F6E05E", "bg": "#FFF5F5", "bg2": "#FED7D7"},
    }
    FONTS = {
        "minimalista": ("Inter", "Inter"),
        "corporativo":  ("Merriweather", "Open Sans"),
        "moderno":      ("Poppins", "Lato"),
        "agressivo":    ("Oswald", "Roboto"),
    }
    palette = dict(PALETTES.get(style, PALETTES["moderno"]))
    if brand_color and brand_color not in ("#084753", "#1A365D"):
        palette["primary"] = brand_color
    elif colors:
        palette["primary"] = colors[0]
    if accent_color and accent_color not in ("#D8AC4D", "#F6AD55"):
        palette["accent"] = accent_color
    elif len(colors) > 1:
        palette["accent"] = colors[1]
    primary_lum = _luminance(palette["primary"])
    accent_lum = _luminance(palette["accent"])
    palette["text_on_primary"] = "#FFFFFF" if primary_lum < 0.35 else "#1A202C"
    palette["text_on_accent"] = "#FFFFFF" if accent_lum < 0.35 else "#1A202C"
    if primary_lum > 0.6:
        palette["primary"] = _darken(palette["primary"], 0.4)
        palette["text_on_primary"] = "#FFFFFF"
    if accent_lum < 0.05:
        palette["accent"] = _lighten(palette["accent"], 0.3)
        palette["text_on_accent"] = "#1A202C"
    palette["text"] = "#1A202C"
    palette["text_muted"] = "#718096"
    palette["white"] = "#FFFFFF"
    hf, bf = FONTS.get(style, ("Poppins", "Lato"))
    return {"palette": palette, "heading_font": hf, "body_font": bf}

def _luminance(hex_color: str) -> float:
    """Calculate relative luminance (0=black, 1=white)."""
    try:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return 0.5
        r, g, b = int(h[0:2], 16)/255, int(h[2:4], 16)/255, int(h[4:6], 16)/255
        def lin(c):
            return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
        return 0.2126*lin(r) + 0.7152*lin(g) + 0.0722*lin(b)
    except Exception:
        return 0.5


def _darken(hex_color: str, amount: float) -> str:
    """Darken a hex color by amount (0-1)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = max(0, int(r * (1 - amount)))
        g = max(0, int(g * (1 - amount)))
        b = max(0, int(b * (1 - amount)))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color


def _lighten(hex_color: str, amount: float) -> str:
    """Lighten a hex color by amount (0-1)."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r = min(255, int(r + (255 - r) * amount))
        g = min(255, int(g + (255 - g) * amount))
        b = min(255, int(b + (255 - b) * amount))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color


# ══════════════════════════════════════════════════════════════════════════════
# SECTION BUILDER
# ══════════════════════════════════════════════════════════════════════════════


# ── Niche default section layouts ─────────────────────────────────────────────
NICHE_SECTION_DEFAULTS = {
    "odontologia":         ["features", "about", "testimonials", "faq", "form", "map"],
    "ortodontia":          ["features", "about", "testimonials", "faq", "form", "map"],
    "harmonizacao facial": ["features", "gallery", "testimonials", "faq", "form"],
    "dermatologia":        ["features", "about", "testimonials", "faq", "form"],
    "psicologia":          ["features", "about", "testimonials", "faq", "form"],
    "psiquiatria":         ["features", "about", "faq", "form"],
    "fisioterapia":        ["features", "about", "testimonials", "faq", "form", "map"],
    "nutricao":            ["features", "about", "testimonials", "faq", "form"],
    "saude":               ["features", "about", "testimonials", "faq", "form", "map"],
    "cardiologia":         ["features", "about", "testimonials", "faq", "form", "map"],
    "pediatria":           ["features", "about", "testimonials", "faq", "form", "map"],
    "veterinaria":         ["features", "about", "testimonials", "faq", "form", "map"],
    "petshop":             ["features", "gallery", "testimonials", "form", "map"],
    "farmacia":            ["features", "about", "testimonials", "faq", "map"],
    "beleza":              ["features", "gallery", "testimonials", "pricing", "form", "map"],
    "barbearia":           ["features", "gallery", "testimonials", "pricing", "form", "map"],
    "lash design":         ["features", "gallery", "testimonials", "form", "map"],
    "nail design":         ["features", "gallery", "testimonials", "pricing", "form", "map"],
    "sobrancelhas":        ["features", "gallery", "testimonials", "form", "map"],
    "estetica corporal":   ["features", "gallery", "testimonials", "pricing", "form"],
    "spa":                 ["features", "gallery", "testimonials", "pricing", "form", "map"],
    "fitness":             ["features", "pricing", "testimonials", "faq", "form", "map"],
    "crossfit":            ["features", "pricing", "testimonials", "faq", "form", "map"],
    "pilates":             ["features", "pricing", "about", "testimonials", "form", "map"],
    "yoga":                ["features", "pricing", "about", "testimonials", "form", "map"],
    "personal trainer":    ["features", "about", "testimonials", "pricing", "faq", "form"],
    "gastronomia":         ["features", "gallery", "testimonials", "map"],
    "hamburgueria":        ["features", "gallery", "testimonials", "map"],
    "pizzaria":            ["features", "gallery", "testimonials", "map"],
    "cafeteria":           ["features", "gallery", "testimonials", "map"],
    "confeitaria":         ["features", "gallery", "testimonials", "form", "map"],
    "construcao":          ["features", "gallery", "about", "testimonials", "form"],
    "loja construcao":     ["features", "about", "testimonials", "form", "map"],
    "arquitetura":         ["features", "gallery", "about", "testimonials", "form"],
    "design interiores":   ["features", "gallery", "about", "testimonials", "form"],
    "energia solar":       ["features", "about", "testimonials", "faq", "form"],
    "reformas":            ["features", "gallery", "testimonials", "form"],
    "moveis planejados":   ["features", "gallery", "testimonials", "faq", "form", "map"],
    "imoveis":             ["features", "gallery", "about", "testimonials", "faq", "form"],
    "imoveis alto padrao": ["features", "gallery", "about", "testimonials", "form"],
    "contabilidade":       ["features", "about", "testimonials", "faq", "form"],
    "financas":            ["features", "about", "testimonials", "faq", "form"],
    "seguros":             ["features", "about", "testimonials", "faq", "form"],
    "holding":             ["features", "about", "faq", "form"],
    "tecnologia":          ["features", "about", "testimonials", "pricing", "faq", "form"],
    "saas":                ["features", "pricing", "testimonials", "faq", "form"],
    "desenvolvimento web": ["features", "gallery", "testimonials", "pricing", "form"],
    "educacao":            ["features", "about", "testimonials", "pricing", "faq", "form"],
    "curso online":        ["features", "about", "testimonials", "pricing", "faq", "form"],
    "idiomas":             ["features", "pricing", "testimonials", "faq", "form"],
    "marketing":           ["features", "about", "testimonials", "pricing", "faq", "form"],
    "trafego pago":        ["features", "testimonials", "pricing", "faq", "form"],
    "juridico":            ["features", "about", "testimonials", "faq", "form"],
    "direito trabalhista": ["features", "about", "testimonials", "faq", "form"],
    "turismo":             ["features", "gallery", "testimonials", "pricing", "form"],
    "casamentos":          ["features", "gallery", "testimonials", "faq", "form"],
    "fotografia":          ["features", "gallery", "testimonials", "pricing", "form"],
    "infoprodutos":        ["features", "about", "testimonials", "pricing", "faq", "form"],
    "lancamentos":         ["features", "testimonials", "countdown", "pricing", "faq", "form"],
    "igreja":              ["features", "about", "testimonials", "map"],
    "oficina":             ["features", "about", "testimonials", "faq", "form", "map"],
    "estetica automotiva": ["features", "gallery", "testimonials", "pricing", "form", "map"],
    "autopecas":           ["features", "about", "testimonials", "form", "map"],
    "e-commerce":          ["features", "testimonials", "pricing", "faq", "form"],
    "moda":                ["features", "gallery", "testimonials", "pricing", "form"],
    "moda feminina":       ["features", "gallery", "testimonials", "pricing", "form"],
}


def build_sections(ctx: dict) -> list[dict]:
    """Build niche-aware section list, then apply user overrides from prompt."""
    niche = ctx.get("niche", "negocios")

    default_body = NICHE_SECTION_DEFAULTS.get(niche, [
        "features", "about", "testimonials", "faq", "form",
    ])

    sections = [{"type": "header"}]
    for i in range(ctx.get("banner_count", 1)):
        sections.append({"type": "hero", "index": i})

    for sec_type in default_body:
        sections.append({"type": sec_type})

    present = {s["type"] for s in sections}

    # Apply explicit user requests
    if ctx.get("wants_gallery") and "gallery" not in present:
        idx = next((i for i, s in enumerate(sections) if s["type"] == "testimonials"), len(sections) - 1)
        sections.insert(idx, {"type": "gallery"})
        present.add("gallery")
    if ctx.get("wants_video") and "video" not in present:
        sections.insert(3, {"type": "video"})
        present.add("video")
    if ctx.get("wants_pricing") and "pricing" not in present:
        idx = next((i for i, s in enumerate(sections) if s["type"] in ("testimonials", "form", "cta")), len(sections) - 1)
        sections.insert(idx, {"type": "pricing"})
        present.add("pricing")
    if ctx.get("wants_faq") and "faq" not in present:
        idx = next((i for i, s in enumerate(sections) if s["type"] in ("form", "map", "cta")), len(sections) - 1)
        sections.insert(idx, {"type": "faq"})
        present.add("faq")
    if "about" in ctx.get("sections_requested", []) and "about" not in present:
        sections.insert(3, {"type": "about"})
        present.add("about")
    if "partners" in ctx.get("sections_requested", []):
        sections.append({"type": "partners"})
    if "countdown" in ctx.get("sections_requested", []) and "countdown" not in present:
        sections.insert(2, {"type": "countdown"})

    # Map: add if address/schedule found
    if (ctx.get("wants_map") or ctx.get("address") or ctx.get("schedule")) and "map" not in present:
        sections.append({"type": "map"})
    # Form: ensure present if lead capture needed
    if ctx.get("wants_form") and "form" not in {s["type"] for s in sections}:
        sections.append({"type": "form"})

    sections.append({"type": "cta"})
    sections.append({"type": "footer"})

    # Deduplicate preserving order (keep hero duplicates for multi-banner)
    seen: set[str] = set()
    unique = []
    for s in sections:
        key = s["type"]
        if key not in seen or key == "hero":
            seen.add(key)
            unique.append(s)
    return unique

# ══════════════════════════════════════════════════════════════════════════════
# HTML RENDERER
# ══════════════════════════════════════════════════════════════════════════════

def render_html(ctx: dict, copy: dict, design: dict, sections: list[dict], logo_url: str | None = None) -> tuple[str, str]:
    p = design["palette"]
    hf = design["heading_font"]
    bf = design["body_font"]
    name = copy["display_name"]
    cta1 = copy["ctas"][0]
    cta2 = copy["ctas"][1] if len(copy["ctas"]) > 1 else cta1
    loc = f" | {ctx['location']}" if ctx["location"] else ""
    phone = ctx.get("phone", "")
    email = ctx.get("email", "")
    wa = ctx.get("wa", "")
    ig = ctx.get("ig", "")

    address = ctx.get("address", "")
    schedule = ctx.get("schedule", [])

    css = _build_css(p, hf, bf, niche=ctx.get("niche", ""))
    body_parts = []

    for sec in sections:
        t = sec["type"]
        if t == "header":   body_parts.append(_sec_header(name, cta1, p, hf, wa, logo_url=logo_url))
        elif t == "hero":   body_parts.append(_sec_hero(copy, p, hf, bf, cta1, cta2, sec.get("index", 0), ctx))
        elif t == "features": body_parts.append(_sec_features(copy["features"], p, hf, bf, name, ctx["audience"], niche=ctx.get("niche", "")))
        elif t == "about":  body_parts.append(_sec_about(name, ctx["niche"], ctx["differentials"], p, hf, bf, extra_info=ctx.get("extra_info", "") or ctx.get("custom_info", [""])[0] if ctx.get("custom_info") else "", location=ctx.get("location", "")))
        elif t == "gallery": body_parts.append(_sec_gallery(name, ctx["niche"], p, hf))
        elif t == "video":  body_parts.append(_sec_video(name, p, hf))
        elif t == "pricing": body_parts.append(_sec_pricing(copy["pricing"], p, hf, bf, cta1))
        elif t == "testimonials": body_parts.append(_sec_testimonials(copy["testimonials"], p, hf, bf, niche=ctx.get("niche", "")))
        elif t == "partners": body_parts.append(_sec_partners(p, hf))
        elif t == "faq":    body_parts.append(_sec_faq(copy["faq"], p, hf, bf))
        elif t == "countdown": body_parts.append(_sec_countdown(p, hf, bf, cta1))
        elif t == "form":   body_parts.append(_sec_form(ctx["form_fields"], p, hf, bf, cta1, name))
        elif t == "map":    body_parts.append(_sec_map(name, ctx["location"], p, hf, bf, phone, email, address=address, schedule=schedule))
        elif t == "cta":    body_parts.append(_sec_cta(name, ctx["niche"], cta2, p, hf, bf))
        elif t == "footer": body_parts.append(_sec_footer(name, ctx["niche"], loc, p, hf, bf, phone, email, wa, ig, address=address, schedule=schedule))

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{copy['seo_title']}</title>
  <meta name="description" content="{copy['seo_description']}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family={hf.replace(' ', '+')}:wght@400;600;700;800&family={bf.replace(' ', '+')}:wght@400;500;600&display=swap" rel="stylesheet">
  <style>{css}</style>
</head>
<body>
{''.join(body_parts)}
</body>
</html>"""
    return html, css


def _build_css(p, hf, bf, niche: str = ""):
    pri = p["primary"]
    acc = p["accent"]
    bg = p.get("bg", "#F7FAFC")
    bg2 = p.get("bg2", "#EDF2F7")
    top = p.get("text_on_primary", "#FFFFFF")
    toa = p.get("text_on_accent", "#1A202C")
    txt = p.get("text", "#1A202C")
    mut = p.get("text_muted", "#718096")

    return f"""
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'{bf}',sans-serif;color:{txt};line-height:1.6}}
a{{text-decoration:none}}
.container{{max-width:1100px;margin:0 auto;padding:0 24px}}
.header{{background:{pri};padding:16px 48px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.2)}}
.logo{{color:{top};font-family:'{hf}',sans-serif;font-size:1.4rem;font-weight:700}}
.nav-cta{{background:{acc};color:{toa};padding:10px 24px;border-radius:6px;font-weight:700;font-size:.9rem}}
.hero{{background:linear-gradient(135deg,{pri} 0%,{_darken(pri, 0.15)} 100%);color:{top};padding:120px 48px 100px;text-align:center}}
.hero-badge{{display:inline-block;background:rgba(255,255,255,.15);color:{top};padding:6px 16px;border-radius:20px;font-size:.85rem;margin-bottom:24px;border:1px solid rgba(255,255,255,.3)}}
.hero h1{{font-family:'{hf}',sans-serif;font-size:3rem;margin-bottom:24px;line-height:1.15;max-width:800px;margin-left:auto;margin-right:auto}}
.hero p{{font-size:1.2rem;opacity:.9;margin-bottom:48px;max-width:620px;margin-left:auto;margin-right:auto}}
.hero-buttons{{display:flex;justify-content:center;gap:16px;flex-wrap:wrap}}
.btn-primary{{background:{acc};color:{toa};padding:18px 48px;border-radius:8px;font-size:1.05rem;font-weight:700;display:inline-block;box-shadow:0 4px 12px rgba(0,0,0,.2);transition:transform .2s}}
.btn-primary:hover{{transform:translateY(-2px)}}
.btn-outline{{background:transparent;color:{top};padding:18px 48px;border:2px solid rgba(255,255,255,.7);border-radius:8px;font-size:1.05rem;font-weight:600;display:inline-block}}
.section{{padding:80px 48px}}
.section-alt{{background:{bg}}}
.section-dark{{background:{pri};color:{top}}}
.section h2{{font-family:'{hf}',sans-serif;font-size:2.2rem;margin-bottom:16px;text-align:center;color:{pri}}}
.section-dark h2{{color:{top}}}
.section .subtitle{{text-align:center;color:{mut};font-size:1.05rem;margin-bottom:48px;max-width:560px;margin-left:auto;margin-right:auto}}
.section-dark .subtitle{{color:rgba(255,255,255,.8)}}
.features-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:24px;max-width:1100px;margin:0 auto}}
.feature-card{{background:#fff;padding:32px 24px;border-radius:16px;box-shadow:0 2px 12px rgba(0,0,0,.07);text-align:center;border:1px solid {bg2};transition:transform .2s}}
.feature-card:hover{{transform:translateY(-4px)}}
.feature-icon{{font-size:2.5rem;margin-bottom:16px}}
.feature-card h3{{font-family:'{hf}',sans-serif;color:{pri};font-size:1.1rem;margin-bottom:8px}}
.feature-card p{{color:{mut};font-size:.9rem}}
.testimonials-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px;max-width:1100px;margin:0 auto}}
.testimonial-card{{background:rgba(255,255,255,.1);border-radius:16px;padding:32px;border:1px solid rgba(255,255,255,.15)}}
.testimonial-text{{font-size:1rem;font-style:italic;line-height:1.8;margin-bottom:16px;color:{top}}}
.testimonial-author{{font-weight:600;opacity:.85;font-size:.9rem;color:{top}}}
.pricing-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px;max-width:900px;margin:0 auto}}
.pricing-card{{background:#fff;border-radius:16px;padding:40px 32px;text-align:center;box-shadow:0 2px 12px rgba(0,0,0,.08);border:2px solid {bg2}}}
.pricing-card.highlight{{border-color:{pri};transform:scale(1.05)}}
.pricing-name{{font-family:'{hf}',sans-serif;font-size:1.2rem;color:{pri};margin-bottom:8px}}
.pricing-price{{font-size:2.5rem;font-weight:700;color:{pri};margin:16px 0}}
.pricing-features{{list-style:none;margin:24px 0;text-align:left}}
.pricing-features li{{padding:8px 0;border-bottom:1px solid {bg2};font-size:.9rem;color:#4a5568}}
.pricing-features li::before{{content:"\2713 ";color:{pri};font-weight:700}}
.faq-list{{max-width:760px;margin:0 auto}}
.faq-item{{background:#fff;border-radius:12px;padding:24px;margin-bottom:16px;box-shadow:0 1px 6px rgba(0,0,0,.06)}}
.faq-q{{font-family:'{hf}',sans-serif;font-size:1.05rem;color:{pri};margin-bottom:10px;font-weight:600}}
.faq-a{{color:{mut};font-size:.95rem;line-height:1.7}}
.form-wrapper{{max-width:560px;margin:0 auto;background:#fff;padding:48px;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.1)}}
.form-group{{margin-bottom:20px}}
.form-group label{{display:block;font-size:.875rem;font-weight:600;color:{pri};margin-bottom:6px}}
.form-group input,.form-group textarea,.form-group select{{width:100%;padding:12px 16px;border:2px solid {bg2};border-radius:8px;font-size:1rem;font-family:'{bf}',sans-serif}}
.form-group input:focus,.form-group textarea:focus{{outline:none;border-color:{pri}}}
.btn-submit{{width:100%;background:{pri};color:{top};padding:16px;border:none;border-radius:8px;font-size:1.05rem;font-weight:700;cursor:pointer}}
.cta-section{{background:{bg2};padding:96px 48px;text-align:center}}
.cta-section h2{{font-family:'{hf}',sans-serif;font-size:2.4rem;color:{pri};margin-bottom:16px}}
.cta-section p{{color:{mut};font-size:1.1rem;margin-bottom:48px;max-width:520px;margin-left:auto;margin-right:auto}}
.btn-cta{{background:{pri};color:{top};padding:20px 56px;border-radius:8px;font-size:1.1rem;font-weight:700;display:inline-block;box-shadow:0 4px 16px rgba(0,0,0,.15)}}
.footer{{background:#1a202c;color:#a0aec0;padding:48px}}
.footer-inner{{max-width:1100px;margin:0 auto;display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:32px}}
.footer-brand{{font-family:'{hf}',sans-serif;color:#fff;font-size:1.2rem;font-weight:700;margin-bottom:12px}}
.footer-desc{{font-size:.875rem;line-height:1.7}}
.footer-title{{font-family:'{hf}',sans-serif;color:#fff;font-size:.95rem;font-weight:600;margin-bottom:12px}}
.footer-links{{list-style:none}}
.footer-links li{{margin-bottom:8px;font-size:.875rem}}
.footer-bottom{{max-width:1100px;margin:32px auto 0;padding-top:24px;border-top:1px solid #2d3748;text-align:center;font-size:.8rem}}
.stats{{display:flex;justify-content:center;gap:64px;flex-wrap:wrap;margin-bottom:48px}}
.stat-number{{font-family:'{hf}',sans-serif;font-size:3rem;font-weight:700;color:{acc};line-height:1}}
.stat-label{{font-size:.9rem;opacity:.8;margin-top:6px;color:{top}}}
.gallery-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;max-width:1100px;margin:0 auto}}
.gallery-item{{background:{bg2};border-radius:12px;height:200px;display:flex;align-items:center;justify-content:center;font-size:3rem}}
.about-inner{{display:grid;grid-template-columns:1fr 1fr;gap:64px;align-items:center;max-width:1000px;margin:0 auto}}
.about-text h2{{font-family:'{hf}',sans-serif;font-size:2rem;color:{pri};margin-bottom:16px;text-align:left}}
.about-text p{{color:{mut};line-height:1.8;margin-bottom:16px}}
.about-visual{{background:linear-gradient(135deg,{pri},{_darken(pri, 0.2)});border-radius:24px;height:320px;display:flex;align-items:center;justify-content:center;font-size:5rem}}
.map-section{{background:{bg}}}
.map-info{{display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:start;max-width:1000px;margin:0 auto}}
.map-placeholder{{background:{bg2};border-radius:16px;height:300px;display:flex;align-items:center;justify-content:center;font-size:4rem;border:2px dashed {pri}}}
.contact-info h3{{font-family:'{hf}',sans-serif;color:{pri};margin-bottom:16px}}
.contact-item{{display:flex;align-items:center;gap:12px;margin-bottom:16px;font-size:.95rem;color:#4a5568}}
@media(max-width:768px){{
  .hero h1{{font-size:2rem}}
  .hero,.section{{padding:60px 24px}}
  .header{{padding:14px 24px}}
  .about-inner,.map-info{{grid-template-columns:1fr}}
  .pricing-card.highlight{{transform:none}}
  .stats{{gap:32px}}
  .form-wrapper{{padding:32px 24px}}
}}
@media(max-width:480px){{
  .hero h1{{font-size:1.7rem}}
  .btn-primary,.btn-outline,.btn-cta{{padding:14px 28px;font-size:.95rem}}
}}
""" + _niche_css_overrides(niche, pri, acc, bg, bg2, top, toa, txt, mut, hf, bf)


# ── Niche-specific CSS overrides — visual identity per sector ─────────────────

def _niche_css_overrides(niche: str, pri: str, acc: str, bg: str, bg2: str,
                          top: str, toa: str, txt: str, mut: str, hf: str, bf: str) -> str:
    """
    Returns additional CSS classes that give each sector a unique visual identity.
    Appended to the base CSS. Does NOT override — only adds specializations.
    """
    # Map niche to sector
    SECTOR = {
        # SAÚDE — clean, trust, calm blues/greens
        "odontologia": "saude", "ortodontia": "saude", "dermatologia": "saude",
        "psicologia": "saude", "psiquiatria": "saude", "fisioterapia": "saude",
        "nutricao": "saude", "cardiologia": "saude", "ginecologia": "saude",
        "pediatria": "saude", "veterinaria": "saude", "laboratorio": "saude",
        "acupuntura": "saude", "fertilidade": "saude", "saude": "saude",
        "harmonizacao facial": "estetica", "procedimentos esteticos": "estetica",
        "estetica corporal": "estetica", "skincare": "estetica",
        # BELEZA — elegante, rosé, gradient
        "beleza": "beleza", "barbearia": "barbearia", "lash design": "beleza",
        "nail design": "beleza", "sobrancelhas": "beleza", "maquiagem": "beleza",
        "spa": "beleza", "depilacao": "beleza",
        # FITNESS — energético, bold, escuro
        "fitness": "fitness", "crossfit": "fitness", "pilates": "fitness",
        "yoga": "fitness", "personal trainer": "fitness", "jiu-jitsu": "fitness",
        "boxe": "fitness", "artes marciais": "fitness",
        # FOOD — quente, apetitoso, textured
        "gastronomia": "food", "hamburgueria": "food", "pizzaria": "food",
        "cafeteria": "food", "confeitaria": "food", "sorveteria": "food",
        "delivery": "food", "food truck": "food",
        # MODA — clean, editorial, tipografia grande
        "moda feminina": "moda", "moda masculina": "moda", "moda infantil": "moda",
        "moda": "moda", "e-commerce": "moda",
        # TECH — dark, neon accent, moderno
        "tecnologia": "tech", "saas": "tech", "ia": "tech", "cybersecurity": "tech",
        "desenvolvimento web": "tech", "app mobile": "tech", "software house": "tech",
        "devops": "tech", "blockchain": "tech",
        # JURÍDICO / FINANCEIRO — sóbrio, confiável
        "juridico": "corporativo", "direito trabalhista": "corporativo",
        "direito previdenciario": "corporativo", "direito familia": "corporativo",
        "contabilidade": "corporativo", "financas": "corporativo",
        "investimentos": "corporativo", "seguros": "corporativo",
        "holding": "corporativo", "bpo financeiro": "corporativo",
        # CONSTRUÇÃO — robusto, terroso
        "construcao": "construcao", "loja construcao": "construcao",
        "arquitetura": "construcao", "design interiores": "construcao",
        "energia solar": "construcao", "reformas": "construcao",
        "marcenaria": "construcao", "moveis planejados": "construcao",
        # EDUCAÇÃO — vibrante, amigável
        "educacao": "educacao", "curso online": "educacao", "idiomas": "educacao",
        "mentoria": "educacao", "infoprodutos": "educacao",
        "enem vestibular": "educacao", "lancamentos": "educacao",
        # IMÓVEIS — premium, espacoso
        "imoveis": "imoveis", "imoveis alto padrao": "imoveis",
        # IGREJA — acolhedor, espiritual
        "igreja": "igreja",
    }

    sector = SECTOR.get(niche, "")

    extras = {
        "saude": f"""
/* Saúde: bordas suaves, ícone médico, cards com borda azul-esverdeada */
.feature-card{{border-top:3px solid {acc};border-radius:12px}}
.hero{{background:linear-gradient(150deg,{pri} 0%,{_darken(pri,0.1)} 60%,{_lighten(pri,0.05)} 100%)}}
.section h2{{font-size:2rem;letter-spacing:-.5px}}
.testimonial-card{{border-left:4px solid {acc};background:rgba(255,255,255,.07);border-radius:8px}}
.faq-item{{border-left:3px solid {acc}}}
.faq-q{{color:{pri}}}
.btn-primary{{border-radius:50px}}
.btn-cta{{border-radius:50px}}
.nav-cta{{border-radius:50px}}
""",
        "estetica": f"""
/* Estética: gradiente rose, bordas arredondadas, elegante */
.hero{{background:linear-gradient(135deg,{pri} 0%,{_lighten(pri,0.1)} 50%,{_darken(pri,0.05)} 100%)}}
.feature-card{{border-radius:20px;box-shadow:0 4px 20px rgba(0,0,0,.08)}}
.btn-primary,.btn-cta,.nav-cta{{border-radius:50px;letter-spacing:.5px}}
.section h2{{letter-spacing:-1px;font-size:2.4rem}}
.gallery-item{{border-radius:20px;overflow:hidden}}
""",
        "beleza": f"""
/* Beleza: clean, rosa suave, tipografia elegante */
.hero{{background:linear-gradient(135deg,{pri} 0%,{_darken(pri,0.08)} 100%)}}
.feature-card{{border-radius:20px;border-top:3px solid {acc}}}
.btn-primary,.btn-cta,.nav-cta{{border-radius:50px}}
.section h2{{letter-spacing:-1px}}
.gallery-item{{border-radius:16px}}
.testimonial-card{{border-radius:20px;border:1px solid rgba(255,255,255,.25)}}
""",
        "barbearia": f"""
/* Barbearia: bold, dark, textura mascu */
.hero{{background:linear-gradient(160deg,{pri} 0%,{_darken(pri,0.25)} 100%)}}
.feature-card{{border-left:4px solid {acc};border-radius:4px;text-align:left}}
.section h2{{text-transform:uppercase;letter-spacing:2px;font-size:1.8rem}}
.btn-primary,.nav-cta{{border-radius:0px;text-transform:uppercase;letter-spacing:1px}}
.btn-cta{{border-radius:0;text-transform:uppercase;letter-spacing:2px}}
.testimonial-card{{border-left:3px solid {acc};border-radius:0}}
""",
        "fitness": f"""
/* Fitness: bold, energético, angular */
.hero{{background:linear-gradient(160deg,{_darken(pri,0.1)} 0%,{pri} 50%,{_darken(pri,0.2)} 100%)}}
.feature-card{{border-radius:4px;border-bottom:4px solid {acc};text-align:left;padding-left:28px}}
.section h2{{text-transform:uppercase;letter-spacing:1px;font-size:2rem}}
.hero h1{{font-size:3.5rem;text-transform:uppercase;letter-spacing:-1px}}
.btn-primary{{border-radius:0;text-transform:uppercase;letter-spacing:1px;padding:18px 56px}}
.btn-cta{{border-radius:0;text-transform:uppercase;letter-spacing:2px}}
.nav-cta{{border-radius:0;text-transform:uppercase;font-size:.8rem;letter-spacing:1px}}
.stat-number{{font-size:3.5rem}}
""",
        "food": f"""
/* Food: quente, apetitoso, arredondado */
.hero{{background:linear-gradient(135deg,{_darken(pri,0.05)} 0%,{pri} 100%)}}
.feature-card{{border-radius:16px;background:linear-gradient(135deg,#fff 0%,{bg} 100%)}}
.feature-icon{{font-size:3rem}}
.section h2{{font-size:2.5rem;letter-spacing:-1px}}
.hero h1{{font-size:3.2rem}}
.btn-primary{{border-radius:50px;font-size:1.1rem}}
.btn-cta{{border-radius:50px}}
.testimonial-card{{border-radius:16px;border:none;background:rgba(255,255,255,.12)}}
.gallery-item{{border-radius:12px}}
""",
        "moda": f"""
/* Moda: editorial, clean, tipografia grande */
.hero{{background:{pri};padding:140px 48px 120px}}
.hero h1{{font-size:3.8rem;letter-spacing:-2px;line-height:1.05}}
.hero-badge{{display:none}}
.feature-card{{border-radius:0;box-shadow:none;border:1px solid {bg2};border-radius:2px}}
.section h2{{font-size:2.8rem;letter-spacing:-1.5px}}
.btn-primary{{border-radius:0;text-transform:uppercase;letter-spacing:2px;font-size:.9rem}}
.btn-cta{{border-radius:0;text-transform:uppercase;letter-spacing:2px}}
.nav-cta{{border-radius:2px}}
.gallery-item{{border-radius:0}}
.pricing-card{{border-radius:0;border:1px solid {bg2}}}
""",
        "tech": f"""
/* Tech: dark accent, futurista, neon */
.hero{{background:linear-gradient(135deg,{pri} 0%,{_darken(pri,0.2)} 60%,{_darken(pri,0.1)} 100%)}}
.feature-card{{background:#fff;border-top:2px solid {acc};border-radius:8px}}
.section h2{{letter-spacing:-1px;font-size:2.3rem}}
.hero h1{{font-size:3.2rem;letter-spacing:-1.5px}}
.btn-primary{{border-radius:6px;background:linear-gradient(135deg,{acc},{_rotate_hue_css(acc,30)})}}
.nav-cta{{border-radius:6px}}
.testimonial-card{{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1)}}
.stat-number{{font-size:3.5rem;background:linear-gradient(135deg,{acc},{_lighten(acc,0.3)});-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
""",
        "corporativo": f"""
/* Corporativo/Jurídico: sóbrio, confiável, clássico */
.hero{{background:linear-gradient(135deg,{pri} 0%,{_darken(pri,0.15)} 100%)}}
.feature-card{{border-top:3px solid {acc};border-radius:4px}}
.section h2{{font-size:2rem;letter-spacing:-.5px}}
.btn-primary{{border-radius:4px}}
.btn-cta{{border-radius:4px}}
.faq-item{{border-left:3px solid {acc};border-radius:0 8px 8px 0}}
.testimonial-card{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12)}}
""",
        "construcao": f"""
/* Construção: robusto, sólido, terroso */
.hero{{background:linear-gradient(160deg,{pri} 0%,{_darken(pri,0.2)} 100%)}}
.feature-card{{border-radius:4px;border-left:4px solid {acc};text-align:left}}
.feature-icon{{font-size:2.2rem}}
.section h2{{text-transform:uppercase;letter-spacing:1px;font-size:1.9rem}}
.btn-primary{{border-radius:2px;text-transform:uppercase;letter-spacing:1px}}
.btn-cta{{border-radius:2px;text-transform:uppercase;letter-spacing:1px}}
.nav-cta{{border-radius:2px}}
""",
        "educacao": f"""
/* Educação: vibrante, amigável, motivador */
.hero{{background:linear-gradient(135deg,{pri} 0%,{_darken(pri,0.1)} 100%)}}
.feature-card{{border-radius:16px;border-bottom:3px solid {acc}}}
.section h2{{font-size:2.2rem}}
.btn-primary{{border-radius:12px;font-size:1.1rem}}
.btn-cta{{border-radius:12px}}
.nav-cta{{border-radius:8px}}
.testimonial-card{{border-radius:16px}}
""",
        "imoveis": f"""
/* Imóveis: premium, espacoso, moderno */
.hero{{background:linear-gradient(150deg,{pri} 0%,{_darken(pri,0.12)} 100%);padding:140px 48px 120px}}
.hero h1{{font-size:3.4rem;letter-spacing:-1.5px}}
.feature-card{{border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.1)}}
.section h2{{font-size:2.4rem;letter-spacing:-1px}}
.btn-primary{{border-radius:6px;padding:20px 56px}}
.btn-cta{{border-radius:6px;padding:22px 64px}}
.gallery-item{{border-radius:8px;height:240px}}
""",
        "igreja": f"""
/* Igreja: acolhedor, espiritual, sereno */
.hero{{background:linear-gradient(135deg,{pri} 0%,{_darken(pri,0.1)} 100%)}}
.feature-card{{border-radius:16px;border-top:3px solid {acc}}}
.section h2{{font-size:2rem;letter-spacing:-.5px}}
.btn-primary,.btn-cta,.nav-cta{{border-radius:50px}}
.testimonial-card{{border-radius:16px;border:1px solid rgba(255,255,255,.2)}}
""",
    }

    return extras.get(sector, "")


def _rotate_hue_css(hex_color: str, degrees: float) -> str:
    """Rotate hue of hex color by degrees — for CSS gradient use."""
    try:
        import colorsys
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16)/255, int(h[2:4], 16)/255, int(h[4:6], 16)/255
        hh, s, v = colorsys.rgb_to_hsv(r, g, b)
        hh = (hh + degrees / 360) % 1.0
        r2, g2, b2 = colorsys.hsv_to_rgb(hh, s, v)
        return f"#{int(r2*255):02X}{int(g2*255):02X}{int(b2*255):02X}"
    except Exception:
        return hex_color


# ── Section renderers ─────────────────────────────────────────────────────────

def _sec_header(name, cta1, p, hf, wa, logo_url=None):
    top = p.get("text_on_primary", "#FFFFFF")
    acc = p["accent"]
    toa = p.get("text_on_accent", "#1A202C")
    wa_btn = f'<a href="https://wa.me/55{wa}" class="nav-cta" style="background:#25D366;color:#fff">WhatsApp</a>' if wa else f'<a href="#contato" class="nav-cta">{cta1}</a>'
    if logo_url:
        # Strip any accidental base URL prefix (e.g. http://localhost:8000data:...)
        clean_logo = logo_url
        if 'data:' in logo_url and not logo_url.startswith('data:'):
            clean_logo = logo_url[logo_url.index('data:'):]
        logo_html = (f'<a href="#inicio" class="logo-link" aria-label="{name}">'
                     f'<img src="{clean_logo}" alt="Logo {name}" class="header-logo-img" /></a>')
        logo_css = '.logo-link{display:flex;align-items:center;text-decoration:none}.header-logo-img{height:48px;width:auto;object-fit:contain;max-width:180px}'
    else:
        logo_html = f'<span class="logo">{name}</span>'
        logo_css = ''
    return f'<header class="header">{logo_html}{wa_btn}</header><style>{logo_css}</style>'


def _sec_hero(copy, p, hf, bf, cta1, cta2, idx, ctx):
    niche = ctx["niche"]
    btype = ctx.get("business_type", niche.capitalize())
    loc = f" em {ctx['location']}" if ctx["location"] else ""
    top = p.get("text_on_primary", "#FFFFFF")
    headline = copy["headline_variations"][idx % len(copy["headline_variations"])]
    subtitle = copy["subtitle"] if idx == 0 else f"Descubra tudo que {copy['display_name']} pode fazer por voce{loc}."
    # Use business_type for badge, not the generic niche slug
    badge_text = btype if btype and btype.lower() != "empresa" else niche.capitalize()
    badge = f"{badge_text}{loc}"
    return f"""
<section class="hero" id="{'inicio' if idx == 0 else f'banner{idx+1}'}">
  <div class="hero-badge">{badge}</div>
  <h1>{headline}</h1>
  <p>{subtitle}</p>
  <div class="hero-buttons">
    <a href="#contato" class="btn-primary">{cta1}</a>
    <a href="#servicos" class="btn-outline">Conhecer servicos</a>
  </div>
</section>"""


def _sec_features(features, p, hf, bf, name, audience, niche=""):
    NICHE_FEATURE_TITLE = {
        "odontologia": "Nossos Tratamentos", "ortodontia": "Nossos Tratamentos",
        "harmonizacao facial": "Nossos Procedimentos", "dermatologia": "Nossos Tratamentos",
        "psicologia": "Como Podemos Te Ajudar", "fisioterapia": "Nossos Tratamentos",
        "nutricao": "Nossos Servicos", "saude": "Nossos Servicos",
        "fitness": "O que Oferecemos", "crossfit": "Nossa Programacao",
        "pilates": "Nosso Metodo", "yoga": "Nossas Praticas",
        "beleza": "Nossos Servicos", "barbearia": "Nossos Servicos",
        "gastronomia": "Nosso Menu", "hamburgueria": "Nosso Cardapio",
        "pizzaria": "Nosso Cardapio", "cafeteria": "Nosso Menu",
        "confeitaria": "Nossos Doces", "loja construcao": "Nosso Estoque",
        "autopecas": "Nossas Pecas", "farmacia": "Nossos Produtos",
        "moda feminina": "Nossas Colecoes", "moda masculina": "Nossas Colecoes",
        "moda": "Nossas Colecoes", "e-commerce": "Nossos Produtos",
        "veterinaria": "Nossos Servicos Veterinarios", "petshop": "Nossos Servicos",
        "turismo": "Nossos Destinos e Servicos", "casamentos": "Nossos Servicos",
        "imoveis": "O que Oferecemos", "contabilidade": "Nossos Servicos",
        "tecnologia": "Nossas Solucoes", "saas": "Nossas Funcionalidades",
        "marketing": "Nossas Solucoes", "juridico": "Nossas Areas de Atuacao",
        "educacao": "O que Voce Vai Aprender", "curso online": "O que Voce Vai Aprender",
        "infoprodutos": "O que Esta Incluido", "lancamentos": "O que Esta Incluido",
        "energia solar": "Nossas Solucoes em Energia Solar",
        "construcao": "Nossos Servicos", "arquitetura": "Nossos Servicos",
        "igreja": "Nossa Programacao", "oficina": "Nossos Servicos",
    }
    title = NICHE_FEATURE_TITLE.get(niche, f"Por que escolher o {name}?")
    subtitle = f"Tudo que voce precisa em um so lugar para {audience}"
    cards = "".join(
        f'<div class="feature-card"><div class="feature-icon">{f["icon"]}</div><h3>{f["title"]}</h3><p>{f["desc"]}</p></div>'
        for f in features
    )
    return f"""
<section class="section section-alt" id="servicos">
  <h2>{title}</h2>
  <p class="subtitle">{subtitle}</p>
  <div class="features-grid">{cards}</div>
</section>"""



# Niche-specific about texts — (specialty, mission)
_ABOUT_TEXT = {
    # SAÚDE
    "odontologia": ("odontologia com tecnologia de ponta e atendimento humanizado",
                    "Cuidamos do seu sorriso com técnicas modernas, garantindo conforto, estetica e resultados duradouros."),
    "ortodontia": ("ortodontia com tratamentos personalizados e tecnologia digital",
                   "Alinhamos sorrisos com alinhadores e aparelhos de ultima geracao, respeitando o ritmo de cada paciente."),
    "harmonizacao facial": ("harmonizacao facial com resultados naturais e seguros",
                            "Valorizamos sua beleza natural com procedimentos esteticos minimamente invasivos realizados por profissionais certificados."),
    "dermatologia": ("dermatologia clinica e estetica com diagnostico preciso",
                     "Cuidamos da saude e beleza da sua pele com tratamentos baseados em evidencias e tecnologia de ponta."),
    "psicologia": ("psicologia com abordagem acolhedora, etica e humanizada",
                   "Acreditamos que saude mental e fundamental. Oferecemos espaco seguro para autoconhecimento e transformacao."),
    "psiquiatria": ("psiquiatria com atendimento sigiloso e tratamento individualizado",
                    "Abordagem integrativa e humanizada para transtornos do humor, ansiedade, TDAH e outros diagnosticos."),
    "fisioterapia": ("fisioterapia com reabilitacao completa e equipamentos modernos",
                     "Nossa equipe devolve qualidade de vida com protocolos individualizados para cada tipo de lesao e objetivo."),
    "nutricao": ("nutricao clinica e esportiva com plano 100% personalizado",
                 "Transformamos sua relacao com a comida para voce atingir seus objetivos com saude e sem restricoes desnecessarias."),
    "saude": ("medicina com atendimento humanizado e diagnostico preciso",
              "Nossa equipe de profissionais de saude cuida de voce com dedicacao, tecnologia e abordagem preventiva."),
    "cardiologia": ("cardiologia com diagnostico precoce e prevencao cardiovascular",
                    "Cuidamos do seu coracao com exames modernos, acompanhamento continuo e orientacao de estilo de vida saudavel."),
    "ginecologia": ("ginecologia e obstetricia com atendimento integral a saude feminina",
                    "Da adolescencia a menopausa, cuidamos de voce em todas as fases com respeito e expertise."),
    "pediatria": ("pediatria com atendimento especializado para criancas e adolescentes",
                  "Cuidamos da saude dos pequenos com carinho, tecnica e orientacao completa para as familias."),
    "veterinaria": ("medicina veterinaria com cuidado e amor pelos animais",
                    "Tratamos seus pets como membros da familia com diagnosticos precisos, cirurgias seguras e cuidados humanizados."),
    "laboratorio": ("laboratorio de analises clinicas com resultados rapidos e precisos",
                    "Exames realizados com equipamentos de ultima geracao, laudo digital e coleta domiciliar disponivel."),
    "acupuntura": ("acupuntura e medicina tradicional chinesa com abordagem integrativa",
                   "Equilibramos corpo e mente atraves de tecnicas milenares para alivio de dor e bem-estar geral."),
    "fertilidade": ("medicina reprodutiva com tecnologia de reproducao assistida de ponta",
                    "Realizamos o sonho de constituir familia com tratamentos personalizados e suporte emocional em cada etapa."),
    # ESTÉTICA / BELEZA
    "beleza": ("beleza e bem-estar com profissionais especializados e produtos premium",
               "Cuidamos da sua beleza com as melhores tecnicas do mercado, produtos de alta qualidade e atendimento personalizado."),
    "barbearia": ("barbearia moderna com os melhores profissionais do estilo masculino",
                  "Combinamos tradicao e modernidade para entregar o corte e barba perfeitos. Ambiente masculino exclusivo."),
    "lash design": ("extensao de cilios e lash design com tecnica profissional",
                    "Cada par de cilios e aplicado com precisao milimetrica para realcar seu olhar com naturalidade e durabilidade."),
    "nail design": ("nail design com unhas em gel, acrilica e nail art personalizadas",
                    "Arte e cuidado para suas maos e pes com as melhores marcas e tecnicas de nail design do mercado."),
    "sobrancelhas": ("design de sobrancelhas e micropigmentacao facial profissional",
                     "Emolduramos seu rosto realcando sua beleza natural com tecnicas de design e pigmentacao precisas."),
    "maquiagem": ("maquiagem profissional para noivas, festas e eventos especiais",
                  "Valorizamos seus tracos com maquiagem artistica que dura o dia todo, do pre-making ao retoque final."),
    "estetica corporal": ("estetica corporal com tratamentos corporais avancados",
                          "Tratamentos de reducao de medidas, drenagem linfatica e modelagem corporal com tecnologias modernas."),
    "spa": ("spa e bem-estar com experiencias relaxantes e rejuvenescedoras",
            "Um oasis de tranquilidade onde cada tratamento e pensado para restaurar seu equilibrio fisico e mental."),
    "skincare": ("skincare com formulas dermato testadas e ingredientes ativos",
                 "Desenvolvemos rotinas de cuidado com a pele personalizadas para sua pele funcionar no melhor estado possivel."),
    "depilacao": ("depilacao a laser e tratamentos definitivos com tecnologia avancada",
                  "Livre-se dos pelos indesejados com seguranca, eficacia e o minimo de desconforto possivel."),
    # FITNESS
    "fitness": ("academia com metodologia comprovada e equipamentos modernos",
                "Transformamos vidas atraves do exercicio fisico com instrutores certificados e planos de treino individualizados."),
    "crossfit": ("CrossFit com coaches certificados e comunidade motivadora",
                 "Superamos limites juntos com treinos funcionais de alta intensidade que transformam corpo, mente e habitos."),
    "pilates": ("pilates com metodo original e instrutores especializados",
                "O metodo Pilates transforma sua postura, alivia dores cronicas e conecta voce com seu corpo de forma unica."),
    "yoga": ("yoga e meditacao para equilibrio corpo-mente",
             "Praticas milenares adaptadas ao cotidiano moderno para reduzir estresse, melhorar flexibilidade e qualidade de vida."),
    "personal trainer": ("personal training 100% personalizado para seus objetivos",
                         "Cada treino e criado especificamente para voce, com acompanhamento presencial ou online e resultados reais."),
    "jiu-jitsu": ("jiu-jitsu brasileiro com professores faixa preta experientes",
                  "Arte marcial que desenvolve tecnica, disciplina e autoconfianca para criancas, adultos e atletas."),
    "boxe": ("boxe e muay thai para condicao fisica e defesa pessoal",
             "Treinamento de alta performance que combina tecnica de luta, condicionamento fisico e autodefesa pratica."),
    # IMOBILIÁRIO
    "imoveis": ("mercado imobiliario com carteira exclusiva e atendimento personalizado",
                "Ajudamos voce a encontrar o imovel ideal com transparencia total, suporte juridico e as melhores condicoes."),
    "imoveis alto padrao": ("imoveis de luxo com consultoria exclusiva e total discrição",
                            "Curadoria de residencias premium com atendimento VIP e acesso a lancamentos antes do mercado."),
    # FINANCEIRO
    "contabilidade": ("contabilidade estrategica para empresas que querem crescer",
                      "Alem dos numeros, entregamos inteligencia fiscal e financeira para sua empresa pagar menos impostos legalmente."),
    "financas": ("consultoria financeira pessoal e empresarial com resultados comprovados",
                 "Ajudamos pessoas e empresas a organizar, investir e crescer com planejamento financeiro personalizado."),
    "investimentos": ("consultoria de investimentos com gestao profissional de carteira",
                      "Protegemos e multiplicamos seu patrimonio com estrategia diversificada e monitoramento constante."),
    "seguros": ("corretora de seguros com as melhores coberturas e custo-beneficio",
                "Protegemos o que voce mais valoriza com seguros personalizados para cada etapa da sua vida."),
    "holding": ("holding patrimonial para protecao e planejamento sucessorio",
                "Estruturamos seu patrimonio de forma inteligente para protege-lo, reduzir impostos e garantir o futuro da familia."),
    "bpo financeiro": ("BPO financeiro para empresas que querem foco no seu negocio",
                       "Assumimos toda a gestao financeira da sua empresa com equipe especializada e tecnologia moderna."),
    # TECNOLOGIA
    "tecnologia": ("tecnologia e inovacao que transformam negocios e processos",
                   "Desenvolvemos solucoes digitais personalizadas que aumentam eficiencia, reduzem custos e geram crescimento."),
    "saas": ("plataforma SaaS escalavel para empresas em crescimento",
             "Nossa plataforma automatiza processos, centraliza dados e entrega insights para voce tomar decisoes mais rapidas."),
    "ia": ("inteligencia artificial e machine learning para vantagem competitiva",
           "Desenvolvemos solucoes de IA personalizadas que automatizam tarefas, analisam dados e geram valor real para seu negocio."),
    "cybersecurity": ("seguranca digital e protecao de dados para empresas",
                      "Protegemos sua infraestrutura digital com pentest, monitoramento continuo e conformidade com LGPD."),
    "desenvolvimento web": ("desenvolvimento web com tecnologias modernas e performance",
                            "Criamos sites e sistemas rapidos, seguros e responsivos que convertem visitantes em clientes."),
    "app mobile": ("desenvolvimento de aplicativos iOS e Android de alta qualidade",
                   "Apps intuitivos, performaticos e escalaves desenvolvidos com metodologia agil e foco na experiencia do usuario."),
    "software house": ("fabrica de software para solucoes customizadas e escalaves",
                       "Transformamos suas necessidades em solucoes tecnologicas com qualidade, prazo e suporte continuo."),
    # EDUCAÇÃO
    "educacao": ("educacao com metodologia focada em resultados praticos e mercado",
                 "Preparamos nossos alunos para os desafios reais com conteudo atual, professores experientes e certificacao."),
    "curso online": ("cursos online que transformam carreiras e vidas",
                     "Aprenda no seu ritmo com metodologia comprovada, comunidade ativa e certificado reconhecido pelo mercado."),
    "idiomas": ("escola de idiomas com metodo comunicativo e resultados rapidos",
                "Desenvolvemos fluencia real atraves de metodologia comunicativa, professores qualificados e pratica constante."),
    "mentoria": ("mentoria profissional intensiva com especialistas do mercado",
                 "Aceleramos seu desenvolvimento com acompanhamento proximo, estrategia personalizada e rede de contatos."),
    "enem vestibular": ("preparatorio ENEM e vestibular com metodologia de aprovacao",
                        "Nossos alunos passam nos melhores vestibulares com nossa metodologia focada em simulados e revisao estrategica."),
    # MARKETING
    "marketing": ("agencia de marketing digital com foco em resultados mensuraveis",
                  "Estrategia, conteudo e gestao de campanhas integradas para sua marca crescer de forma consistente e escalavel."),
    "trafego pago": ("gestao de trafego pago com ROI comprovado e gestao transparente",
                     "Gerenciamos seu investimento em anuncios com eficiencia maxima, relatorios claros e foco em leads qualificados."),
    "social media": ("gestao de redes sociais com estrategia e producao de conteudo",
                     "Construimos presenca digital solida com conteudo relevante, engajamento real e crescimento consistente."),
    "seo": ("consultoria SEO para posicionamento organico no Google",
            "Posicionamos sua empresa nos primeiros resultados do Google com tecnicas sustentaveis de SEO on e off-page."),
    "branding": ("branding e identidade visual para marcas que querem ser lembradas",
                 "Criamos identidades visuais estrategicas que comunicam os valores da sua marca e conectam com seu publico."),
    "lancamentos": ("especialista em lancamentos digitais de alto impacto",
                    "Metodologia de lancamento que gera faturamento expressivo em poucos dias, com estrutura e previsibilidade."),
    # JURÍDICO
    "juridico": ("advocacia com experiencia comprovada e atendimento personalizado",
                 "Defendemos seus direitos com tecnica, etica e total comprometimento, buscando sempre o melhor resultado."),
    "direito trabalhista": ("direito trabalhista com defesa efetiva dos seus direitos",
                            "Atuamos em acoes trabalhistas para garantir o que voce tem direito: verbas, adicionais e indenizacoes."),
    "direito previdenciario": ("direito previdenciario para conquista e revisao de beneficios INSS",
                               "Especialistas em aposentadorias, auxilio-doenca, BPC/LOAS e revisao de beneficios negados."),
    "direito familia": ("direito de familia com atendimento sigiloso e humano",
                        "Acompanhamento juridico em divorcios, guarda de filhos, pensao alimenticia e inventarios."),
    # AUTOMOTIVO
    "oficina": ("oficina mecanica com diagnostico preciso e garantia nos servicos",
                "Cuidamos do seu veiculo com transparencia total, tecnologia de diagnostico e maos de obra qualificada."),
    "estetica automotiva": ("estetica automotiva de nivel profissional para seu carro brilhar",
                            "Polimento, vitrificacao e higienizacao realizados com produtos premium e tecnica milimetrica."),
    "lava rapido": ("lava rapido com lavagem profissional rapida e de qualidade",
                    "Lavagem completa com agilidade e resultado impecavel, usando produtos especificos para cada superficie."),
    # CONSTRUÇÃO CIVIL
    "energia solar": ("energia solar com instalacao certificada e garantia de economia",
                      "Reduzimos sua conta de luz em ate 95% com paineis de alta eficiencia, monitoramento online e suporte tecnico."),
    "construcao": ("construcao civil com qualidade comprovada e prazo garantido",
                   "Cada obra e unica. Nossa equipe de engenheiros e mestres de obras entrega no prazo e dentro do orcamento."),
    "arquitetura": ("arquitetura e projetos que transformam espacos em experiencias",
                    "Criamos espacos funcionais e esteticamente belos que refletem a identidade de quem vai viver ou trabalhar neles."),
    "design interiores": ("design de interiores com conceito exclusivo e execucao perfeita",
                          "Transformamos ambientes com projeto de interiores que equilibra estetica, funcionalidade e seu estilo de vida."),
    "moveis planejados": ("moveis planejados sob medida para aproveitar cada centimetro",
                          "Projetamos e fabricamos moveis que se adaptam perfeitamente ao espaco, ao seu estilo e ao seu orcamento."),
    "reformas": ("empresa de reformas residenciais e comerciais de alto padrao",
                 "Executamos reformas completas ou por etapas com equipe propria, materiais de qualidade e acabamento impecavel."),
    "loja construcao": ("loja de materiais de construcao com o maior estoque da regiao",
                        "Atendemos construtores, engenheiros, arquitetos e autoempreendedores com os melhores materiais e preco justo."),
    "marcenaria": ("marcenaria sob medida para moveis e projetos especiais",
                   "Fabricamos pecas em madeira macica e MDF com precisao artesanal e acabamento de nivel profissional."),
    # ALIMENTAÇÃO
    "gastronomia": ("gastronomia com ingredientes frescos e receitas exclusivas",
                    "Cada prato e preparado com dedicacao e ingredientes selecionados para proporcionar uma experiencia gastronomica inesquecivel."),
    "hamburgueria": ("hamburgueria artesanal com blend exclusivo de carnes nobres",
                     "Hamburguer feito na hora, com ingredientes frescos e receitas proprias criadas com paixao e tecnica."),
    "pizzaria": ("pizzaria artesanal com massa fermentada e ingredientes premium",
                 "Nossa pizza e feita com massa de longa fermentacao, molho caseiro e ingredientes selecionados para sabor autentico."),
    "cafeteria": ("cafeteria especializada em cafe especial e experiencias aconchegantes",
                  "Cada xcara e cuidadosamente preparada por baristas treinados com graos de origem para o melhor sabor."),
    "confeitaria": ("confeitaria artesanal com bolos personalizados e doces finos",
                    "Criamos doces que sao obras de arte comestiveis, preparados com ingredientes premium e muito amor."),
    "delivery": ("delivery de comida saborosa e saudavel com entrega rapida",
                 "Refeicoes preparadas com carinho, entregues quentes e dentro do prazo para voce curtir em casa."),
    # E-COMMERCE / MODA
    "moda feminina": ("moda feminina com pecas exclusivas e qualidade premium",
                      "Curadoria de pecas que combinam tendencia, conforto e personalidade para mulheres que tem estilo."),
    "moda masculina": ("moda masculina com estilo contemporaneo e qualidade comprovada",
                       "Roupas e acessorios que comunicam personalidade, para o homem que se veste com atencao aos detalhes."),
    "moda infantil": ("moda infantil com conforto, seguranca e estilo",
                      "Roupinhas lindas, confortaveis e com tecidos seguros para os pequenos se expressarem com estilo."),
    "moda": ("loja de moda com curadoria especial para todos os estilos",
             "Pecas selecionadas com atencao a qualidade, caimento e tendencia para voce se sentir incrivel todos os dias."),
    "e-commerce": ("loja online com catalogo completo e entrega rapida",
                   "Compra segura, frete acessivel e produto de qualidade entregue no conforto da sua casa."),
    # PET
    "petshop": ("pet shop completo para o bem-estar do seu animal de estimacao",
                "Tudo para o seu pet em um so lugar: banho, tosa, racao, acessorios e muito amor pelos animais."),
    "hotel pet": ("hotel para pets com cuidados individualizados e webcam ao vivo",
                  "Seu pet fica em ambiente seguro, confortavel e cheio de carinho enquanto voce viaja sem preocupacao."),
    "adestramento": ("adestramento profissional com metodos positivos e humanizados",
                     "Desenvolvemos o comportamento do seu pet com tecnicas baseadas em reforcamento positivo e paciencia."),
    # TURISMO
    "turismo": ("agencia de viagens com roteiros exclusivos e atendimento dedicado",
                "Planejamos cada detalhe da sua viagem para voce vivenciar experiencias inesqueciveis sem estresse."),
    "turismo luxo": ("turismo de luxo com curadoria de experiencias exclusivas",
                     "Viagens premium com hoteis 5 estrelas, transfers privados e acesso a experiencias unicas pelo mundo."),
    "hospedagem": ("hospedagem aconchegante com ótimo custo-beneficio",
                   "Quartos confortaveis, cafe da manha caprichado e localizacao estrategica para sua estadia perfeita."),
    # EVENTOS
    "casamentos": ("cerimonial de casamentos com atencao a cada detalhe",
                   "Realizamos o casamento dos seus sonhos com planejamento impecavel, execucao precisa e muita emocao."),
    "fotografia": ("fotografia profissional que eterniza seus momentos mais especiais",
                   "Imagens que contam historias com sensibilidade artistica, luz perfeita e equipamentos profissionais."),
    "buffet": ("buffet gourmet para eventos memoraveis de todos os portes",
               "Cardapio variado e sofisticado preparado por chefs experientes para encantar todos os convidados."),
    # INFOPRODUTOS
    "infoprodutos": ("produtor de infoprodutos e cursos digitais que transformam vidas",
                     "Conteudo de qualidade, metodologia testada e suporte real para quem quer aprender e aplicar com resultado."),
    "curso online": ("cursos online que entregam conhecimento pratico e transformacao real",
                     "Aprenda com quem tem resultado, aplique imediatamente e conquiste seus objetivos com nossa metodologia."),
    # RELIGIOSO
    "igreja": ("comunidade crista acolhedora e transformadora",
               "Uma familia que te recebe de bracos abertos com fe, proposito, louvor e mensagem que transforma vidas."),
    # LOJAS ESPECIALIZADAS
    "farmacia": ("farmacia com atendimento farmaceutico especializado e humanizado",
                 "Nosso compromisso e com sua saude e bem-estar, com orientacao profissional para uso correto dos medicamentos."),
    "autopecas": ("loja de autopecas com estoque completo para todas as marcas",
                  "Pecas originais e paralelas de qualidade para mecanicos e proprietarios, com entrega rapida e preco justo."),
    "optica": ("otica com exame de vista gratuito e os melhores modelos",
               "Encontre os oculos perfeitos para seu rosto, seu estilo e sua visao com auxilio de optometristas qualificados."),
    "floricultura": ("floricultura com arranjos florais para todas as ocasioes",
                     "Flores frescas selecionadas diariamente para presentear, decorar e expressar sentimentos com arte floral."),
    "loja moveis": ("loja de moveis com design moderno e excelente custo-beneficio",
                    "Ambiente, conforto e estilo para todos os comodos da sua casa com qualidade que dura anos."),
    "papelaria": ("papelaria completa para escola, escritorio e presentear",
                  "Material escolar, de escritorio, impressao e artigos para presente em um so lugar com preco acessivel."),
    # RH / LOGÍSTICA
    "rh": ("consultoria de RH para contratar e reter os melhores talentos",
           "Recrutamento estrategico, avaliacao por competencias e desenvolvimento de pessoas para empresas que crescem."),
    "logistica": ("logistica e transporte de cargas com seguranca e pontualidade",
                  "Soluções completas de frete, armazenagem e distribuicao para sua empresa funcionar sem interrupcoes."),
    # CONSULTORIA
    "consultoria": ("consultoria empresarial estrategica para empresas em crescimento",
                    "Analise profunda do seu negocio com solucoes praticas para aumentar eficiencia, lucro e escalabilidade."),
}


def _sec_about(name, niche, diffs, p, hf, bf, extra_info="", location=""):
    diff_items = "".join(
        f"<li style='padding:6px 0;color:#4a5568'>✓ {d}</li>" for d in diffs
    ) if diffs else "<li style='padding:6px 0;color:#4a5568'>✓ Qualidade comprovada</li>"

    desc = _ABOUT_TEXT.get(niche)
    if desc:
        specialty, mission = desc
        p1 = f"O {name} é especialista em {specialty}."
        p2 = mission
    else:
        # Generic but better fallback based on niche sector
        NICHE_SECTOR_ABOUT = {
            "saas": ("plataforma digital escalavel", "Automatizamos processos e entregamos tecnologia de ponta para empresas que querem crescer mais rapido."),
            "marketing": ("marketing digital com foco em performance", "Estrategia, conteudo e campanhas integradas para sua marca crescer de forma consistente."),
            "lancamentos": ("lancamentos digitais de alto impacto", "Metodologia comprovada que gera faturamento expressivo com estrutura e previsibilidade."),
            "infoprodutos": ("infoprodutos e cursos digitais", "Conteudo de qualidade com metodologia testada para quem quer aprender e ter resultado real."),
            "turismo luxo": ("turismo de luxo e experiencias exclusivas", "Curadoria de viagens premium com hoteis 5 estrelas e acesso a experiencias unicas pelo mundo."),
            "casamentos": ("cerimonial e assessoria de casamentos", "Realizamos o casamento dos seus sonhos com planejamento impecavel e atencao a cada detalhe."),
            "fotografia": ("fotografia profissional de eventos e retratos", "Capturamos momentos com sensibilidade artistica e qualidade tecnica para eternizar memorias."),
            "petshop": ("pet shop completo com foco no bem-estar animal", "Tudo para seu pet em um so lugar com profissionais que realmente amam os animais."),
            "hotel pet": ("hotel para pets com cuidados individualizados", "Seu pet fica em ambiente seguro e confortavel com acompanhamento 24h e webcam ao vivo."),
            "hamburgueria": ("hamburgueria artesanal com blend exclusivo", "Hamburguer feito na hora com ingredientes frescos e receitas proprias criadas com paixao."),
            "pizzaria": ("pizzaria artesanal com massa de longa fermentacao", "Pizza autentica com massa artesanal, molho caseiro e ingredientes premium selecionados."),
            "cafeteria": ("cafeteria especializada em cafe especial", "Cada xcara preparada por baristas treinados com graos de origem para o melhor sabor."),
            "confeitaria": ("confeitaria artesanal com bolos personalizados", "Doces que sao obras de arte preparados com ingredientes premium e muito carinho."),
        }
        fb = NICHE_SECTOR_ABOUT.get(niche)
        if fb:
            specialty, mission = fb
            p1 = f"O {name} é especialista em {specialty}."
            p2 = mission
        else:
            p1 = f"O {name} é referencia em {niche} com anos de experiencia no mercado."
            p2 = "Nossa equipe dedicada garante o melhor atendimento e resultados que superam suas expectativas em cada projeto."

    # Enrich with real data from prompt if available
    loc_txt = f" em {location}" if location else ""
    p1 = p1.replace(f"O {name} é", f"O {name} é uma referencia consolidada{loc_txt} — " if location else f"O {name} é")

    # Add extra_info as a third paragraph if available and substantive
    extra_para = ""
    if extra_info and len(extra_info) > 20:
        extra_para = f"<p>{extra_info}</p>"

    return f"""
<section class="section" id="sobre">
  <div class="about-inner">
    <div class="about-text">
      <h2>Sobre o {name}</h2>
      <p>{p1}</p>
      <p>{p2}</p>
      {extra_para}
      <ul style="list-style:none;margin-top:16px">{diff_items}</ul>
    </div>
    <div class="about-visual">🏆</div>
  </div>
</section>"""


def _sec_gallery(name, niche, p, hf):
    # Niche-specific gallery labels and emojis instead of generic "image"
    NICHE_GALLERY: dict[str, list[str]] = {
        "odontologia":       ["😁 Sorriso Transformado", "🦷 Implante", "✨ Clareamento", "💎 Facetas", "😁 Antes e Depois", "🏆 Resultado Final"],
        "harmonizacao facial": ["✨ Harmonizacao", "💆 Preenchimento", "👄 Labios", "✨ Botox", "💎 Resultado", "🌟 Antes e Depois"],
        "beleza":            ["💇 Coloracao", "✂️ Corte", "💅 Unhas", "💄 Maquiagem", "✨ Escova", "🌟 Transformacao"],
        "barbearia":         ["✂️ Corte Masculino", "🪒 Barba Feita", "💈 Estilo", "👑 VIP", "✂️ Acabamento", "🏆 Resultado"],
        "lash design":       ["👁️ Fio a Fio", "✨ Volume Russo", "💎 Mega Volume", "👁️ Lash Lifting", "✨ Natural", "🌟 Marcante"],
        "fitness":           ["💪 Musculacao", "🏋️ Funcional", "🔥 HIIT", "🎯 Aula Coletiva", "⚡ Resultado", "🏆 Transformacao"],
        "crossfit":          ["🔥 WOD", "💪 Levantamento", "⚡ Ginastica", "🏆 Competicao", "🎯 Treino", "🚀 Performance"],
        "pilates":           ["🧘 Solo", "🎯 Aparelhos", "💚 Gestantes", "✨ Clinico", "🌟 Postura", "❤️ Resultado"],
        "gastronomia":       ["🍽️ Prato Principal", "🥗 Entrada", "🍷 Harmonizacao", "👨‍🍳 Chef", "🌟 Sobremesa", "✨ Ambiente"],
        "hamburgueria":      ["🍔 Artesanal", "🔥 Smash Burger", "🍟 Batata Frita", "😋 Combo", "🏆 Especial", "❤️ Favorito"],
        "pizzaria":          ["🍕 Margherita", "🍕 Especial", "🍕 Forno a Lenha", "🍕 Borda Recheada", "🍕 Artesanal", "🌟 Chef"],
        "cafeteria":         ["☕ Espresso", "🧁 Croissant", "☕ Cappuccino", "🍰 Brunch", "☕ Cold Brew", "✨ Ambiente"],
        "confeitaria":       ["🎂 Bolo Personalizado", "🧁 Cupcake", "💎 Cake Design", "🎀 Doces Finos", "🎂 Casamento", "✨ Arte"],
        "imoveis":           ["🏠 Residencial", "🏢 Comercial", "🏡 Casa", "🏰 Cobertura", "🔑 Entrega", "✨ Interior"],
        "construcao":        ["🏗️ Fundacao", "🧱 Estrutura", "🔨 Acabamento", "🏠 Entrega", "✨ Interior", "🏆 Obra Concluida"],
        "arquitetura":       ["📐 Projeto", "🏠 Render 3D", "✨ Interiores", "🔑 Entrega", "🌟 Antes", "🏆 Depois"],
        "design interiores": ["🛋️ Sala", "🛏️ Quarto", "🍳 Cozinha", "🏠 Home Office", "✨ Detalhe", "🌟 Resultado"],
        "moveis planejados": ["🪑 Sala", "🛏️ Closet", "🍳 Cozinha", "💻 Home Office", "🚿 Banheiro", "✨ Detalhe"],
        "moda feminina":     ["👗 Nova Colecao", "👠 Calcados", "👜 Bolsas", "✨ Look Completo", "💃 Estilo", "🌟 Tendencia"],
        "moda masculina":    ["👔 Camisas", "👖 Calcas", "🧥 Blazer", "👟 Calcados", "✨ Look", "🌟 Estilo"],
        "moda":              ["✨ Lancamento", "💃 Look Feminino", "👔 Look Masculino", "👟 Calcados", "👜 Acessorios", "🌟 Colecao"],
        "veterinaria":       ["🐕 Consulta", "🐈 Gato", "💉 Vacinacao", "🏥 Cirurgia", "❤️ Cuidado", "🌟 Recuperado"],
        "petshop":           ["🐩 Tosa Artistica", "🛁 Banho", "🎀 Acessorios", "🐾 Hidratacao", "🌟 Resultado", "❤️ Feliz"],
        "fotografia":        ["📷 Retrato", "💍 Casamento", "🎓 Formatura", "👶 Gestante", "🏢 Corporativo", "🌟 Arte"],
        "casamentos":        ["💍 Cerimonia", "💐 Decoracao", "🎂 Bolo", "📷 Fotos", "🥂 Festa", "❤️ Casal"],
        "estetica automotiva": ["✨ Polimento", "🚗 Vitrificacao", "🧹 Higienizacao", "✨ Antes e Depois", "🏆 Resultado", "💎 Premium"],
        "loja construcao":   ["🧱 Cimento", "🔨 Ferragens", "🎨 Tintas", "🪟 Esquadrias", "🔩 Parafusos", "🏗️ Materiais"],
        "turismo":           ["✈️ Destino", "🏖️ Praia", "🏔️ Montanha", "🗺️ Roteiro", "🏨 Hotel", "🌟 Experiencia"],
        "energia solar":     ["☀️ Instalacao", "🔧 Painel Solar", "💡 Ligacao", "📊 Monitoramento", "🏠 Residencial", "🏢 Comercial"],
    }
    gallery_items = NICHE_GALLERY.get(niche, [f"✨ Trabalho {i+1}" for i in range(6)])
    # Cycle if fewer than 6
    while len(gallery_items) < 6:
        gallery_items += gallery_items
    gallery_items = gallery_items[:6]

    NICHE_GALLERY_TITLE = {
        "odontologia": "Sorrisos Transformados", "harmonizacao facial": "Resultados Reais",
        "beleza": "Nosso Portfolio", "barbearia": "Nossos Trabalhos",
        "lash design": "Galeria de Cilios", "fitness": "Transformacoes Reais",
        "crossfit": "Nossos Atletas", "pilates": "Nosso Studio",
        "gastronomia": "Nossos Pratos", "hamburgueria": "Nosso Cardapio",
        "pizzaria": "Nossas Pizzas", "cafeteria": "Nosso Espaco",
        "confeitaria": "Nossas Criacoes", "imoveis": "Imoveis em Destaque",
        "construcao": "Nossas Obras", "arquitetura": "Nossos Projetos",
        "design interiores": "Ambientes Criados", "moveis planejados": "Projetos Realizados",
        "moda feminina": "Nossa Colecao", "moda masculina": "Nossa Colecao",
        "moda": "Nossas Pecas", "veterinaria": "Nossos Pacientes",
        "petshop": "Nossos Clientes", "fotografia": "Nosso Portfolio",
        "casamentos": "Casamentos Realizados", "estetica automotiva": "Resultados Reais",
        "turismo": "Destinos e Experiencias", "energia solar": "Instalacoes Realizadas",
    }
    title = NICHE_GALLERY_TITLE.get(niche, "Nosso Portfolio")
    subtitle = f"Veja alguns dos nossos trabalhos em {niche}" if niche else "Conheca nossa galeria de trabalhos"

    bg2 = p.get("bg2", "#EDF2F7")
    items_html = "".join(
        f'<div class="gallery-item" style="font-size:1rem;font-weight:600;color:#4a5568;gap:8px;flex-direction:column">'
        f'<span style="font-size:2.5rem">{item.split()[0]}</span>'
        f'<span style="font-size:.8rem">{" ".join(item.split()[1:])}</span>'
        f'</div>'
        for item in gallery_items
    )
    return f"""
<section class="section section-alt" id="galeria">
  <h2>{title}</h2>
  <p class="subtitle">{subtitle}</p>
  <div class="gallery-grid">{items_html}</div>
</section>"""


def _sec_video(name, p, hf):
    bg2 = p.get("bg2", "#EDF2F7")
    return f"""
<section class="section" id="video">
  <h2>Conheca o {name}</h2>
  <p class="subtitle">Assista e descubra como podemos transformar seus resultados</p>
  <div style="max-width:720px;margin:0 auto;background:{bg2};border-radius:16px;height:400px;display:flex;align-items:center;justify-content:center;font-size:5rem;cursor:pointer">play</div>
</section>"""


def _sec_pricing(plans, p, hf, bf, cta1):
    pri = p["primary"]
    top = p.get("text_on_primary", "#FFFFFF")
    bg2 = p.get("bg2", "#EDF2F7")
    cards = ""
    for plan in plans:
        highlight = 'highlight' if plan.get("highlight") else ''
        feats = "".join(f"<li>{f}</li>" for f in plan["features"])
        cards += f'<div class="pricing-card {highlight}"><div class="pricing-name">{plan["name"]}</div><div class="pricing-price">{plan["price"]}</div><ul class="pricing-features">{feats}</ul><a href="#contato" style="display:block;margin-top:24px;padding:14px;background:{pri};color:{top};border-radius:8px;font-weight:700;text-align:center">{cta1}</a></div>'
    return f"""
<section class="section section-alt" id="planos">
  <h2>Planos e Precos</h2>
  <p class="subtitle">Escolha o plano ideal para voce</p>
  <div class="pricing-grid">{cards}</div>
</section>"""


def _sec_testimonials(testimonials, p, hf, bf, niche=""):
    cards = "".join(f'<div class="testimonial-card"><p class="testimonial-text">"{t["text"]}"</p><p class="testimonial-author">— {t["author"]}</p></div>' for t in testimonials)
    acc = p["accent"]
    top = p.get("text_on_primary", "#FFFFFF")

    # Niche-specific stats
    NICHE_STATS = {
        "odontologia": [("2.000+", "Sorrises transformados"), ("98%", "Satisfacao"), ("15 anos", "De experiencia")],
        "fitness": [("5.000+", "Alunos ativos"), ("30kg", "Media de resultado"), ("10 anos", "De metodologia")],
        "crossfit": [("800+", "Atletas treinados"), ("95%", "Renovacao mensal"), ("Coaches", "Certificados")],
        "imoveis": [("500+", "Imoveis vendidos"), ("R$200M+", "Em negocios"), ("98%", "Satisfacao")],
        "contabilidade": [("1.000+", "Empresas atendidas"), ("40%", "Reducao media de impostos"), ("15 anos", "De experiencia")],
        "marketing": [("200+", "Empresas atendidas"), ("3x", "Aumento medio de vendas"), ("500%", "ROI medio")],
        "tecnologia": [("150+", "Projetos entregues"), ("98%", "No prazo"), ("5 estrelas", "Avaliacao media")],
        "energia solar": [("2.000+", "Instalacoes"), ("95%", "Economia media"), ("25 anos", "Garantia dos paineis")],
        "juridico": [("3.000+", "Casos resolvidos"), ("95%", "Taxa de exito"), ("20 anos", "De atuacao")],
        "educacao": [("10.000+", "Alunos formados"), ("90%", "Empregabilidade"), ("4.9/5", "Avaliacao media")],
        "turismo": [("5.000+", "Viagens realizadas"), ("4.9/5", "Satisfacao"), ("20 anos", "No mercado")],
        "gastronomia": [("50.000+", "Pratos servidos"), ("4.9/5", "Avaliacao"), ("10 anos", "De gastronomia")],
        "saude": [("10.000+", "Pacientes atendidos"), ("98%", "Satisfacao"), ("15 anos", "De experiencia")],
        "infoprodutos": [("15.000+", "Alunos"), ("4.9/5", "Avaliacao media"), ("95%", "Concluem o curso")],
        "farmacia": [("10 anos", "Servindo a comunidade"), ("24h", "Atendimento todos os dias"), ("98%", "Clientes satisfeitos")],
        "loja construcao": [("5.000+", "Obras atendidas"), ("10.000+", "Itens em estoque"), ("10 anos", "No mercado")],
        "autopecas": [("50.000+", "Pecas em estoque"), ("98%", "Satisfacao"), ("10 anos", "De experiencia")],
        "optica": [("5.000+", "Clientes atendidos"), ("1h", "Oculos simples prontos"), ("98%", "Satisfacao")],
        "veterinaria": [("5.000+", "Pets atendidos"), ("24h", "Emergencia"), ("98%", "Satisfacao")],
        "petshop": [("3.000+", "Pets atendidos", ), ("98%", "Clientes voltam"), ("5 estrelas", "Avaliacao")],
    }
    stats_data = NICHE_STATS.get(niche, [("500+", "Clientes atendidos"), ("98%", "Satisfacao"), ("5 estrelas", "Avaliacao")])
    stats = "".join(
        f'<div class="stat"><div class="stat-number">{s[0]}</div><div class="stat-label">{s[1]}</div></div>'
        for s in stats_data
    )
    return f"""
<section class="section section-dark" id="depoimentos">
  <h2>O que nossos clientes dizem</h2>
  <div class="stats">{stats}</div>
  <div class="testimonials-grid">{cards}</div>
</section>"""


def _sec_partners(p, hf):
    top = p.get("text_on_primary", "#FFFFFF")
    logos = "".join(f'<div style="background:rgba(255,255,255,.1);border-radius:12px;padding:24px 32px;font-size:1.5rem;font-weight:700;color:rgba(255,255,255,.7)">Parceiro {i+1}</div>' for i in range(5))
    return f"""
<section class="section section-dark" id="parceiros">
  <h2>Nossos Parceiros</h2>
  <div style="display:flex;justify-content:center;gap:24px;flex-wrap:wrap;margin-top:32px">{logos}</div>
</section>"""


def _sec_faq(faq_items, p, hf, bf):
    items = "".join(f'<div class="faq-item"><p class="faq-q">? {item["q"]}</p><p class="faq-a">{item["a"]}</p></div>' for item in faq_items)
    return f"""
<section class="section section-alt" id="faq">
  <h2>Perguntas Frequentes</h2>
  <p class="subtitle">Tire suas duvidas sobre nossos servicos</p>
  <div class="faq-list">{items}</div>
</section>"""


def _sec_countdown(p, hf, bf, cta1):
    acc = p["accent"]
    toa = p.get("text_on_accent", "#1A202C")
    top = p.get("text_on_primary", "#FFFFFF")
    return f"""
<section class="section section-dark" id="oferta">
  <h2>Oferta por Tempo Limitado!</h2>
  <p class="subtitle">Aproveite antes que acabe</p>
  <div style="display:flex;justify-content:center;gap:32px;margin:32px 0;flex-wrap:wrap">
    <div style="text-align:center"><span style="font-family:'{hf}',sans-serif;font-size:3rem;font-weight:700;color:{acc};background:rgba(255,255,255,.1);padding:16px 24px;border-radius:12px;min-width:80px;display:block" id="days">07</span><div style="font-size:.8rem;opacity:.8;margin-top:8px;color:{top}">Dias</div></div>
    <div style="text-align:center"><span style="font-family:'{hf}',sans-serif;font-size:3rem;font-weight:700;color:{acc};background:rgba(255,255,255,.1);padding:16px 24px;border-radius:12px;min-width:80px;display:block" id="hours">23</span><div style="font-size:.8rem;opacity:.8;margin-top:8px;color:{top}">Horas</div></div>
    <div style="text-align:center"><span style="font-family:'{hf}',sans-serif;font-size:3rem;font-weight:700;color:{acc};background:rgba(255,255,255,.1);padding:16px 24px;border-radius:12px;min-width:80px;display:block" id="mins">59</span><div style="font-size:.8rem;opacity:.8;margin-top:8px;color:{top}">Minutos</div></div>
  </div>
  <div style="text-align:center;margin-top:32px"><a href="#contato" class="btn-primary">{cta1}</a></div>
</section>"""


def _sec_form(fields, p, hf, bf, cta1, name):
    pri = p["primary"]
    top = p.get("text_on_primary", "#FFFFFF")
    inputs = ""
    for field in fields:
        fid = field.lower().replace(" ", "_").replace("/", "_")
        if field == "Mensagem":
            inputs += f'<div class="form-group"><label for="{fid}">{field}</label><textarea id="{fid}" name="{fid}" rows="4" placeholder="Sua {field.lower()}..."></textarea></div>'
        elif field == "Data preferida":
            inputs += f'<div class="form-group"><label for="{fid}">{field}</label><input type="date" id="{fid}" name="{fid}"></div>'
        else:
            t = "email" if "mail" in field.lower() else "tel" if "telefone" in field.lower() or "whatsapp" in field.lower() else "text"
            inputs += f'<div class="form-group"><label for="{fid}">{field}</label><input type="{t}" id="{fid}" name="{fid}" placeholder="{field}..." required></div>'
    return f"""
<section class="section" id="contato">
  <h2>Entre em Contato</h2>
  <p class="subtitle">Preencha o formulario e nossa equipe retornara em breve</p>
  <div class="form-wrapper">
    <form onsubmit="alert('Mensagem enviada! Entraremos em contato em breve.');return false;">
      {inputs}
      <button type="submit" class="btn-submit">{cta1}</button>
    </form>
  </div>
</section>"""


def _sec_map(name, location, p, hf, bf, phone, email, address="", schedule=None):
    pri = p["primary"]
    bg = p.get("bg", "#F7FAFC")
    bg2 = p.get("bg2", "#EDF2F7")
    loc_text = address or location or "Nossa localizacao"
    phone_item = f'<div class="contact-item"><span>\U0001f4de {phone}</span></div>' if phone else ''
    email_item = f'<div class="contact-item"><span>\u2709\ufe0f {email}</span></div>' if email else ''
    schedule_html = ""
    if schedule:
        schedule_html = "".join(
            f'<div class="contact-item"><span>\U0001f550 {s["day"]}' +
            (f' \u2014 {s["event"]}' if s.get("event") else "") +
            f': {s["time"]}h</span></div>'
            for s in schedule
        )
    else:
        schedule_html = '<div class="contact-item"><span>\U0001f550 Consulte nossos horarios</span></div>'
    maps_url = f"https://www.google.com/maps/search/{loc_text.replace(' ', '+')}" if loc_text and loc_text != "Nossa localizacao" else "#"
    return f"""
<section class="section map-section" id="localizacao">
  <h2>Onde Estamos</h2>
  <p class="subtitle">Venha nos visitar</p>
  <div class="map-info">
    <a href="{maps_url}" target="_blank" rel="noopener" style="display:block;text-decoration:none">
      <div class="map-placeholder" title="Ver no Google Maps">\U0001f5fa\ufe0f<br><small style="font-size:.8rem;color:#718096;margin-top:8px;display:block">Ver no Google Maps</small></div>
    </a>
    <div class="contact-info">
      <h3>Informacoes de Contato</h3>
      <div class="contact-item"><span>\U0001f4cd {loc_text}</span></div>
      {phone_item}{email_item}
      {schedule_html}
    </div>
  </div>
</section>"""


def _sec_cta(name, niche, cta2, p, hf, bf):
    # Niche-specific CTA section copy
    NICHE_CTA_COPY: dict[str, tuple[str, str]] = {
        "farmacia":        ("Precisa de medicamentos ou produtos de saude?",
                            f"O {name} esta aberto para voce 24 horas por dia, 7 dias por semana. Venha nos visitar ou entre em contato agora."),
        "loja construcao": ("Sua obra precisa dos melhores materiais?",
                            f"O {name} tem tudo para sua construcao ou reforma. Entrega rapida e os melhores precos da regiao."),
        "autopecas":       ("Precisa de pecas para seu veiculo?",
                            f"O {name} tem o maior estoque de pecas da regiao. Fale com nossa equipe e resolva agora."),
        "optica":          ("Cuide da sua visao com quem entende do assunto.",
                            f"Agende seu exame de vista gratuito no {name} e encontre os oculos perfeitos para voce."),
        "gastronomia":     ("Pronto para uma experiencia gastronomica inesquecivel?",
                            f"Reserve sua mesa no {name} e vivencie sabores que ficam na memoria."),
        "hamburgueria":    ("Com fome? O melhor hamburguer esta esperando por voce.",
                            f"Faca seu pedido agora no {name} e receba em casa ou venha pessoalmente."),
        "petshop":         ("Seu pet merece o melhor cuidado.",
                            f"Agende o banho e tosa do seu pet no {name} e garanta o horario hoje mesmo."),
        "veterinaria":     ("A saude do seu pet nao pode esperar.",
                            f"O {name} esta pronto para atender seu animal de estimacao. Agende ou venha agora."),
        "moda feminina":   ("Sua nova peca favorita esta aqui.",
                            f"Confira a colecao completa do {name} e encontre o look perfeito para voce."),
        "moda masculina":  ("Vista-se com estilo e qualidade.",
                            f"Confira os lancamentos do {name} e monte o look ideal para qualquer ocasiao."),
        "moda":            ("Sua nova peca favorita esta esperando por voce.",
                            f"Confira a colecao do {name} e encontre pecas que combinam com o seu estilo."),
    }
    title, desc = NICHE_CTA_COPY.get(niche, (
        "Pronto para comecar?",
        f"Entre em contato agora e descubra como o {name} pode transformar seus resultados em {niche}.",
    ))
    return f"""
<section class="cta-section">
  <h2>{title}</h2>
  <p>{desc}</p>
  <a href="#contato" class="btn-cta">{cta2}</a>
</section>"""


def _sec_footer(name, niche, loc, p, hf, bf, phone, email, wa, ig, address="", schedule=None):
    phone_li = f'<li>\U0001f4de {phone}</li>' if phone else ''
    email_li = f'<li>\u2709\ufe0f {email}</li>' if email else ''
    wa_li = f'<li><a href="https://wa.me/55{wa}" style="color:#a0aec0">\U0001f4ac WhatsApp</a></li>' if wa else ''
    ig_li = f'<li><a href="https://instagram.com/{ig}" style="color:#a0aec0">\U0001f4f8 @{ig}</a></li>' if ig else ''
    addr_li = f'<li>\U0001f4cd {address}</li>' if address else f'<li>\U0001f4cd {loc.replace(" | ", "") if loc else "Brasil"}</li>'
    schedule_lis = ""
    if schedule:
        schedule_lis = "".join(
            f'<li>\U0001f550 {s["day"]}' +
            (f' \u2014 {s["event"]}' if s.get("event") else "") +
            f': {s["time"]}h</li>'
            for s in schedule
        )
    schedule_col_title = "Horarios" if schedule else "Links Rapidos"
    schedule_col_content = schedule_lis if schedule else '<li><a href="#inicio" style="color:#a0aec0">Inicio</a></li><li><a href="#servicos" style="color:#a0aec0">Servicos</a></li><li><a href="#contato" style="color:#a0aec0">Contato</a></li>'
    return f"""
<footer class="footer">
  <div class="footer-inner">
    <div>
      <div class="footer-brand">{name}</div>
      <p class="footer-desc">Especialistas em {niche}{loc}. Qualidade e confianca em cada atendimento.</p>
    </div>
    <div>
      <div class="footer-title">Contato</div>
      <ul class="footer-links">{phone_li}{email_li}{wa_li}{ig_li}{addr_li}</ul>
    </div>
    <div>
      <div class="footer-title">{schedule_col_title}</div>
      <ul class="footer-links">{schedule_col_content}</ul>
    </div>
  </div>
  <div class="footer-bottom">\u00a9 2024 {name} \u2014 Todos os direitos reservados{loc} | Gerado por WTech Landing Page</div>
</footer>"""


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _upd(db, job_id, status, step="", progress=0.0, error=None):
    try:
        from app.models.ai_generation import AIGeneration
        gen = db.query(AIGeneration).filter_by(job_id=uuid.UUID(job_id)).first()
        if gen:
            gen.status = status
            if status == "completed":
                gen.completed_at = datetime.now(tz=timezone.utc)
            if error:
                gen.error_details = {"error": error, "step": step}
            db.commit()
    except Exception as e:
        logger.warning("Could not update job: %s", e)


def _save(db, job_id, project_id, structured, html, css):
    try:
        from app.models.ai_generation import AIGeneration
        from app.models.project import Project
        gen = db.query(AIGeneration).filter_by(job_id=uuid.UUID(job_id)).first()
        if gen:
            gen.structured_json = structured
            gen.html_output = html
            gen.css_output = css
            gen.niche = structured.get("niche", "")  # save for learning queries
        proj = db.query(Project).filter_by(id=uuid.UUID(project_id)).first()
        if proj:
            proj.status = "ready"
        db.commit()
    except Exception as e:
        logger.error("Could not save results: %s", e)
