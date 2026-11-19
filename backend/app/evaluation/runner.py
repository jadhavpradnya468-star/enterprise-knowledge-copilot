"""Repeatable evaluation: ingest the bundled corpus, run every dataset question, write a report.

Usage (from backend/):  python -m app.evaluation.runner
                        python -m app.evaluation.runner --compare report_a.json report_b.json
"""
import argparse
import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from app.agents.deps import Deps, build_deps
from app.agents.graph import build_graph, run_workflow
from app.agents.prompts import PROMPT_VERSION
from app.agents.retriever import retrieve_chunks
from app.db import Base, Document, SessionLocal, User, get_engine
from app.evaluation import metrics as m
from app.ingestion.indexing import delete_document_full, ingest_upload
from app.observability.metrics import summarize_trace
from app.security import hash_key

EVAL_USER_ID = "user_eval"
HERE = Path(__file__).parent
DATASET = HERE / "dataset.jsonl"
CORPUS = HERE / "corpus"


def load_dataset(path: Path) -> tuple[dict, list[dict]]:
    meta, items = {}, []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "_meta" in row:
            meta = row["_meta"]
        else:
            items.append(row)
    return meta, items


def _ensure_eval_user() -> None:
    with SessionLocal() as db:
        if db.get(User, EVAL_USER_ID) is None:
            db.add(User(id=EVAL_USER_ID, name="eval", api_key_hash=hash_key(secrets.token_hex(32))))
            db.commit()


def _cleanup(deps: Deps) -> None:
    with SessionLocal() as db:
        for doc in db.query(Document).filter(Document.owner_id == EVAL_USER_ID).all():
            delete_document_full(db, deps, doc)


def run_evaluation(deps: Deps, dataset_path: Path = DATASET, corpus_dir: Path = CORPUS, k: int | None = None) -> dict:
    s = deps.settings
    k = k or s.top_k
    Base.metadata.create_all(get_engine())
    _ensure_eval_user()
    _cleanup(deps)
    meta, items = load_dataset(dataset_path)
    graph = build_graph(deps)

    with SessionLocal() as db:
        for f in sorted(corpus_dir.glob("*.txt")):
            ingest_upload(db, deps, EVAL_USER_ID, f.name, f.read_bytes())

    per_q = []
    try:
        for item in items:
            retrieved = retrieve_chunks(deps, EVAL_USER_ID, None, item["question"], k)
            t0 = time.perf_counter()
            state = run_workflow(graph, item["question"], EVAL_USER_ID)
            total_ms = (time.perf_counter() - t0) * 1000
            final = state["final"]
            mx = summarize_trace(state["trace"], total_ms, s)
            abstained = final["status"] == "insufficient_evidence"
            should_abstain = bool(item.get("should_abstain"))
            per_q.append({
                "id": item["id"], "type": item.get("type"), "status": final["status"],
                "should_abstain": should_abstain, "abstained": abstained,
                "recall_at_k": None if should_abstain else m.recall_at_k(retrieved, item),
                "precision_at_k": None if should_abstain else m.precision_at_k(retrieved, item),
                "correctness": None if should_abstain or abstained else m.answer_correctness(final["answer"], item),
                "groundedness_lexical": None if abstained else m.lexical_groundedness(final["answer"], state.get("chunks", [])),
                "retrieved_chunk_ids": [c["chunk_id"] for c in retrieved],
                "latency_ms": mx["latency_ms"], "input_tokens": mx["input_tokens"],
                "output_tokens": mx["output_tokens"], "cost_usd": mx["estimated_cost_usd"],
            })
    finally:
        _cleanup(deps)

    ans = [q for q in per_q if not q["should_abstain"]]
    unans = [q for q in per_q if q["should_abstain"]]
    lat = [q["latency_ms"] for q in per_q]
    summary = {
        f"recall@{k}": m.mean([q["recall_at_k"] for q in ans]),
        f"precision@{k}": m.mean([q["precision_at_k"] for q in ans]),
        "answer_correctness_keyword": m.mean([q["correctness"] for q in ans]),
        "groundedness_lexical_proxy": m.mean([q["groundedness_lexical"] for q in per_q]),
        "abstention_rate_on_unanswerable": m.mean([1.0 if q["abstained"] else 0.0 for q in unans]),
        "false_abstention_rate_on_answerable": m.mean([1.0 if q["abstained"] else 0.0 for q in ans]),
        "latency_ms_mean": m.mean(lat), "latency_ms_p50": m.percentile(lat, 0.5),
        "latency_ms_p95": m.percentile(lat, 0.95),
        "input_tokens_mean": m.mean([q["input_tokens"] for q in per_q]),
        "output_tokens_mean": m.mean([q["output_tokens"] for q in per_q]),
        "cost_usd_mean": m.mean([q["cost_usd"] for q in per_q]),
    }
    now = datetime.now(timezone.utc)
    report = {
        "metadata": {
            "run_id": f"eval_{now.strftime('%Y%m%dT%H%M%SZ')}",
            "test_date_utc": now.isoformat(timespec="seconds"),
            "dataset_version": meta.get("version", "unversioned"),
            "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest()[:16],
            "dataset_size": len(items),
            "llm_provider": s.llm_provider, "llm_model": s.llm_model if s.llm_provider != "fake" else "fake-extractive",
            "embedding_provider": s.embedding_provider,
            "embedding_model": s.embedding_model if s.embedding_provider != "fake" else "fake-hashed-bow",
            "prompt_version": PROMPT_VERSION, "vector_store": s.vector_store,
            "top_k": k, "min_score": s.min_score, "chunk_size": s.chunk_size,
            "chunk_overlap": s.chunk_overlap, "max_retries": s.max_retries,
            "note": "Fake providers produce pipeline checks only, not quality measurements."
            if "fake" in (s.llm_provider, s.embedding_provider) else "",
        },
        "summary": summary,
        "questions": per_q,
    }
    out_dir = Path(s.eval_report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{report['metadata']['run_id']}.json").write_text(json.dumps(report, indent=2))
    return report


def compare(a_path: str, b_path: str) -> None:
    a, b = (json.loads(Path(p).read_text()) for p in (a_path, b_path))
    print(f"{'metric':42} {'A':>10} {'B':>10} {'delta':>10}")
    for key in a["summary"]:
        va, vb = a["summary"].get(key), b["summary"].get(key)
        delta = round(vb - va, 4) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else ""
        print(f"{key:42} {str(va):>10} {str(vb):>10} {str(delta):>10}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"))
    parser.add_argument("-k", type=int, default=None)
    args = parser.parse_args()
    if args.compare:
        compare(*args.compare)
    else:
        rep = run_evaluation(build_deps(), k=args.k)
        print(json.dumps({"metadata": rep["metadata"], "summary": rep["summary"]}, indent=2))
