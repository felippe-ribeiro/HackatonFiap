"""Camada de RAG: indexação e recuperação de imóveis + base de conhecimento.

Dois índices:
- `imoveis`      : um documento por imóvel (busca semântica + filtro estruturado).
- `conhecimento` : trechos de cartilhas sobre financiamento, locação, investimento,
                   processo de compra e a própria imobiliária.
"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import select

from app.config import ROOT_DIR, settings
from app.db.database import session_scope
from app.db.models import Property
from app.rag.vector_store import SearchHit, VectorStore

KB_DIR = ROOT_DIR / "data" / "base_conhecimento"

_imoveis_store: VectorStore | None = None
_kb_store: VectorStore | None = None


# --------------------------------------------------------------------------- #
# Texto indexável
# --------------------------------------------------------------------------- #
def property_to_document(p: Property) -> str:
    partes = [
        p.titulo,
        f"{p.tipo} para {p.finalidade}",
        f"{p.bairro}, {p.zona}, {p.cidade}",
        f"{p.quartos} dormitórios" if p.quartos else "studio / ambiente integrado",
        f"{p.suites} suítes" if p.suites else "",
        f"{p.vagas} vagas" if p.vagas else "sem vaga",
        f"{p.area_util:.0f} m²",
        f"preço {p.preco:,.0f} reais".replace(",", "."),
        f"condomínio {p.condominio:,.0f}".replace(",", "."),
        f"rentabilidade estimada de aluguel {p.rentabilidade_aluguel_pct}% ao ano"
        if p.rentabilidade_aluguel_pct
        else "",
        ", ".join(p.caracteristicas),
        p.descricao,
    ]
    return ". ".join(x for x in partes if x)


def property_to_metadata(p: Property) -> dict:
    return {
        "codigo": p.codigo,
        "titulo": p.titulo,
        "tipo": p.tipo,
        "finalidade": p.finalidade,
        "cidade": p.cidade,
        "bairro": p.bairro,
        "zona": p.zona,
        "preco": p.preco,
        "condominio": p.condominio,
        "quartos": p.quartos,
        "suites": p.suites,
        "vagas": p.vagas,
        "area_util": p.area_util,
        "rentabilidade_aluguel_pct": p.rentabilidade_aluguel_pct,
    }


# --------------------------------------------------------------------------- #
# Construção dos índices
# --------------------------------------------------------------------------- #
def _chunk_markdown(text: str, source: str, max_chars: int = 700) -> list[tuple[str, dict]]:
    blocks, current = [], ""
    for line in text.splitlines():
        if line.startswith("#") and current.strip():
            blocks.append(current.strip())
            current = ""
        current += line + "\n"
        if len(current) >= max_chars:
            blocks.append(current.strip())
            current = ""
    if current.strip():
        blocks.append(current.strip())
    return [(b, {"source": source, "chunk": i}) for i, b in enumerate(blocks)]


def build_indexes() -> dict[str, int]:
    """(Re)constrói os dois índices a partir do banco e dos .md. Retorna contagens."""
    global _imoveis_store, _kb_store

    with session_scope() as s:
        props = s.exec(select(Property)).all()

    imoveis = VectorStore("imoveis", settings.index_dir)
    imoveis.build(
        ids=[p.codigo for p in props],
        texts=[property_to_document(p) for p in props],
        metadatas=[property_to_metadata(p) for p in props],
    )
    _imoveis_store = imoveis

    kb_ids, kb_texts, kb_meta = [], [], []
    for md in sorted(KB_DIR.glob("*.md")):
        for text, meta in _chunk_markdown(md.read_text(encoding="utf-8"), md.stem):
            kb_ids.append(f"{md.stem}-{meta['chunk']}")
            kb_texts.append(text)
            kb_meta.append(meta)
    kb = VectorStore("conhecimento", settings.index_dir)
    kb.build(ids=kb_ids, texts=kb_texts, metadatas=kb_meta)
    _kb_store = kb

    return {"imoveis": imoveis.size, "conhecimento": kb.size}


# --------------------------------------------------------------------------- #
# Acesso lazy
# --------------------------------------------------------------------------- #
def _get_store(name: str) -> VectorStore:
    global _imoveis_store, _kb_store
    cache = _imoveis_store if name == "imoveis" else _kb_store
    if cache is not None:
        return cache
    store = VectorStore(name, settings.index_dir)
    if not store.load():
        raise RuntimeError(
            f"Índice '{name}' não encontrado em {settings.index_dir}. "
            "Rode `python -m scripts.seed_db` primeiro."
        )
    if name == "imoveis":
        _imoveis_store = store
    else:
        _kb_store = store
    return store


# --------------------------------------------------------------------------- #
# Busca
# --------------------------------------------------------------------------- #
def buscar_imoveis(
    consulta: str,
    finalidade: str | None = None,
    zona: str | None = None,
    bairro: str | None = None,
    preco_max: float | None = None,
    preco_min: float | None = None,
    quartos_min: int | None = None,
    k: int | None = None,
) -> list[SearchHit]:
    where: dict = {}
    if finalidade:
        where["finalidade"] = finalidade
    if zona:
        where["zona"] = zona.lower()
    if bairro:
        where["bairro"] = bairro
    if preco_max is not None:
        where.setdefault("preco", {})["$lte"] = preco_max
    if preco_min is not None:
        where.setdefault("preco", {})["$gte"] = preco_min
    if quartos_min is not None:
        where["quartos"] = {"$gte": quartos_min}

    store = _get_store("imoveis")
    topk = k or settings.rag_top_k
    hits = store.search(consulta or "imóvel", k=topk, where=where or None)

    # fallback progressivo: relaxa preço/quartos e, por fim, só finalidade
    if len(hits) < 2 and where:
        relaxado = {x: where[x] for x in ("finalidade", "zona") if x in where}
        hits = store.search(consulta or "imóvel", k=topk, where=relaxado or None)
    if len(hits) < 2 and finalidade:
        hits = store.search(consulta or "imóvel", k=topk, where={"finalidade": finalidade})

    # re-rank: penaliza imóveis muito acima do nº de dormitórios pedido
    if quartos_min is not None and hits:
        hits.sort(key=lambda h: (max(0, h.metadata.get("quartos", 0) - quartos_min), -h.score))
    return hits


def buscar_conhecimento(consulta: str, k: int = 3) -> list[SearchHit]:
    return _get_store("conhecimento").search(consulta, k=k)
