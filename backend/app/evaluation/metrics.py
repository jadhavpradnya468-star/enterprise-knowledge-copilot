import statistics

from app.utils import tokenize


def chunk_is_relevant(chunk: dict, item: dict) -> bool:
    if chunk["filename"] not in item.get("expected_docs", []):
        return False
    kws = [k.lower() for k in item.get("evidence_keywords", [])]
    return not kws or any(k in chunk["text"].lower() for k in kws)


def recall_at_k(chunks: list[dict], item: dict) -> float | None:
    """Share of the item's evidence keywords that appear in the retrieved chunks."""
    kws = [k.lower() for k in item.get("evidence_keywords", [])]
    if not kws:
        return None
    blob = " ".join(c["text"].lower() for c in chunks if c["filename"] in item.get("expected_docs", []))
    return sum(k in blob for k in kws) / len(kws)


def precision_at_k(chunks: list[dict], item: dict) -> float | None:
    return sum(chunk_is_relevant(c, item) for c in chunks) / len(chunks) if chunks else 0.0


def answer_correctness(answer: str, item: dict) -> float | None:
    """Keyword proxy: share of expected answer points found verbatim (case-insensitive)."""
    pts = [p.lower() for p in item.get("expected_points", [])]
    return sum(p in answer.lower() for p in pts) / len(pts) if pts else None


def lexical_groundedness(answer: str, chunks: list[dict]) -> float | None:
    """Independent cheap proxy: share of answer content tokens present in the retrieved context."""
    import re

    toks = tokenize(re.sub(r"\[[^\]]*\]", "", answer))
    if not toks or not chunks:
        return None
    ctx = set(tokenize(" ".join(c["text"] for c in chunks)))
    return sum(t in ctx for t in toks) / len(toks)


def mean(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.fmean(vals), 4) if vals else None


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(round(p * (len(s) - 1))))], 1)
