from datetime import datetime

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.deps import Deps
from app.api.dependencies import get_current_user, get_db, get_deps
from app.api.errors import AppError
from app.db import Document, User
from app.ingestion.indexing import delete_document_full, ingest_upload

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    status: str
    size_bytes: int
    pages: int
    num_chunks: int
    error: str | None = None
    created_at: datetime


def _owned(db: Session, user: User, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.owner_id != user.id:  # same response for missing and not-yours
        raise AppError(404, "document_not_found", "Document not found.")
    return doc


@router.post("", status_code=201, response_model=DocumentOut)
def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    deps: Deps = Depends(get_deps),
):
    data = file.file.read(deps.settings.max_upload_bytes + 1)  # bounded read
    return ingest_upload(db, deps, user.id, file.filename or "", data)


@router.get("", response_model=list[DocumentOut])
def list_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Document).where(Document.owner_id == user.id).order_by(Document.created_at.desc())
    ).all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _owned(db, user, document_id)


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    deps: Deps = Depends(get_deps),
):
    delete_document_full(db, deps, _owned(db, user, document_id))
