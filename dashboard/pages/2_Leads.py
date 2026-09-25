"""Detalhe de leads: perfil, score explicável, transcrição e resumo."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from _shared import brl, leads_df, page

page("Leads", "📇")

from app.services.leads import get_lead, missing_fields, score_breakdown
from app.services.leads import get_history
from app.services.scheduling import agendamentos_do_lead
from app.services.summary import gerar_resumo, ultimo_resumo

st.title("📇 Leads")

df = leads_df()
if df.empty:
    st.info("Sem leads. Rode `python -m scripts.seed_db` ou use o Simulador.")
    st.stop()

f1, f2 = st.columns([1, 1])
status_sel = f1.multiselect("Status", sorted(df["status"].unique()))
temp_sel = f2.multiselect("Temperatura", ["quente", "morno", "frio"])
view = df.copy()
if status_sel:
    view = view[view["status"].isin(status_sel)]
if temp_sel:
    view = view[view["temperatura"].isin(temp_sel)]

st.dataframe(view, width='stretch', hide_index=True)

st.divider()
lead_id = st.selectbox(
    "Abrir lead",
    options=view["id"].tolist(),
    format_func=lambda i: f"#{i} · {df.loc[df['id'] == i, 'nome'].values[0]}",
)
lead = get_lead(int(lead_id))
if not lead:
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Score", f"{lead.score}/100", lead.temperatura)
c2.metric("Intenção / status", f"{lead.intent} · {lead.status}")
c3.metric("Follow-ups enviados", lead.followup_attempts)

left, right = st.columns([1, 1])

with left:
    st.subheader("Score explicável")
    bd = pd.DataFrame(score_breakdown(lead))
    st.dataframe(bd, width='stretch', hide_index=True)

    st.subheader("Perfil coletado")
    prof = dict(lead.profile)
    for k in ("orcamento_max", "ticket_investimento", "orcamento_min"):
        if prof.get(k):
            prof[k] = brl(prof[k])
    st.json({"contato": lead.contato, **prof})

    falt = missing_fields(lead)
    if falt:
        st.warning("Pendências: " + ", ".join(falt))

    ags = agendamentos_do_lead(lead.id)
    if ags:
        st.subheader("Agendamentos")
        for a in ags:
            st.write(f"📅 {a.tipo} — {a.scheduled_for:%d/%m %Hh} · {a.corretor} · {a.status}")

with right:
    st.subheader("Transcrição")
    with st.container(height=360):
        for m in get_history(lead.id, limit=200):
            if m.role not in ("user", "assistant"):
                continue
            quem = "🧑 Cliente" if m.role == "user" else "🤖 Lária"
            tag = " _(follow-up)_" if m.is_followup else ""
            st.markdown(f"**{quem}**{tag}: {m.content}")

    st.subheader("Resumo para o corretor")
    if st.button("Gerar / atualizar resumo"):
        st.session_state[f"resumo_{lead.id}"] = gerar_resumo(lead.id, kind="manual")
    cache = st.session_state.get(f"resumo_{lead.id}")
    if not cache:
        r = ultimo_resumo(lead.id)
        cache = r.content if r else None
    st.markdown(cache or "_Nenhum resumo gerado ainda._")
