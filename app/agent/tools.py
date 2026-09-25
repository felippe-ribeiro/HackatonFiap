"""Ferramentas do agente + heurísticas de extração de sinais da conversa."""

from __future__ import annotations

import re
from typing import Any

from app.observability.tracing import trace
from app.rag import retriever
from app.rag.vector_store import SearchHit
from app.services import scheduling, summary
from app.services.leads import get_lead, set_status, update_profile

# --------------------------------------------------------------------------- #
# Heurísticas (usadas no modo simulado e como reforço do classificador)
# --------------------------------------------------------------------------- #
_ZONAS = ["zona sul", "zona oeste", "zona norte", "zona leste", "centro"]
_BAIRROS = [
    "moema", "vila mariana", "campo belo", "brooklin", "itaim bibi", "saúde", "saude",
    "jabaquara", "chácara klabin", "pinheiros", "perdizes", "vila madalena", "butantã",
    "butanta", "lapa", "alto de pinheiros", "santana", "tucuruvi", "tatuapé", "tatuape",
    "mooca", "anália franco", "analia franco", "higienópolis", "higienopolis", "bela vista",
    "consolação", "consolacao", "vila prudente",
]

_INTENT_KW = {
    "investimento": ["investir", "investimento", "renda", "rentabilidade", "retorno", "yield", "alugar depois", "valorização", "valorizacao"],
    "aluguel": ["alugar", "aluguel", "locação", "locacao", "locar", "para alugar"],
    "compra": ["comprar", "compra", "adquirir", "financiar", "morar", "financiamento"],
}
# Se a pessoa está claramente à procura de um imóvel mas sem verbo explícito,
# assume compra (cenário 1 do desafio: "Estou procurando apartamento na zona sul").
_BUSCA_MORADIA = ["procur", "gostaria de ver", "estou vendo", "estou olhando", "quero um", "quero uma", "à procura", "a procura", "busco um", "busco uma"]
_IMOVEL_NOUNS = ["apartamento", "apê", "ape", "apto", "casa", "imóvel", "imovel", "studio", "cobertura", "kitnet"]
_URGENCIA_KW = {
    "alta": [
        "urgente", "essa semana", "esse mês", "este mês", "mês que vem", "mes que vem",
        "semana que vem", "o quanto antes", "vencendo", "mudança marcada", "mudanca marcada",
        "preciso decidir", "com pressa", "tenho pressa", "estou com pressa", "pra ontem",
        "rápido", "rapido", "logo",
    ],
    "media": ["próximos meses", "proximos meses", "sem pressa mas", "até o fim do ano", "ate o fim do ano", "nos próximos", "nos proximos"],
    "baixa": ["só pesquisando", "so pesquisando", "sem pressa", "apenas olhando", "só olhando", "so olhando", "curiosidade", "começando a pesquisar", "comecando a pesquisar", "começo a pesquisar", "comeco a pesquisar", "pesquisar agora", "estou começando", "estou comecando", "sem data", "ano que vem", "longo prazo"],
}


def _parse_valor(texto: str) -> float | None:
    """Extrai um valor monetário: 'R$ 650 mil', '1,2 milhão', '3500', '800000', '2kk'."""
    t = texto.lower().replace(".", "").replace("r$", " ")
    # milhão primeiro (radical 'milh' cobre milhão/milhões); 'kk' = milhão coloquial
    m = re.search(r"(\d+(?:,\d+)?)\s*(milh\w*|kk)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000_000
    # 'mil' / 'k' (o \b após 'mil' impede casar com 'milhão')
    m = re.search(r"(\d+(?:,\d+)?)\s*(mil|k)\b", t)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000
    # número "cru" com 3 a 8 dígitos (ex.: 3500, 850000)
    m = re.search(r"\b(\d{3,8})\b", t)
    if m:
        return float(m.group(1))
    return None


def extrair_sinais(texto: str) -> dict[str, Any]:
    """Deriva um patch de perfil a partir de uma mensagem do cliente."""
    t = f" {texto.lower()} "
    patch: dict[str, Any] = {}

    # Contato primeiro — e removido antes de procurar valores (telefone não é orçamento)
    me = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", texto)
    mp = re.search(r"\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}", texto)
    texto_sem_contato = texto
    if me:
        patch["contato"] = me.group(0)
        texto_sem_contato = texto_sem_contato.replace(me.group(0), " ")
    elif mp:
        patch["contato"] = mp.group(0)
        texto_sem_contato = texto_sem_contato.replace(mp.group(0), " ")

    for intent, kws in _INTENT_KW.items():
        if any(k in t for k in kws):
            patch["finalidade"] = intent
            break
    if "finalidade" not in patch and any(b in t for b in _BUSCA_MORADIA) and any(
        n in t for n in _IMOVEL_NOUNS
    ):
        patch["finalidade"] = "compra"

    zonas = [z for z in _ZONAS if z in t]
    if zonas:
        patch["zonas"] = sorted(set(zonas))
    bairros = sorted({b for b in _BAIRROS if f" {b} " in t or f" {b}," in t})
    if bairros:
        patch["bairros"] = bairros

    mq = re.search(r"(\d+)\s*(quarto|dorm|dormit)", t)
    if mq:
        patch["quartos_min"] = int(mq.group(1))
    mv = re.search(r"(\d+)\s*(vaga|garagem)", t)
    if mv:
        patch["vagas_min"] = int(mv.group(1))

    valor = _parse_valor(texto_sem_contato)
    if valor:
        if patch.get("finalidade") == "investimento" or "invest" in t:
            patch["ticket_investimento"] = valor
        else:
            patch["orcamento_max"] = valor

    for nivel, kws in _URGENCIA_KW.items():
        if any(k in t for k in kws):
            patch["urgencia"] = nivel
            break

    if any(k in t for k in ("renda mensal", "renda todo mês", "renda de aluguel", "renda com aluguel", "para renda", "ter renda", "gerar renda")):
        patch["perfil_investidor"] = "renda mensal"
    elif "valorização" in t or "valorizacao" in t or "patrimônio" in t:
        patch["perfil_investidor"] = "valorização"

    return patch


# --------------------------------------------------------------------------- #
# Formatação
# --------------------------------------------------------------------------- #
def _brl(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


def formatar_imovel(hit: SearchHit) -> str:
    m = hit.metadata
    partes = [f"[{m['codigo']}] {m['titulo']} — {m['bairro']} ({m['zona']})"]
    dorm = f"{m['quartos']} dorm" if m.get("quartos") else "studio"
    if m.get("suites"):
        dorm += f" ({m['suites']} suíte)"
    partes.append(dorm)
    if m.get("vagas"):
        partes.append(f"{m['vagas']} vaga(s)")
    partes.append(f"{m['area_util']:.0f} m²")
    preco = _brl(m["preco"])
    if m.get("condominio"):
        preco += f" + cond. {_brl(m['condominio'])}"
    partes.append(preco)
    if m.get("rentabilidade_aluguel_pct"):
        partes.append(f"rentabilidade ~{m['rentabilidade_aluguel_pct']}% a.a.")
    return ", ".join(partes)


def formatar_resultado_busca(hits: list[SearchHit]) -> str:
    if not hits:
        return "Não encontrei imóveis com esse perfil na base agora."
    return "\n".join(f"- {formatar_imovel(h)}" for h in hits)


# --------------------------------------------------------------------------- #
# Núcleo das ferramentas (funções puras, reaproveitadas pelos dois modos)
# --------------------------------------------------------------------------- #
def tool_buscar_imoveis(lead_id: int, **kwargs: Any) -> tuple[str, list[SearchHit]]:
    with trace("tool", "buscar_imoveis", lead_id=lead_id) as ctx:
        hits = retriever.buscar_imoveis(**kwargs)
        ctx["data"] = {"args": {k: v for k, v in kwargs.items() if v is not None}, "n": len(hits)}
    return formatar_resultado_busca(hits), hits


def tool_consultar_conhecimento(lead_id: int, pergunta: str) -> str:
    with trace("tool", "consultar_conhecimento", lead_id=lead_id) as ctx:
        hits = retriever.buscar_conhecimento(pergunta, k=3)
        ctx["data"] = {"pergunta": pergunta, "fontes": [h.metadata.get("source") for h in hits]}
    if not hits:
        return "Não há material sobre isso na base de conhecimento."
    blocos = [f"(fonte: {h.metadata.get('source')})\n{h.text}" for h in hits]
    return "\n\n---\n\n".join(blocos)


def tool_registrar_dados(lead_id: int, **patch: Any) -> str:
    patch = {k: v for k, v in patch.items() if v not in (None, "", [], {})}
    if not patch:
        return "Nada para registrar."
    lead = update_profile(lead_id, patch)
    with trace("tool", "registrar_dados_do_lead", lead_id=lead_id) as ctx:
        ctx["data"] = {"patch": patch, "score": lead.score, "temperatura": lead.temperatura}
    return f"Registrado. Score do lead: {lead.score}/100 ({lead.temperatura})."


def tool_listar_horarios(lead_id: int, tipo: str = "visita") -> str:
    slots = scheduling.proximos_horarios(tipo, n=5)
    return "Horários disponíveis: " + ", ".join(slots)


def tool_agendar_visita(
    lead_id: int, quando_iso: str, tipo: str = "visita", imovel_codigo: str | None = None, canal: str = "web"
) -> str:
    try:
        appt = scheduling.agendar(
            lead_id, quando_iso, tipo=tipo, property_codigo=imovel_codigo, canal=canal
        )
    except ValueError as e:
        return f"Não consegui agendar: {e}"
    with trace("tool", "agendar_visita", lead_id=lead_id) as ctx:
        ctx["data"] = {"quando": appt.scheduled_for.isoformat(), "tipo": tipo, "imovel": imovel_codigo}
    quando_fmt = appt.scheduled_for.strftime("%d/%m às %Hh")
    return f"{tipo.capitalize()} agendada para {quando_fmt} com {appt.corretor}."


def tool_encaminhar_corretor(lead_id: int, motivo: str = "") -> str:
    set_status(lead_id, "qualificado")
    resumo = summary.gerar_resumo(lead_id, kind="handoff")
    with trace("tool", "encaminhar_para_corretor", lead_id=lead_id) as ctx:
        ctx["data"] = {"motivo": motivo}
    return "Lead encaminhado ao corretor com resumo:\n\n" + resumo


# --------------------------------------------------------------------------- #
# Ferramentas LangChain (modo real) — criadas por requisição para capturar contexto
# --------------------------------------------------------------------------- #
def make_langchain_tools(lead_id: int, canal: str):
    from langchain_core.tools import tool

    @tool
    def buscar_imoveis(
        consulta: str,
        finalidade: str | None = None,
        zona: str | None = None,
        bairro: str | None = None,
        preco_max: float | None = None,
        preco_min: float | None = None,
        quartos_min: int | None = None,
    ) -> str:
        """Busca imóveis na base da Aurora. `consulta` = descrição livre do que o cliente quer.
        `finalidade` deve ser 'venda' ou 'aluguel'. `zona` como 'zona sul'. Retorna lista formatada."""
        texto, _ = tool_buscar_imoveis(
            lead_id,
            consulta=consulta,
            finalidade=finalidade,
            zona=zona,
            bairro=bairro,
            preco_max=preco_max,
            preco_min=preco_min,
            quartos_min=quartos_min,
        )
        return texto

    @tool
    def consultar_conhecimento(pergunta: str) -> str:
        """Consulta a base de conhecimento (financiamento, locação, investimento, processo de
        compra, dados da Aurora). Use para responder dúvidas de processo. Retorna trechos com fonte."""
        return tool_consultar_conhecimento(lead_id, pergunta)

    @tool
    def registrar_dados_do_lead(
        finalidade: str | None = None,
        nome: str | None = None,
        contato: str | None = None,
        zonas: list[str] | None = None,
        bairros: list[str] | None = None,
        orcamento_max: float | None = None,
        orcamento_min: float | None = None,
        quartos_min: int | None = None,
        vagas_min: int | None = None,
        tipo: str | None = None,
        urgencia: str | None = None,
        prazo: str | None = None,
        financiamento: str | None = None,
        forma_pagamento: str | None = None,
        perfil_investidor: str | None = None,
        ticket_investimento: float | None = None,
        retorno_esperado: str | None = None,
        observacoes: str | None = None,
    ) -> str:
        """Registra/atualiza os dados de qualificação do lead. Chame sempre que descobrir algo novo.
        `urgencia` deve ser 'alta', 'media' ou 'baixa'."""
        return tool_registrar_dados(
            lead_id,
            finalidade=finalidade,
            nome=nome,
            contato=contato,
            zonas=zonas,
            bairros=bairros,
            orcamento_max=orcamento_max,
            orcamento_min=orcamento_min,
            quartos_min=quartos_min,
            vagas_min=vagas_min,
            tipo=tipo,
            urgencia=urgencia,
            prazo=prazo,
            financiamento=financiamento,
            forma_pagamento=forma_pagamento,
            perfil_investidor=perfil_investidor,
            ticket_investimento=ticket_investimento,
            retorno_esperado=retorno_esperado,
            observacoes=observacoes,
        )

    @tool
    def listar_horarios(tipo: str = "visita") -> str:
        """Lista horários disponíveis. `tipo` = 'visita' (imóvel) ou 'reuniao' (especialista)."""
        return tool_listar_horarios(lead_id, tipo)

    @tool
    def agendar_visita(quando_iso: str, tipo: str = "visita", imovel_codigo: str | None = None) -> str:
        """Agenda uma visita ou reunião. `quando_iso` no formato ISO 8601 (use um dos horários de
        `listar_horarios`). `imovel_codigo` como 'AUR-0007' quando for visita a um imóvel."""
        return tool_agendar_visita(lead_id, quando_iso, tipo, imovel_codigo, canal)

    @tool
    def encaminhar_para_corretor(motivo: str) -> str:
        """Encaminha o lead para um corretor humano e gera o resumo do atendimento.
        Use quando o cliente pedir, quando estiver pronto para negociar, ou em investimento de ticket alto."""
        return tool_encaminhar_corretor(lead_id, motivo)

    return [
        buscar_imoveis,
        consultar_conhecimento,
        registrar_dados_do_lead,
        listar_horarios,
        agendar_visita,
        encaminhar_para_corretor,
    ]
