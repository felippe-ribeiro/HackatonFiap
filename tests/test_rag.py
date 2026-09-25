from app.rag import retriever


def test_busca_imoveis_retorna_resultados():
    hits = retriever.buscar_imoveis("apartamento na zona sul com varanda", finalidade="venda", k=5)
    assert hits
    assert all(h.metadata["finalidade"] == "venda" for h in hits)


def test_filtro_preco_maximo():
    hits = retriever.buscar_imoveis("apartamento", preco_max=600_000, k=8)
    assert hits
    assert all(h.metadata["preco"] <= 600_000 for h in hits)


def test_busca_conhecimento_traz_fonte():
    hits = retriever.buscar_conhecimento("quanto preciso de entrada para financiar?", k=3)
    assert hits
    assert any("financiamento" in h.metadata.get("source", "") for h in hits)
