"""Mini-suite de avaliação da solução (para o relatório técnico).

Mede, sem depender do modo real:
- Acurácia do extrator de sinais de qualificação (heurística determinística);
- Qualidade de recuperação do RAG de imóveis (o resultado respeita os filtros?);
- Cobertura da base de conhecimento por tema.

Uso:  python -m scripts.avaliar
"""

from __future__ import annotations

import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        pass

from app.agent.tools import extrair_sinais
from app.rag import retriever

# --------------------------------------------------------------------------- #
# 1) Extração de sinais — casos rotulados
# --------------------------------------------------------------------------- #
CASOS = [
    ("Estou procurando apartamento na zona sul", {"finalidade": "compra", "zonas": ["zona sul"]}),
    ("Quero alugar um apê de 2 quartos na Vila Madalena até 3500", {"finalidade": "aluguel", "bairros": ["vila madalena"], "quartos_min": 2, "orcamento_max": 3500.0}),
    ("Quero investir 600 mil para ter renda de aluguel", {"finalidade": "investimento", "ticket_investimento": 600000.0, "perfil_investidor": "renda mensal"}),
    ("Preciso comprar rápido, minha mudança é mês que vem", {"finalidade": "compra", "urgencia": "alta"}),
    ("Só estou começando a pesquisar, sem pressa", {"urgencia": "baixa"}),
    ("meu email é cliente@teste.com.br", {"contato": "cliente@teste.com.br"}),
    ("me liga no (11) 98888-7777", {"contato": "(11) 98888-7777"}),
    ("Busco cobertura em Moema, uns 1,2 milhão", {"bairros": ["moema"], "orcamento_max": 1200000.0}),
    ("apartamento 3 dormitórios com 2 vagas no Tatuapé", {"bairros": ["tatuapé"], "quartos_min": 3, "vagas_min": 2}),
    ("quero um imóvel para investir focado em valorização", {"finalidade": "investimento", "perfil_investidor": "valorização"}),
]


def aval_extracao() -> tuple[int, int]:
    acertos_campo = total_campo = 0
    print("\n== 1) Extração de sinais de qualificação ==")
    for texto, esperado in CASOS:
        got = extrair_sinais(texto)
        ok_itens = []
        for k, v in esperado.items():
            total_campo += 1
            hit = got.get(k) == v or (isinstance(v, list) and set(v).issubset(set(got.get(k, []))))
            acertos_campo += int(hit)
            ok_itens.append(f"{'✓' if hit else '✗'}{k}")
        print(f"  [{' '.join(ok_itens)}]  «{texto[:55]}»")
    print(f"  -> {acertos_campo}/{total_campo} campos corretos ({acertos_campo / total_campo:.0%})")
    return acertos_campo, total_campo


# --------------------------------------------------------------------------- #
# 2) RAG de imóveis — o resultado respeita os filtros pedidos?
# --------------------------------------------------------------------------- #
CONSULTAS = [
    dict(consulta="apartamento com varanda perto do metrô", finalidade="venda", zona="zona sul", preco_max=900000.0, quartos_min=2),
    dict(consulta="studio para alugar mobiliado", finalidade="aluguel", zona="zona oeste", preco_max=3500.0),
    dict(consulta="imóvel para investir com boa rentabilidade", finalidade="venda", preco_max=700000.0),
    dict(consulta="cobertura alto padrão", finalidade="venda", zona="zona sul"),
]


def aval_rag() -> tuple[int, int]:
    print("\n== 2) RAG de imóveis: aderência aos filtros ==")
    ok = tot = 0
    for q in CONSULTAS:
        hits = retriever.buscar_imoveis(**q, k=4)
        for h in hits:
            tot += 1
            m = h.metadata
            aderente = (
                (q.get("finalidade") is None or m["finalidade"] == q["finalidade"])
                and (q.get("preco_max") is None or m["preco"] <= q["preco_max"] * 1.15)
            )
            ok += int(aderente)
        zonas = {h.metadata["zona"] for h in hits}
        print(f"  «{q['consulta'][:42]}» -> {len(hits)} imóveis | zonas {zonas}")
    print(f"  -> {ok}/{tot} resultados aderentes aos filtros ({ok / max(tot, 1):.0%})")
    return ok, tot


# --------------------------------------------------------------------------- #
# 3) Base de conhecimento — recupera o tema certo?
# --------------------------------------------------------------------------- #
KB = [
    ("qual a entrada mínima para financiar um imóvel?", "financiamento"),
    ("quais garantias posso usar para alugar?", "locacao"),
    ("como calcular a rentabilidade de um imóvel para renda?", "investimento"),
    ("quais os passos para comprar um imóvel?", "processo_compra"),
    ("qual o horário de atendimento da imobiliária?", "aurora_imoveis"),
]


def aval_kb() -> tuple[int, int]:
    print("\n== 3) RAG da base de conhecimento: tema recuperado ==")
    ok = 0
    for pergunta, fonte_esperada in KB:
        hits = retriever.buscar_conhecimento(pergunta, k=3)
        fontes = [h.metadata.get("source") for h in hits]
        hit = fonte_esperada in fontes
        ok += int(hit)
        print(f"  [{'✓' if hit else '✗'}] «{pergunta[:48]}» -> {fontes}")
    print(f"  -> {ok}/{len(KB)} perguntas com a fonte correta no top-3 ({ok / len(KB):.0%})")
    return ok, len(KB)


def main() -> None:
    a1 = aval_extracao()
    a2 = aval_rag()
    a3 = aval_kb()
    print("\n== Resumo ==")
    print(f"  Extração de sinais:      {a1[0]}/{a1[1]} ({a1[0]/a1[1]:.0%})")
    print(f"  RAG imóveis (aderência): {a2[0]}/{a2[1]} ({a2[0]/max(a2[1],1):.0%})")
    print(f"  RAG conhecimento (top-3):{a3[0]}/{a3[1]} ({a3[0]/a3[1]:.0%})")


if __name__ == "__main__":
    main()
