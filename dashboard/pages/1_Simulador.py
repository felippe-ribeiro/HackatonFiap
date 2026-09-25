"""Simulador de conversa — reproduz o canal de mensageria na tela.

O motor é o mesmo do Telegram/WhatsApp (`app.agent.runner.responder`).
Migrar para um canal real = plugar o adapter, sem tocar nesta lógica.
"""

from __future__ import annotations

import uuid

import plotly.graph_objects as go
import streamlit as st

from _shared import brl, page

page("Simulador", "💬")

from app.agent.runner import responder
from app.services.leads import get_history, get_or_create_lead, missing_fields, score_breakdown

st.title("💬 Simulador de Atendimento")

# --- sessão / identidade do lead simulado ------------------------------------
if "sim_external_id" not in st.session_state:
    st.session_state.sim_external_id = f"sim-{uuid.uuid4().hex[:8]}"
if "sim_nome" not in st.session_state:
    st.session_state.sim_nome = ""

with st.sidebar:
    st.subheader("Sessão simulada")
    st.text_input("Seu nome (opcional)", key="sim_nome")
    canal = st.selectbox("Canal simulado", ["web", "whatsapp", "telegram"], index=0)
    st.code(st.session_state.sim_external_id, language=None)
    if st.button("🔄 Nova conversa", width='stretch'):
        st.session_state.sim_external_id = f"sim-{uuid.uuid4().hex[:8]}"
        st.rerun()
    st.divider()
    st.caption("Sugestões para testar:")
    st.markdown(
        "- *Estou procurando apartamento na zona sul*\n"
        "- *Quero investir em imóveis para renda*\n"
        "- *Tenho pressa, meu aluguel vence mês que vem*\n"
        "- *Pode me mostrar as opções?*\n"
        "- *Quero agendar uma visita*\n"
        "- *Prefiro falar com um corretor*"
    )

ext = st.session_state.sim_external_id

col_chat, col_info = st.columns([3, 2])

# --- coluna do chat ---------------------------------------------------------
with col_chat:
    lead_obj = None
    try:
        from sqlmodel import select

        from app.db.database import session_scope
        from app.db.models import Lead

        with session_scope() as s:
            lead_obj = s.exec(select(Lead).where(Lead.external_id == ext)).first()
    except Exception:
        lead_obj = None

    history = get_history(lead_obj.id, limit=100) if lead_obj else []
    if not history:
        with st.chat_message("assistant"):
            st.write(
                "Oi! Aqui é a **Lária**, da Aurora Imóveis 🏠 "
                "Você está pensando em **comprar**, **alugar** ou **investir**?"
            )
    for m in history:
        if m.role not in ("user", "assistant"):
            continue
        with st.chat_message("user" if m.role == "user" else "assistant"):
            if m.is_followup:
                st.caption("🔁 follow-up automático")
            st.write(m.content)

    prompt = st.chat_input("Escreva como se fosse o cliente...")
    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"), st.spinner("Lária está digitando..."):
            out = responder(
                ext, prompt, canal=canal, nome=st.session_state.sim_nome or None
            )
            st.write(out.reply)
        st.rerun()

# --- coluna de qualificação (o "cockpit" do corretor) ---------------------
with col_info:
    st.subheader("Qualificação em tempo real")
    lead = get_or_create_lead(ext, canal=canal)

    tcor = {"quente": "🔥 quente", "morno": "🌤️ morno", "frio": "❄️ frio"}[lead.temperatura]
    m1, m2 = st.columns(2)
    m1.metric("Score do lead", f"{lead.score}/100", tcor)
    m2.metric("Intenção", lead.intent)
    m2.metric("Status", lead.status)

    gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=lead.score,
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#111"},
                "steps": [
                    {"range": [0, 40], "color": "#dbeafe"},
                    {"range": [40, 70], "color": "#fef3c7"},
                    {"range": [70, 100], "color": "#fee2e2"},
                ],
            },
        )
    )
    gauge.update_layout(height=180, margin=dict(l=20, r=20, t=10, b=10))
    st.plotly_chart(gauge, width='stretch')

    st.markdown("**Critérios de score**")
    for c in score_breakdown(lead):
        icon = "✅" if c["atendido"] else "⬜"
        st.write(f"{icon} {c['criterio']} — {c['pontos']}/{c['max']}")

    faltando = missing_fields(lead)
    if faltando:
        st.markdown("**Ainda falta descobrir**")
        for f in faltando:
            st.write(f"• {f}")
    else:
        st.success("Lead qualificado — pronto para o corretor!")

    if lead.profile:
        with st.expander("Perfil coletado (dados estruturados)"):
            prof = dict(lead.profile)
            for k in ("orcamento_max", "ticket_investimento"):
                if prof.get(k):
                    prof[k] = brl(prof[k])
            st.json(prof)

    if st.button("📋 Gerar resumo para o corretor", width='stretch'):
        from app.services.summary import gerar_resumo

        st.session_state["sim_resumo"] = gerar_resumo(lead.id, kind="manual")
    if st.session_state.get("sim_resumo"):
        st.markdown(st.session_state["sim_resumo"])
