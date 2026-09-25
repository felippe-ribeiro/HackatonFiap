"""Orquestração multiagente com LangGraph.

    START
      │
      ▼
  classificar_intencao ──(investimento)──▶ agente_investimento ──▶ END
      │
      └────────(compra/aluguel/indefinido)──▶ agente_vendas ──▶ END

Cada "agente" é um ReAct agent (LangGraph prebuilt) com o mesmo conjunto de
ferramentas, mas system prompt especializado. O nó `classificar_intencao`
funciona como supervisor leve que roteia a conversa.
"""

from __future__ import annotations

import json
from typing import Annotated, TypedDict

from app.agent import prompts
from app.agent.tools import extrair_sinais, make_langchain_tools
from app.config import settings
from app.db.models import Intent
from app.llm import approx_tokens, chat_complete, estimate_cost, get_chat_model
from app.logging_conf import get_logger
from app.observability.tracing import record_event, trace
from app.services.leads import get_lead, update_profile

log = get_logger("agent.graph")


class SdrState(TypedDict, total=False):
    lead_id: int
    canal: str
    intent: str
    route: str
    history: list  # mensagens LangChain (sem system)
    reply: str


# --------------------------------------------------------------------------- #
def _classificar(state: SdrState) -> SdrState:
    lead = get_lead(state["lead_id"])
    intent = lead.intent if lead else Intent.INDEFINIDO
    last_user = ""
    for m in reversed(state.get("history", [])):
        if getattr(m, "type", None) == "human":
            last_user = m.content
            break

    if intent == Intent.INDEFINIDO and last_user:
        with trace("node", "classificar_intencao", lead_id=state["lead_id"]) as ctx:
            try:
                raw = chat_complete(prompts.CLASSIFICADOR, last_user, temperature=0.0)
                data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
                fin = data.get("finalidade", "indefinido")
                conf = float(data.get("confianca", 0))
            except Exception:
                fin, conf = extrair_sinais(last_user).get("finalidade", "indefinido"), 0.5
            ctx["data"] = {"finalidade": fin, "confianca": conf}
            ctx["tokens_in"] = approx_tokens(prompts.CLASSIFICADOR + last_user)
            ctx["tokens_out"] = approx_tokens(str(fin))
            ctx["cost_usd"] = estimate_cost(settings.llm_model, ctx["tokens_in"], ctx["tokens_out"])

        if fin in {"compra", "aluguel", "investimento"} and conf >= 0.55:
            update_profile(state["lead_id"], {"finalidade": fin})
            intent = fin

    route = "agente_investimento" if intent == Intent.INVESTIMENTO else "agente_vendas"
    return {"intent": intent, "route": route}


def _run_react(state: SdrState, system_prompt: str, node_name: str) -> SdrState:
    from langchain_core.messages import SystemMessage
    from langgraph.prebuilt import create_react_agent

    tools = make_langchain_tools(state["lead_id"], state.get("canal", "web"))
    model = get_chat_model()
    agent = create_react_agent(model, tools)

    messages = [SystemMessage(content=system_prompt), *state.get("history", [])]

    with trace("node", node_name, lead_id=state["lead_id"]) as ctx:
        try:
            result = agent.invoke({"messages": messages}, config={"recursion_limit": 12})
            reply = result["messages"][-1].content
            novos = result["messages"][len(messages):]
            n_steps = len(novos)
            tin, tout = _somar_uso(novos)
            tools_usadas = [
                tc["name"]
                for m in novos
                for tc in (getattr(m, "tool_calls", None) or [])
            ]
        except Exception:  # nunca deixa o usuário sem resposta
            log.exception("falha no agente ReAct")
            reply = (
                "Tive um problema técnico agora há pouco 😕 pode repetir sua última mensagem? "
                "Se preferir, posso te encaminhar para um corretor."
            )
            n_steps, tin, tout, tools_usadas = 0, 0, 0, []
        ctx["data"] = {"passos": n_steps, "ferramentas": tools_usadas}
        ctx["tokens_in"] = tin or approx_tokens(system_prompt)
        ctx["tokens_out"] = tout or approx_tokens(reply)
        ctx["cost_usd"] = estimate_cost(settings.llm_model, ctx["tokens_in"], ctx["tokens_out"])

    return {"reply": reply if isinstance(reply, str) else str(reply)}


def _somar_uso(messages: list) -> tuple[int, int]:
    """Soma tokens reais reportados pela OpenAI nas AIMessages do passo."""
    tin = tout = 0
    for m in messages:
        um = getattr(m, "usage_metadata", None)
        if um:
            tin += um.get("input_tokens", 0)
            tout += um.get("output_tokens", 0)
    return tin, tout


def _agente_vendas(state: SdrState) -> SdrState:
    return _run_react(state, prompts.PERSONA + prompts.VENDAS_EXTRA, "agente_vendas")


def _agente_investimento(state: SdrState) -> SdrState:
    return _run_react(state, prompts.PERSONA + prompts.INVESTIMENTO_EXTRA, "agente_investimento")


# --------------------------------------------------------------------------- #
_compiled = None


def get_graph():
    global _compiled
    if _compiled is not None:
        return _compiled

    from langgraph.graph import END, START, StateGraph

    g = StateGraph(SdrState)
    g.add_node("classificar_intencao", _classificar)
    g.add_node("agente_vendas", _agente_vendas)
    g.add_node("agente_investimento", _agente_investimento)

    g.add_edge(START, "classificar_intencao")
    g.add_conditional_edges(
        "classificar_intencao",
        lambda s: s["route"],
        {"agente_vendas": "agente_vendas", "agente_investimento": "agente_investimento"},
    )
    g.add_edge("agente_vendas", END)
    g.add_edge("agente_investimento", END)

    _compiled = g.compile()
    return _compiled


def responder_via_graph(lead_id: int, canal: str, history_lc: list) -> dict:
    graph = get_graph()
    final = graph.invoke({"lead_id": lead_id, "canal": canal, "history": history_lc})
    record_event(
        type="node",
        name="graph_done",
        lead_id=lead_id,
        data={"intent": final.get("intent"), "route": final.get("route")},
    )
    return {"reply": final.get("reply", ""), "intent": final.get("intent"), "route": final.get("route")}
