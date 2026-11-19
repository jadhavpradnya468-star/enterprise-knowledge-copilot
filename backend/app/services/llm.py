import json
import re
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings
from app.services.genai_client import build_client
from app.utils import tokenize, with_retries

INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLM(Protocol):
    def generate(
        self, task: str, prompt: str, system: str | None = None, json_mode: bool = False,
        payload: dict | None = None,
    ) -> LLMResult: ...


class GeminiLLM:
    def __init__(self, settings: Settings):
        self.client, self.model = build_client(settings), settings.llm_model

    def generate(self, task, prompt, system=None, json_mode=False, payload=None) -> LLMResult:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0,
            response_mime_type="application/json" if json_mode else None,
        )
        resp = self.client.models.generate_content(model=self.model, contents=prompt, config=config)
        usage = getattr(resp, "usage_metadata", None)
        return LLMResult(
            text=(resp.text or "").strip(),
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
        )


class RetryingLLM:
    """Bounded retries with backoff around any provider. Timeouts are set on the provider client."""

    def __init__(self, inner: LLM, attempts: int):
        self.inner, self.attempts = inner, attempts

    def generate(self, *args, **kwargs) -> LLMResult:
        return with_retries(lambda: self.inner.generate(*args, **kwargs), self.attempts)


class FakeLLM:
    """Offline, deterministic, extractive stand-in for tests and demos. It is NOT a language model.

    Uses `payload` (structured inputs) instead of parsing the prompt.
    """

    SMALLTALK = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b", re.I)

    def generate(self, task, prompt, system=None, json_mode=False, payload=None) -> LLMResult:
        payload = payload or {}
        if task == "plan":
            q = payload.get("question", "")
            text = json.dumps(
                {"needs_retrieval": not self.SMALLTALK.match(q), "category": "factual", "rewritten_query": q}
            )
        elif task == "answer":
            text = self._answer(payload)
        elif task == "verify":
            text = self._verify(payload)
        else:
            text = ""
        return LLMResult(text=text, input_tokens=len(prompt.split()), output_tokens=len(text.split()))

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    def _answer(self, payload: dict) -> str:
        q_tokens = set(tokenize(payload.get("question", "")))
        scored = []
        for chunk in payload.get("chunks", []):
            for sent in self._sentences(chunk["text"]):
                overlap = len(q_tokens & set(tokenize(sent))) / max(1, len(q_tokens))
                scored.append((overlap, sent, chunk["chunk_id"]))
        scored.sort(key=lambda x: -x[0])
        best = [s for s in scored[:2] if s[0] >= 0.34]
        if not best:
            return INSUFFICIENT
        return " ".join(f"{sent} [{cid}]" for _, sent, cid in best)

    def _verify(self, payload: dict) -> str:
        context = set()
        for chunk in payload.get("chunks", []):
            context |= set(tokenize(chunk["text"]))
        answer = re.sub(r"\[[^\]]*\]", "", payload.get("answer", ""))
        unsupported = []
        for sent in self._sentences(answer):
            toks = tokenize(sent)
            if toks and len([t for t in toks if t in context]) / len(toks) < 0.6:
                unsupported.append(sent)
        return json.dumps({"supported": not unsupported, "unsupported_claims": unsupported})


def build_llm(s: Settings) -> LLM:
    inner: LLM = GeminiLLM(s) if s.llm_provider == "gemini" else FakeLLM()
    return RetryingLLM(inner, s.llm_max_attempts)
