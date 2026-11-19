"""Vector stores. They hold only vectors + ownership metadata and return (chunk_id, score).

Chunk text lives in the relational `chunks` table. Every search is filtered by owner at the
store level so authorization is enforced at retrieval time.
"""
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sqlalchemy import delete, select, text

from app.config import Settings
from app.db import LocalVector, SessionLocal, get_engine


@dataclass
class VectorItem:
    chunk_id: str
    document_id: str
    owner_id: str
    embedding: list[float]


@dataclass
class Hit:
    chunk_id: str
    score: float


class VectorStore(Protocol):
    def add(self, items: list[VectorItem]) -> None: ...
    def search(self, embedding: list[float], k: int, owner_id: str, document_ids: list[str] | None) -> list[Hit]: ...
    def delete_document(self, document_id: str) -> None: ...


class LocalVectorStore:
    """Cosine search in NumPy over vectors stored in a SQL table. Simple and dependency-free;
    loads all of one user's vectors per query, so use pgvector/Chroma for larger corpora."""

    def add(self, items):
        with SessionLocal() as db:
            db.add_all(
                LocalVector(chunk_id=i.chunk_id, document_id=i.document_id, owner_id=i.owner_id, embedding=i.embedding)
                for i in items
            )
            db.commit()

    def search(self, embedding, k, owner_id, document_ids):
        stmt = select(LocalVector).where(LocalVector.owner_id == owner_id)
        if document_ids:
            stmt = stmt.where(LocalVector.document_id.in_(document_ids))
        with SessionLocal() as db:
            rows = db.scalars(stmt).all()
        if not rows:
            return []
        scores = np.array([r.embedding for r in rows], dtype=float) @ np.array(embedding, dtype=float)
        top = np.argsort(-scores)[:k]
        return [Hit(rows[i].chunk_id, float(scores[i])) for i in top]

    def delete_document(self, document_id):
        with SessionLocal() as db:
            db.execute(delete(LocalVector).where(LocalVector.document_id == document_id))
            db.commit()


class ChromaVectorStore:
    def __init__(self, path: str):
        import chromadb

        self.col = chromadb.PersistentClient(path=path).get_or_create_collection(
            "chunks", metadata={"hnsw:space": "cosine"}
        )

    def add(self, items):
        self.col.add(
            ids=[i.chunk_id for i in items],
            embeddings=[i.embedding for i in items],
            metadatas=[{"owner_id": i.owner_id, "document_id": i.document_id} for i in items],
        )

    def search(self, embedding, k, owner_id, document_ids):
        where: dict = {"owner_id": owner_id}
        if document_ids:
            where = {"$and": [where, {"document_id": {"$in": list(document_ids)}}]}
        n = self.col.count()
        if n == 0:
            return []
        res = self.col.query(query_embeddings=[embedding], n_results=min(k, n), where=where)
        return [Hit(i, 1.0 - d) for i, d in zip(res["ids"][0], res["distances"][0])]

    def delete_document(self, document_id):
        self.col.delete(where={"document_id": document_id})


class PgVectorStore:
    """PostgreSQL + pgvector (cosine distance). Requires the `vector` extension."""

    def __init__(self, dim: int):
        self.engine = get_engine()
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS chunk_vectors (chunk_id text PRIMARY KEY, "
                    f"owner_id text NOT NULL, document_id text NOT NULL, embedding vector({int(dim)}) NOT NULL)"
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS chunk_vectors_owner_idx ON chunk_vectors (owner_id)"))

    @staticmethod
    def _lit(vec: list[float]) -> str:
        return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"

    def add(self, items):
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO chunk_vectors (chunk_id, owner_id, document_id, embedding) "
                    "VALUES (:c, :o, :d, CAST(:e AS vector))"
                ),
                [{"c": i.chunk_id, "o": i.owner_id, "d": i.document_id, "e": self._lit(i.embedding)} for i in items],
            )

    def search(self, embedding, k, owner_id, document_ids):
        sql = (
            "SELECT chunk_id, 1 - (embedding <=> CAST(:q AS vector)) AS score FROM chunk_vectors "
            "WHERE owner_id = :o"
        )
        params: dict = {"q": self._lit(embedding), "o": owner_id, "k": k}
        if document_ids:
            sql += " AND document_id = ANY(:docs)"
            params["docs"] = list(document_ids)
        sql += " ORDER BY embedding <=> CAST(:q AS vector) LIMIT :k"
        with self.engine.connect() as conn:
            return [Hit(r[0], float(r[1])) for r in conn.execute(text(sql), params)]

    def delete_document(self, document_id):
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM chunk_vectors WHERE document_id = :d"), {"d": document_id})


def build_vector_store(s: Settings) -> VectorStore:
    if s.vector_store == "chroma":
        return ChromaVectorStore(s.chroma_dir)
    if s.vector_store == "pgvector":
        return PgVectorStore(s.embedding_dim)
    return LocalVectorStore()
