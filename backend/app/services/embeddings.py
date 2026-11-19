import hashlib
import math
from typing import Protocol

from app.config import Settings
from app.services.genai_client import build_client
from app.utils import tokenize, with_retries


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeEmbedder:
    """Deterministic hashed bag-of-words embeddings. Offline and lexical only: for tests/demos."""

    def __init__(self, dim: int):
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in tokenize(text):
            idx = int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "big") % self.dim
            vec[idx] += 1.0
        return _normalize(vec)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class GeminiEmbedder:
    def __init__(self, settings: Settings):
        self.client = build_client(settings)
        self.model, self.dim, self.attempts = settings.embedding_model, settings.embedding_dim, settings.llm_max_attempts

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        from google.genai import types

        out: list[list[float]] = []
        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            resp = with_retries(
                lambda b=batch: self.client.models.embed_content(
                    model=self.model,
                    contents=b,
                    config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.dim),
                ),
                self.attempts,
            )
            out.extend(_normalize(list(e.values)) for e in resp.embeddings)
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


def build_embedder(s: Settings) -> Embedder:
    if s.embedding_provider == "gemini":
        return GeminiEmbedder(s)
    return FakeEmbedder(s.embedding_dim)
