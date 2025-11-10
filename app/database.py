from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, create_engine

from .settings import settings

engine = create_engine(str(settings.database_url), echo=settings.debug)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
