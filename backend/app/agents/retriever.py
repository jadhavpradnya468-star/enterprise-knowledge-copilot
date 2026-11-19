from sqlalchemy import select

from app.agents.deps import Deps
from app.db import Chunk, Document, SessionLocal
from app.observability.tracing import traced


def retrieve_chunks(deps: Deps, user_id: str, document_ids: list[str] | None, query: str, k: int) -> list[dict]:
    """Embed the query, search (owner-filtered), drop low scores, and load chunk text."""
    hits = deps.store.search(deps.embedder.embed_query(query), k, user_id, document_ids)
    hits = [h for h in hits if h.score >= deps.settings.min_score]
    if not hits:
        return []
    with SessionLocal() as db:
        rows = db.execute(
            select(Chunk, Document.filename)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.id.in_([h.chunk_id for h in hits]), Chunk.owner_id == user_id)  # defence in depth
        ).all()
    by_id = {c.id: (c, fn) for c, fn in rows}
    return [
        {"chunk_id": h.chunk_id, "document_id": by_id[h.chunk_id][0].document_id, "filename": by_id[h.chunk_id][1],
         "page": by_id[h.chunk_id][0].page, "text": by_id[h.chunk_id][0].text, "score": round(h.score, 4)}
        for h in hits if h.chunk_id in by_id
    ]


def make_retriever(deps: Deps):
    @traced("retriever")
    def retriever(state):
        k = state["top_k"] * (2 ** state.get("attempt", 0))  # widen the search on retry
        chunks = retrieve_chunks(deps, state["user_id"], state.get("document_ids"), state["query"], k)
        return {
            "chunks": chunks,
            "_detail": {"k": k, "chunk_ids": [c["chunk_id"] for c in chunks], "scores": [c["score"] for c in chunks]},
        }

    return retriever
