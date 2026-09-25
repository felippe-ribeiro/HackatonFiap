"""Engine e sessão do banco."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args)


def init_db() -> None:
    """Cria as tabelas (idempotente)."""
    if settings.sqlite_path:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    import app.db.models  # noqa: F401  (registra as tabelas no metadata)

    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    # expire_on_commit=False: os objetos continuam legíveis após o commit/close,
    # o que simplifica retornar entidades das funções de serviço.
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """Dependency do FastAPI."""
    with Session(engine, expire_on_commit=False) as session:
        yield session
