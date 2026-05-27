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
            ctx = parse_prompt(prompt)
            _upd(db, job_id, "processing", "consultando base de conhecimento", 0.25)
            past = _load_past(db, ctx["niche"])
            ctx["past_patterns"] = past
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
    # E-COMMERCE / MODA
    (r"moda\s+feminina|roupa\s+feminina|vestido|blusa\s+feminina", "moda feminina", "Loja de Moda Feminina"),
    (r"moda\s+masculina|roupa\s+masculina|camisa\s+masculina", "moda masculina", "Loja de Moda Masculina"),
    (r"moda\s+infantil|roupa\s+infantil|kids\s+fashion|bebe\s+roupa", "moda infantil", "Loja de Moda Infantil"),
    (r"dropshipping|loja\s+dropship|revenda\s+online", "dropshipping", "Loja Dropshipping"),
    (r"marketplace|shopify|loja\s+virtual|e.commerce|venda\s+online", "e-commerce", "Loja Online"),
    (r"roupa|vestuario|fashion|boutique|moda\b|calcado|tenis|sapato|bolsa", "moda", "Loja de Moda"),
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
    "construcao": ["qualidade comprovada", "prazo garantido"],
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
}


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT PARSER
# ══════════════════════════════════════════════════════════════════════════════

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

    found = []
    niche_services = SERVICE_DB.get(niche, [])
    for svc in niche_services:
        words = [w for w in svc.lower().split() if len(w) > 4]
        if words and any(w in pl for w in words):
            if svc not in found:
                found.append(svc)

    spec_m = re.search(r'especializ\w+\s+em\s+([^,\.]+?)(?:\s*,|\s+em\s+|\s+(?:e\s+em|para|com|quero|localiz|em\s+[A-Z])|\.|$)', pl)
    if spec_m:
        for part in re.split(r'\s+e\s+', spec_m.group(1).strip()):
            part_clean = part.strip().title()
            part_words = part.strip().lower().split()
            if len(part_clean) > 3 and not any(w in BLACKLIST for w in part_words) and part_clean not in found:
                found.append(part_clean)

    if not found:
        found = niche_services[:3] if niche_services else ["Servico Especializado", "Atendimento Personalizado", "Resultados Garantidos"]
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
    services = ctx["services"]
    diffs = ctx["differentials"]
    audience = ctx["audience"]
    tone = ctx["communication_tone"]
    intention = ctx["intention"]
    location = ctx["location"]
    past = ctx.get("past_patterns", [])

    loc = f" em {location}" if location else ""
    svc_str = ", ".join(services[:2]) if services else niche
    default_diffs = NICHE_DIFFS.get(niche, ["qualidade comprovada", "atendimento especializado"])
    diff_str = " e ".join(diffs[:2]) if diffs else " e ".join(default_diffs)

    used_headlines = [p.get("headline", "") for p in past]
    variants = _headline_variants(name, niche, intention, tone, loc, services)
    headline = next((h for h in variants if h not in used_headlines), variants[0])

    if tone == "formal":
        subtitle = (f"Oferecemos {svc_str} com {diff_str}. "
                    f"Atendemos {audience} que buscam resultados reais e duradouros{loc}.")
        ctas = _ctas_formal(intention, niche)
    else:
        subtitle = (f"A gente oferece {svc_str} com {diff_str}. "
                    f"Feito para {audience} que querem resultados de verdade{loc}!")
        ctas = _ctas_informal(intention, niche)

    features = _build_features(services, diffs, niche, audience)
    testimonials = _build_testimonials(ctx)
    pricing = _build_pricing(ctx) if ctx["wants_pricing"] else []
    faq = _build_faq(ctx) if ctx["wants_faq"] else []

    seo_title = f"{name} - {niche.capitalize()}{loc}"
    seo_title = (seo_title[:57] + "...") if len(seo_title) > 60 else seo_title
    seo_desc = f"Conheca {name}, especialista em {niche}{loc}. {svc_str} com {diff_str}. Entre em contato!"
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
    features = []
    for i, svc in enumerate(services[:4]):
        features.append({"icon": icons[i % len(icons)], "title": svc,
                          "desc": f"Servico especializado em {svc.lower()} para {audience}."})
    for i, diff in enumerate(diffs[:max(0, 3 - len(features))]):
        features.append({"icon": icons[(len(features)) % len(icons)], "title": diff,
                          "desc": f"{diff} para garantir sua total satisfacao."})
    if not features:
        features = [
            {"icon": icons[0], "title": "Qualidade", "desc": f"Excelencia em {niche}."},
            {"icon": icons[1], "title": "Experiencia", "desc": "Anos de mercado e resultados."},
            {"icon": icons[2], "title": "Confianca", "desc": "Clientes satisfeitos em todo o Brasil."},
        ]
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
    }
    if niche in NICHE_F:
        return NICHE_F[niche]
    return [
        {"q": f"Como funciona o servico do {name}?", "a": f"Nosso processo e simples e transparente. Entre em contato e nossa equipe especializada em {niche} ira guia-lo em cada etapa."},
        {"q": "Qual o prazo de atendimento?", "a": "Respondemos em ate 24 horas uteis. Para urgencias, temos atendimento prioritario disponivel."},
        {"q": "Voces atendem em todo o Brasil?", "a": "Sim! Atendemos clientes em todo o territorio nacional, com opcoes de atendimento presencial e online."},
        {"q": "Como posso agendar?", "a": f"Basta preencher o formulario nesta pagina ou entrar em contato diretamente. Nossa equipe do {name} retornara em breve."},
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

def build_sections(ctx: dict) -> list[dict]:
    sections = [{"type": "header"}]
    for i in range(ctx["banner_count"]):
        sections.append({"type": "hero", "index": i})
    if ctx["services"] or not ctx["sections_requested"]:
        sections.append({"type": "features"})
    if "about" in ctx["sections_requested"]:
        sections.append({"type": "about"})
    if ctx["wants_gallery"]:
        sections.append({"type": "gallery"})
    if ctx["wants_video"]:
        sections.append({"type": "video"})
    if ctx["wants_pricing"]:
        sections.append({"type": "pricing"})
    if ctx["testimonial_count"] > 0:
        sections.append({"type": "testimonials"})
    if "partners" in ctx["sections_requested"]:
        sections.append({"type": "partners"})
    if ctx["wants_faq"]:
        sections.append({"type": "faq"})
    if "countdown" in ctx["sections_requested"]:
        sections.append({"type": "countdown"})
    if ctx["wants_form"]:
        sections.append({"type": "form"})
    if ctx["wants_map"]:
        sections.append({"type": "map"})
    sections.append({"type": "cta"})
    sections.append({"type": "footer"})
    return sections


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

    css = _build_css(p, hf, bf)
    body_parts = []

    for sec in sections:
        t = sec["type"]
        if t == "header":   body_parts.append(_sec_header(name, cta1, p, hf, wa, logo_url=logo_url))
        elif t == "hero":   body_parts.append(_sec_hero(copy, p, hf, bf, cta1, cta2, sec.get("index", 0), ctx))
        elif t == "features": body_parts.append(_sec_features(copy["features"], p, hf, bf, name, ctx["audience"]))
        elif t == "about":  body_parts.append(_sec_about(name, ctx["niche"], ctx["differentials"], p, hf, bf))
        elif t == "gallery": body_parts.append(_sec_gallery(name, ctx["niche"], p, hf))
        elif t == "video":  body_parts.append(_sec_video(name, p, hf))
        elif t == "pricing": body_parts.append(_sec_pricing(copy["pricing"], p, hf, bf, cta1))
        elif t == "testimonials": body_parts.append(_sec_testimonials(copy["testimonials"], p, hf, bf))
        elif t == "partners": body_parts.append(_sec_partners(p, hf))
        elif t == "faq":    body_parts.append(_sec_faq(copy["faq"], p, hf, bf))
        elif t == "countdown": body_parts.append(_sec_countdown(p, hf, bf, cta1))
        elif t == "form":   body_parts.append(_sec_form(ctx["form_fields"], p, hf, bf, cta1, name))
        elif t == "map":    body_parts.append(_sec_map(name, ctx["location"], p, hf, bf, phone, email))
        elif t == "cta":    body_parts.append(_sec_cta(name, ctx["niche"], cta2, p, hf, bf))
        elif t == "footer": body_parts.append(_sec_footer(name, ctx["niche"], loc, p, hf, bf, phone, email, wa, ig))

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


def _build_css(p, hf, bf):
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
"""


# ── Section renderers ─────────────────────────────────────────────────────────

def _sec_header(name, cta1, p, hf, wa, logo_url=None):
    top = p.get("text_on_primary", "#FFFFFF")
    acc = p["accent"]
    toa = p.get("text_on_accent", "#1A202C")
    wa_btn = f'<a href="https://wa.me/55{wa}" class="nav-cta" style="background:#25D366;color:#fff">WhatsApp</a>' if wa else f'<a href="#contato" class="nav-cta">{cta1}</a>'
    if logo_url:
        logo_html = (f'<a href="#inicio" class="logo-link" aria-label="{name}">'
                     f'<img src="{logo_url}" alt="Logo {name}" class="header-logo-img" /></a>')
        logo_css = '.logo-link{display:flex;align-items:center;text-decoration:none}.header-logo-img{height:48px;width:auto;object-fit:contain;max-width:180px}'
    else:
        logo_html = f'<span class="logo">{name}</span>'
        logo_css = ''
    return f'<header class="header">{logo_html}{wa_btn}</header><style>{logo_css}</style>'


def _sec_hero(copy, p, hf, bf, cta1, cta2, idx, ctx):
    niche = ctx["niche"]
    loc = f" em {ctx['location']}" if ctx["location"] else ""
    top = p.get("text_on_primary", "#FFFFFF")
    headline = copy["headline_variations"][idx % len(copy["headline_variations"])]
    subtitle = copy["subtitle"] if idx == 0 else f"Descubra tudo que {copy['display_name']} pode fazer por voce{loc}."
    badge = f"Especialistas em {niche.capitalize()}{loc}"
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


def _sec_features(features, p, hf, bf, name, audience):
    cards = "".join(f'<div class="feature-card"><div class="feature-icon">{f["icon"]}</div><h3>{f["title"]}</h3><p>{f["desc"]}</p></div>' for f in features)
    return f"""
<section class="section section-alt" id="servicos">
  <h2>Por que escolher o {name}?</h2>
  <p class="subtitle">Solucoes completas para {audience}</p>
  <div class="features-grid">{cards}</div>
</section>"""


def _sec_about(name, niche, diffs, p, hf, bf):
    diff_items = "".join(f"<li style='padding:6px 0;color:#4a5568'>checkmark {d}</li>" for d in diffs) if diffs else "<li style='padding:6px 0;color:#4a5568'>checkmark Qualidade comprovada</li>"
    return f"""
<section class="section" id="sobre">
  <div class="about-inner">
    <div class="about-text">
      <h2>Sobre o {name}</h2>
      <p>Somos especialistas em {niche} com anos de experiencia no mercado. Nossa missao e oferecer solucoes de alta qualidade que transformam a vida dos nossos clientes.</p>
      <p>Com uma equipe dedicada e metodologia comprovada, garantimos resultados excepcionais em cada projeto.</p>
      <ul style="list-style:none;margin-top:16px">{diff_items}</ul>
    </div>
    <div class="about-visual">building</div>
  </div>
</section>"""


def _sec_gallery(name, niche, p, hf):
    items = "".join(f'<div class="gallery-item">image</div>' for i in range(6))
    return f"""
<section class="section section-alt" id="galeria">
  <h2>Nosso Portfolio</h2>
  <p class="subtitle">Conheca alguns dos nossos trabalhos em {niche}</p>
  <div class="gallery-grid">{items}</div>
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


def _sec_testimonials(testimonials, p, hf, bf):
    cards = "".join(f'<div class="testimonial-card"><p class="testimonial-text">"{t["text"]}"</p><p class="testimonial-author">- {t["author"]}</p></div>' for t in testimonials)
    acc = p["accent"]
    top = p.get("text_on_primary", "#FFFFFF")
    stats = f'<div class="stats"><div class="stat"><div class="stat-number">500+</div><div class="stat-label">Clientes atendidos</div></div><div class="stat"><div class="stat-number">98%</div><div class="stat-label">Satisfacao</div></div><div class="stat"><div class="stat-number">5 estrelas</div><div class="stat-label">Avaliacao</div></div></div>'
    return f"""
<section class="section section-dark" id="depoimentos">
  <h2>O que nossos clientes dizem</h2>
  {stats}
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


def _sec_map(name, location, p, hf, bf, phone, email):
    pri = p["primary"]
    bg = p.get("bg", "#F7FAFC")
    bg2 = p.get("bg2", "#EDF2F7")
    loc_text = location or "Nossa localizacao"
    phone_item = f'<div class="contact-item"><span>tel {phone}</span></div>' if phone else ''
    email_item = f'<div class="contact-item"><span>email {email}</span></div>' if email else ''
    return f"""
<section class="section map-section" id="localizacao">
  <h2>Onde Estamos</h2>
  <p class="subtitle">Venha nos visitar em {loc_text}</p>
  <div class="map-info">
    <div class="map-placeholder">mapa</div>
    <div class="contact-info">
      <h3>Informacoes de Contato</h3>
      <div class="contact-item"><span>local {loc_text}</span></div>
      {phone_item}{email_item}
      <div class="contact-item"><span>horario Seg-Sex: 8h-18h | Sab: 8h-12h</span></div>
    </div>
  </div>
</section>"""


def _sec_cta(name, niche, cta2, p, hf, bf):
    return f"""
<section class="cta-section">
  <h2>Pronto para comecar?</h2>
  <p>Entre em contato agora e descubra como o {name} pode transformar seus resultados em {niche}.</p>
  <a href="#contato" class="btn-cta">{cta2}</a>
</section>"""


def _sec_footer(name, niche, loc, p, hf, bf, phone, email, wa, ig):
    phone_li = f'<li>tel {phone}</li>' if phone else ''
    email_li = f'<li>email {email}</li>' if email else ''
    wa_li = f'<li><a href="https://wa.me/55{wa}" style="color:#a0aec0">WhatsApp</a></li>' if wa else ''
    ig_li = f'<li><a href="https://instagram.com/{ig}" style="color:#a0aec0">@{ig}</a></li>' if ig else ''
    return f"""
<footer class="footer">
  <div class="footer-inner">
    <div>
      <div class="footer-brand">{name}</div>
      <p class="footer-desc">Especialistas em {niche}{loc}. Qualidade e confianca em cada atendimento.</p>
    </div>
    <div>
      <div class="footer-title">Contato</div>
      <ul class="footer-links">{phone_li}{email_li}{wa_li}{ig_li}<li>local {loc.replace(' | ','') if loc else 'Brasil'}</li></ul>
    </div>
    <div>
      <div class="footer-title">Links Rapidos</div>
      <ul class="footer-links">
        <li><a href="#inicio" style="color:#a0aec0">Inicio</a></li>
        <li><a href="#servicos" style="color:#a0aec0">Servicos</a></li>
        <li><a href="#contato" style="color:#a0aec0">Contato</a></li>
      </ul>
    </div>
  </div>
  <div class="footer-bottom">copyright 2024 {name} - Todos os direitos reservados{loc} | Gerado por WTech Landing Page</div>
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
        proj = db.query(Project).filter_by(id=uuid.UUID(project_id)).first()
        if proj:
            proj.status = "ready"
        db.commit()
    except Exception as e:
        logger.error("Could not save results: %s", e)
