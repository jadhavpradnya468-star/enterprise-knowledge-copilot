import os
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(32), default="processing")  # processing|indexed|failed
    error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    num_chunks: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)


class LocalVector(Base):
    """Embeddings for the default 'local' vector store (works on SQLite and Postgres)."""

    __tablename__ = "local_vectors"
    chunk_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list] = mapped_column(JSON)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@lru_cache
def get_engine():
    url = get_settings().database_url
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        path = url.split("sqlite:///", 1)[-1]
        if path and path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return create_engine(url, pool_pre_ping=True, **kwargs)


def SessionLocal() -> Session:  # noqa: N802 - factory used like a class
    return Session(get_engine(), expire_on_commit=False)
