"""Prepara o ambiente: cria o banco, carrega imóveis, constrói o índice RAG
e (opcional) popula leads de demonstração.

Uso:
    python -m scripts.seed_db            # tudo
    python -m scripts.seed_db --no-demo  # sem leads fictícios
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

from sqlmodel import select

from app.config import ROOT_DIR
from app.db.database import init_db, session_scope
from app.db.models import Property
from app.rag.retriever import build_indexes

IMOVEIS_JSON = ROOT_DIR / "data" / "imoveis.json"


def carregar_imoveis() -> int:
    if not IMOVEIS_JSON.exists():
        from scripts.gerar_imoveis import main as gerar

        gerar()
    dados = json.loads(IMOVEIS_JSON.read_text(encoding="utf-8"))
    novos = 0
    with session_scope() as s:
        existentes = {p.codigo for p in s.exec(select(Property)).all()}
        for item in dados:
            if item["codigo"] in existentes:
                continue
            s.add(Property(**item))
            novos += 1
    return novos


def popular_demo() -> None:
    """Leads fictícios em vários estágios — deixa o dashboard 'vivo' na primeira execução."""
    from datetime import datetime, timedelta, timezone

    from app.db.models import Appointment, Lead, LeadStatus, Message

    agora = datetime.now(timezone.utc)
    with session_scope() as s:
        if s.exec(select(Lead)).first():
            return  # já populado

        # Lead quente com visita agendada
        l1 = Lead(
            external_id="demo-ana", nome="Ana Souza", contato="ana.souza@email.com",
            canal="whatsapp", intent="compra", status=LeadStatus.AGENDADO, score=85,
            temperatura="quente",
            profile={"zonas": ["zona sul"], "bairros": ["moema"], "orcamento_max": 950000,
                     "quartos_min": 2, "urgencia": "alta", "financiamento": "pré-aprovado"},
            last_inbound_at=agora - timedelta(hours=2), last_outbound_at=agora - timedelta(hours=2),
        )
        # Lead morno em qualificação
        l2 = Lead(
            external_id="demo-bruno", nome="Bruno Lima", canal="web", intent="investimento",
            status=LeadStatus.EM_QUALIFICACAO, score=45, temperatura="morno",
            profile={"ticket_investimento": 500000, "perfil_investidor": "renda mensal"},
            last_inbound_at=agora - timedelta(days=2, hours=3),
            last_outbound_at=agora - timedelta(days=2, hours=3),
        )
        # Lead frio, parado -> alvo de follow-up
        l3 = Lead(
            external_id="demo-carla", nome="Carla Nunes", canal="telegram", intent="aluguel",
            status=LeadStatus.EM_QUALIFICACAO, score=25, temperatura="frio",
            profile={"zonas": ["zona oeste"]},
            last_inbound_at=agora - timedelta(days=3),
            last_outbound_at=agora - timedelta(days=3, minutes=5),
        )
        s.add_all([l1, l2, l3])
        s.flush()

        s.add_all([
            Message(lead_id=l1.id, role="user", content="Oi, procuro apê em Moema, uns 2 quartos, até 950 mil. Mudança marcada pro mês que vem!", created_at=agora - timedelta(hours=3)),
            Message(lead_id=l1.id, role="assistant", content="Perfeito, Ana! Já separo opções em Moema até R$ 950 mil com 2 dorm. Consegue visitar quinta às 15h?", created_at=agora - timedelta(hours=2, minutes=58)),
            Message(lead_id=l1.id, role="user", content="Consigo sim!", created_at=agora - timedelta(hours=2)),
            Message(lead_id=l2.id, role="user", content="Quero investir uns 500 mil pra ter renda de aluguel", created_at=agora - timedelta(days=2, hours=3)),
            Message(lead_id=l2.id, role="assistant", content="Ótimo, Bruno! Com esse ticket dá pra pensar em studios bem localizados. Você prefere renda mensal ou valorização?", created_at=agora - timedelta(days=2, hours=2, minutes=59)),
            Message(lead_id=l3.id, role="user", content="tem apê pra alugar na zona oeste?", created_at=agora - timedelta(days=3)),
            Message(lead_id=l3.id, role="assistant", content="Tenho sim! Qual faixa de aluguel e quantos dormitórios você precisa?", created_at=agora - timedelta(days=3, minutes=-5)),
        ])

        prop = s.exec(select(Property)).first()
        s.add(Appointment(
            lead_id=l1.id, property_id=prop.id if prop else None, tipo="visita",
            scheduled_for=agora + timedelta(days=2, hours=6), canal="whatsapp",
            corretor="Corretor de plantão", status="agendado",
        ))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-demo", action="store_true", help="não cria leads fictícios")
    ap.add_argument("--rebuild-index", action="store_true", help="força reconstrução do índice")
    args = ap.parse_args()

    print("→ criando tabelas...")
    init_db()

    print("→ carregando imóveis...")
    novos = carregar_imoveis()
    print(f"  {novos} imóvel(is) novo(s) inserido(s).")

    print("→ construindo índice RAG (embeddings)...")
    counts = build_indexes()
    print(f"  índice imóveis: {counts['imoveis']} docs | conhecimento: {counts['conhecimento']} chunks")

    if not args.no_demo:
        print("→ populando leads de demonstração...")
        popular_demo()

    print("\n✓ pronto. Suba a API com:  uvicorn app.main:app --reload")
    print("  e o painel com:            streamlit run dashboard/Home.py")


if __name__ == "__main__":
    main()
