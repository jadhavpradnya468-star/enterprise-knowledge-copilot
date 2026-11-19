import logging
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.agents.deps import Deps
from app.api.errors import AppError
from app.db import Chunk, Document
from app.ingestion.chunking import chunk_text
from app.ingestion.extractors import ALLOWED_EXTENSIONS, ExtractionError, Page, extract_pages, validate_signature
from app.services.vector_store import VectorItem
from app.utils import new_id

logger = logging.getLogger("app.ingestion")
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def index_document(db: Session, deps: Deps, doc: Document, pages: list[Page]) -> None:
    s = deps.settings
    rows: list[Chunk] = []
    ordinal = 0
    for page in pages:
        for piece in chunk_text(page.text, s.chunk_size, s.chunk_overlap):
            rows.append(
                Chunk(id=f"{doc.id}_chunk_{ordinal:03d}", document_id=doc.id, owner_id=doc.owner_id,
                      ordinal=ordinal, page=page.page, text=piece)
            )
            ordinal += 1
    if not rows:
        raise ExtractionError("No extractable text found.")
    embeddings = deps.embedder.embed_documents([r.text for r in rows])
    try:
        db.add_all(rows)
        db.commit()  # release the write lock before the vector store opens its own session
        deps.store.add([VectorItem(r.id, doc.id, doc.owner_id, e) for r, e in zip(rows, embeddings)])
        doc.pages, doc.num_chunks, doc.status, doc.error = len(pages), len(rows), "indexed", None
        db.commit()
    except Exception:
        db.rollback()
        deps.store.delete_document(doc.id)
        db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
        db.commit()
        raise


def ingest_upload(db: Session, deps: Deps, owner_id: str, filename: str, data: bytes) -> Document:
    """Validate, store, extract, chunk, embed and index one uploaded file."""
    s = deps.settings
    name = Path(filename or "").name or "unnamed"
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AppError(415, "unsupported_file_type", "Only PDF, DOCX and TXT files are supported.")
    if not data:
        raise AppError(400, "empty_file", "The uploaded file is empty.")
    if len(data) > s.max_upload_bytes:
        raise AppError(413, "file_too_large", f"File exceeds the {s.max_upload_mb} MB limit.")
    if not validate_signature(ext, data):
        raise AppError(415, "invalid_file_content", "The file content does not match its extension.")

    doc = Document(id=new_id("doc"), owner_id=owner_id, filename=name, content_type=CONTENT_TYPES[ext],
                   size_bytes=len(data), status="processing")
    db.add(doc)
    db.commit()
    try:
        doc.storage_path = deps.storage.save(doc.id, ext, data)
        db.commit()
        index_document(db, deps, doc, extract_pages(ext, data))
    except ExtractionError as exc:
        _mark_failed(db, doc, str(exc))
        raise AppError(422, "ingestion_failed", str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("ingestion failed for %s: %s", doc.id, type(exc).__name__)
        _mark_failed(db, doc, "Indexing failed.")
        raise AppError(500, "ingestion_failed", "The document could not be indexed.") from exc
    return doc


def _mark_failed(db: Session, doc: Document, message: str) -> None:
    db.rollback()
    doc.status, doc.error = "failed", message[:500]
    db.commit()


def delete_document_full(db: Session, deps: Deps, doc: Document) -> None:
    deps.store.delete_document(doc.id)
    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    try:
        deps.storage.delete(doc.storage_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not delete stored file for %s: %s", doc.id, type(exc).__name__)
    db.delete(doc)
    db.commit()
