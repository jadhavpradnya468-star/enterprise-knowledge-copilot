from dataclasses import dataclass

from app.config import Settings, get_settings
from app.services.embeddings import Embedder, build_embedder
from app.services.llm import LLM, build_llm
from app.services.storage import Storage, build_storage
from app.services.vector_store import VectorStore, build_vector_store


@dataclass
class Deps:
    settings: Settings
    llm: LLM
    embedder: Embedder
    store: VectorStore
    storage: Storage


def build_deps(settings: Settings | None = None) -> Deps:
    s = settings or get_settings()
    return Deps(s, build_llm(s), build_embedder(s), build_vector_store(s), build_storage(s))
