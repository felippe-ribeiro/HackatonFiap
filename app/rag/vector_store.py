"""Vector store leve baseado em NumPy (cosine similarity).

Escolha de projeto: sem dependências nativas (Chroma/FAISS/pgvector), o índice é
100% transparente e portável (Windows/Linux/CI). Em produção, a mesma interface
`VectorStore` seria trocada por pgvector — ver ARQUITETURA.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.llm import embed_query, embed_texts


@dataclass
class SearchHit:
    id: str
    score: float
    text: str
    metadata: dict[str, Any]


class VectorStore:
    def __init__(self, name: str, index_dir: Path):
        self.name = name
        self.dir = Path(index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._meta: list[dict[str, Any]] = []
        self._matrix: np.ndarray | None = None

    # ------------------------------------------------------------------ #
    @property
    def _npz_path(self) -> Path:
        return self.dir / f"{self.name}.npz"

    @property
    def _json_path(self) -> Path:
        return self.dir / f"{self.name}.json"

    @property
    def size(self) -> int:
        return len(self._ids)

    # ------------------------------------------------------------------ #
    def build(self, ids: list[str], texts: list[str], metadatas: list[dict[str, Any]]) -> None:
        if not (len(ids) == len(texts) == len(metadatas)):
            raise ValueError("ids, texts e metadatas devem ter o mesmo tamanho")
        vectors = embed_texts(texts)
        self._ids = list(ids)
        self._texts = list(texts)
        self._meta = list(metadatas)
        self._matrix = _normalize(np.asarray(vectors, dtype=np.float32))
        self.save()

    def save(self) -> None:
        if self._matrix is None:
            return
        np.savez_compressed(self._npz_path, matrix=self._matrix)
        self._json_path.write_text(
            json.dumps({"ids": self._ids, "texts": self._texts, "meta": self._meta}, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self) -> bool:
        if not (self._npz_path.exists() and self._json_path.exists()):
            return False
        self._matrix = np.load(self._npz_path)["matrix"].astype(np.float32)
        data = json.loads(self._json_path.read_text(encoding="utf-8"))
        self._ids, self._texts, self._meta = data["ids"], data["texts"], data["meta"]
        return True

    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        if self._matrix is None or not self._ids:
            return []
        q = _normalize(np.asarray([embed_query(query)], dtype=np.float32))[0]
        if q.shape[0] != self._matrix.shape[1]:
            raise RuntimeError(
                f"Índice '{self.name}' foi construído com embeddings de dimensão "
                f"{self._matrix.shape[1]}, mas a consulta gerou {q.shape[0]}. "
                "O modo de IA (real x simulado) mudou desde a indexação — "
                "rode `python -m scripts.seed_db` novamente para reconstruir o índice."
            )
        sims = self._matrix @ q  # cosine (vetores já normalizados)

        order = np.argsort(-sims)
        hits: list[SearchHit] = []
        for idx in order:
            meta = self._meta[idx]
            if where and not _match(meta, where):
                continue
            hits.append(
                SearchHit(
                    id=self._ids[idx],
                    score=float(sims[idx]),
                    text=self._texts[idx],
                    metadata=meta,
                )
            )
            if len(hits) >= k:
                break
        return hits


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def _match(meta: dict[str, Any], where: dict[str, Any]) -> bool:
    """Filtro estruturado simples: igualdade, `$in`, `$gte`, `$lte`."""
    for key, cond in where.items():
        val = meta.get(key)
        if isinstance(cond, dict):
            if "$in" in cond and val not in cond["$in"]:
                return False
            if "$gte" in cond and (val is None or val < cond["$gte"]):
                return False
            if "$lte" in cond and (val is None or val > cond["$lte"]):
                return False
        else:
            if val != cond:
                return False
    return True
