"""Small shared helpers (ids, tokenisation, JSON parsing, retries)."""
import json
import re
import time
import uuid
from typing import Callable, TypeVar

T = TypeVar("T")

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "of", "to", "in", "on", "at", "by",
    "for", "and", "or", "with", "from", "as", "it", "this", "that", "these", "those", "what", "which",
    "who", "whom", "when", "where", "why", "how", "does", "do", "did", "can", "could", "should",
    "would", "will", "may", "i", "my", "me", "we", "our", "you", "your", "their", "its", "if", "than",
    "then", "there", "about", "any", "per", "up", "not", "no", "has", "have", "had",
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _stem(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokenize(text: str, drop_stopwords: bool = True) -> list[str]:
    toks = [_stem(t) for t in _TOKEN.findall(text.lower())]
    return [t for t in toks if t not in STOPWORDS] if drop_stopwords else toks


def parse_json(text: str) -> dict | None:
    """Parse a JSON object from model output, tolerating code fences and surrounding prose."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    for candidate in (cleaned, _first_object(cleaned)):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            continue
    return None


def _first_object(text: str) -> str | None:
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else None


def with_retries(fn: Callable[[], T], attempts: int, base_delay: float = 0.5) -> T:
    """Bounded retry with exponential backoff."""
    last: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
            last = exc
            if i < attempts - 1:
                time.sleep(base_delay * (2**i))
    assert last is not None
    raise last
