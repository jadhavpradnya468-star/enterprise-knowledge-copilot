import logging
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.deps import Deps
from app.agents.graph import run_workflow
from app.api.dependencies import get_current_user, get_db, get_deps, get_graph
from app.api.errors import AppError
from app.db import Document, Run, User
from app.observability.metrics import summarize_trace
from app.utils import new_id

logger = logging.getLogger("app.chat")
router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_ids: list[str] | None = Field(default=None, max_length=50)


class ChatResponse(BaseModel):
    run_id: str
    answer: str
    sources: list[dict]
    status: str
    metrics: dict


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    deps: Deps = Depends(get_deps),
    graph=Depends(get_graph),
):
    ids = list(dict.fromkeys(body.document_ids or []))
    if ids:
        owned = set(db.scalars(select(Document.id).where(
            Document.owner_id == user.id, Document.id.in_(ids), Document.status == "indexed")))
        if owned != set(ids):
            raise AppError(404, "document_not_found", "One or more documents were not found.")

    start = time.perf_counter()
    state = run_workflow(graph, body.question.strip(), user.id, ids or None)
    metrics = summarize_trace(state.get("trace", []), (time.perf_counter() - start) * 1000, deps.settings)
    final = state["final"]

    run = Run(id=new_id("run"), user_id=user.id, question=body.question, status=final["status"],
              answer=final["answer"], sources=final["sources"], trace=state.get("trace", []), metrics=metrics)
    db.add(run)
    db.commit()
    logger.info("run=%s status=%s latency_ms=%s", run.id, run.status, metrics["latency_ms"])
    return ChatResponse(run_id=run.id, answer=final["answer"], sources=final["sources"],
                        status=final["status"], metrics=metrics)


runs_router = APIRouter(tags=["runs"])


@runs_router.get("/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None or run.user_id != user.id:
        raise AppError(404, "run_not_found", "Run not found.")
    return {"run_id": run.id, "question": run.question, "status": run.status, "answer": run.answer,
            "sources": run.sources, "trace": run.trace, "metrics": run.metrics,
            "created_at": run.created_at.isoformat()}
