"""Agente determinístico para o modo simulado (sem OpenAI).

Reproduz a jornada do agente real — qualificação progressiva, busca no RAG,
agendamento e handoff — usando regras. Serve para a demo offline, testes e CI.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.agent.tools import (
    extrair_sinais,
    formatar_resultado_busca,
    tool_agendar_visita,
    tool_buscar_imoveis,
    tool_encaminhar_corretor,
)
from app.db.models import Intent
from app.observability.tracing import record_event
from app.services import scheduling
from app.services.leads import get_lead, missing_fields, update_profile

_PERGUNTAS = {
    "finalidade (compra, aluguel ou investimento)": "Você está pensando em comprar, alugar ou investir?",
    "região de interesse": "Em qual região ou bairro de São Paulo você quer procurar?",
    "faixa de preço": "Qual faixa de preço faz sentido pra você?",
    "quantidade de dormitórios": "Quantos dormitórios você precisa?",
    "prazo / urgência para decidir": "Você tem um prazo pra decidir ou está começando a pesquisar agora?",
    "um contato para retorno": "Me passa um telefone ou e-mail pra eu (ou o corretor) retomar com você?",
    "ticket de investimento disponível": "Qual valor você pretende investir?",
    "expectativa de retorno": "Você busca mais renda mensal ou valorização no longo prazo?",
    "perfil (renda mensal ou valorização)": "Prefere um imóvel focado em renda de aluguel ou em valorização?",
}

_AGENDA_RE = re.compile(r"\b(agendar|agenda|marcar|visita|visitar|reuni[ãa]o|conhecer)\b", re.I)
_HUMANO_RE = re.compile(r"\b(corretor|atendente|humano|pessoa|especialista|falar com algu[ée]m)\b", re.I)
_VER_RE = re.compile(r"\b(op[çc][õo]es|im[óo]veis|mostra|tem algo|o que voc[êe] tem|ver|alternativas|sugest)\b", re.I)
_ISO_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?)\b")


def _saudacao(nome: str | None) -> str:
    return f"Oi{(' ' + nome) if nome else ''}! Aqui é a Lária, da Aurora Imóveis. "


def _brl(v: float) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


def _eco_do_patch(patch: dict) -> str:
    if not patch:
        return ""
    partes: list[str] = []
    for k, v in patch.items():
        val = ", ".join(map(str, v)) if isinstance(v, list) else v
        if k == "finalidade":
            partes.append(f"então é {val}")
        elif k in ("zonas", "bairros"):
            partes.append(f"região: {val}")
        elif k == "orcamento_max":
            partes.append(f"orçamento até {_brl(v)}")
        elif k == "ticket_investimento":
            partes.append(f"ticket de {_brl(v)}")
        elif k == "quartos_min":
            partes.append(f"{val} dormitório(s)")
        elif k == "urgencia":
            partes.append(f"prioridade {val}")
        elif k == "contato":
            partes.append("contato salvo")
        elif k == "perfil_investidor":
            partes.append(f"perfil {val}")
    return ("Perfeito — " + "; ".join(partes) + ". ") if partes else "Anotado! "


def _filtros_do_perfil(lead) -> dict:
    p = lead.profile
    finalidade = "aluguel" if lead.intent == Intent.ALUGUEL else "venda"
    zona = (p.get("zonas") or [None])[0]
    bairro = (p.get("bairros") or [None])[0]
    return {
        "finalidade": finalidade if lead.intent in (Intent.COMPRA, Intent.ALUGUEL) else None,
        "zona": zona,
        "bairro": bairro,
        "preco_max": p.get("orcamento_max") or p.get("ticket_investimento"),
        "quartos_min": p.get("quartos_min"),
    }


def _buscar_e_apresentar(lead) -> str:
    consulta_partes = [lead.intent] + (lead.profile.get("bairros") or lead.profile.get("zonas") or [])
    texto, hits = tool_buscar_imoveis(
        lead.id, consulta=" ".join(map(str, consulta_partes)), k=3, **_filtros_do_perfil(lead)
    )
    if not hits:
        return "Ainda não achei nada 100% no seu perfil. Quer ampliar a região ou o valor?"
    return (
        "Separei algumas opções que combinam com o que você me disse:\n"
        + formatar_resultado_busca(hits)
        + "\n\nQuer agendar uma visita a alguma delas? Posso ver os horários."
    )


def responder(lead_id: int, texto: str, canal: str = "web") -> dict:
    patch = extrair_sinais(texto)
    if patch:
        update_profile(lead_id, patch)
    lead = get_lead(lead_id)
    record_event(type="node", name="simple_agent", lead_id=lead_id, data={"patch": patch})

    # 1) pedido explícito de humano
    if _HUMANO_RE.search(texto):
        resumo = tool_encaminhar_corretor(lead_id, motivo="cliente pediu atendimento humano")
        return {
            "reply": "Claro! Já passei seu atendimento para um corretor com um resumo do que "
            "conversamos. Ele te chama em breve. Posso ajudar em mais alguma coisa?",
            "intent": lead.intent,
            "handoff": resumo,
        }

    # 2) agendamento
    if _AGENDA_RE.search(texto):
        tipo = "reuniao" if lead.intent == Intent.INVESTIMENTO else "visita"
        iso = _ISO_RE.search(texto)
        cod = re.search(r"\bAUR-\d{4}\b", texto, re.I)
        if iso:
            msg = tool_agendar_visita(
                lead_id, iso.group(1), tipo, cod.group(0).upper() if cod else None, canal
            )
            return {"reply": msg + " Te envio a confirmação e o endereço. Até lá!", "intent": lead.intent}
        slots = scheduling.proximos_horarios(tipo, n=4)
        bonitos = ", ".join(datetime.fromisoformat(s).strftime("%d/%m %Hh") for s in slots)
        return {
            "reply": f"Consigo estes horários para {tipo}: {bonitos}. "
            f"Qual funciona? (pode responder no formato {slots[0]})",
            "intent": lead.intent,
            "slots": slots,
        }

    faltando = missing_fields(lead)

    # 3) cliente quer ver opções e já temos o mínimo
    if _VER_RE.search(texto) and len(faltando) <= 2:
        return {"reply": _buscar_e_apresentar(lead), "intent": lead.intent}

    # 4) qualificação progressiva
    if faltando:
        proximo = faltando[0]
        pergunta = _PERGUNTAS.get(proximo, f"Pode me falar sobre {proximo}?")
        prefixo = _saudacao(lead.nome) if lead.score == 0 and not lead.profile else ""
        eco = _eco_do_patch(patch)
        return {"reply": f"{prefixo}{eco}{pergunta}", "intent": lead.intent}

    # 5) qualificado -> apresenta imóveis
    return {"reply": _buscar_e_apresentar(lead), "intent": lead.intent}
