import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.agents.deps import build_deps
from app.agents.graph import build_graph
from app.api.errors import register_error_handlers
from app.api.routes import chat, documents, evaluations
from app.config import get_settings
from app.db import Base, SessionLocal, get_engine
from app.observability.tracing import configure_logging, request_id_var
from app.security import bootstrap_users


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    Base.metadata.create_all(get_engine())
    with SessionLocal() as db:
        bootstrap_users(db, s)
    app.state.deps = build_deps(s)
    app.state.graph = build_graph(app.state.deps)
    if s.llm_provider == "fake" or s.embedding_provider == "fake":
        logging.getLogger("app").warning(
            "Running with the offline FAKE LLM/embedding provider. Set LLM_PROVIDER=gemini and "
            "EMBEDDING_PROVIDER=gemini for real model output."
        )
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Enterprise Knowledge Copilot", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origin_list, allow_methods=["*"], allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

    register_error_handlers(app)
    for r in (documents.router, chat.router, chat.runs_router, evaluations.router):
        app.include_router(r, prefix=s.api_prefix)

    @app.get(f"{s.api_prefix}/health", tags=["health"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
