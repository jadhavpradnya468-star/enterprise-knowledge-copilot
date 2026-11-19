import re

from langgraph.graph import END, START, StateGraph

from app.agents.answerer import make_answerer
from app.agents.deps import Deps
from app.agents.planner import make_planner
from app.agents.retriever import make_retriever
from app.agents.state import GraphState
from app.agents.verifier import make_verifier
from app.observability.tracing import traced

INSUFFICIENT_MESSAGE = (
    "I couldn't find enough evidence in the selected documents to answer this question reliably."
)
SMALLTALK_MESSAGE = "Hello! Ask me a question about your uploaded documents and I'll answer with sources."
FAILED_MESSAGE = "The request could not be completed because of an internal error. Please try again."


def _cited_ids(answer: str, valid: set[str]) -> set[str]:
    found: set[str] = set()
    for group in re.findall(r"\[([^\[\]]+)\]", answer):
        found.update(p.strip() for p in group.split(",") if p.strip() in valid)
    return found


@traced("composer")
def compose(state):
    if state.get("error"):
        final = {"status": "failed", "answer": FAILED_MESSAGE, "sources": []}
    elif state.get("needs_retrieval") is False:
        final = {"status": "completed", "answer": SMALLTALK_MESSAGE, "sources": []}
    elif state.get("answer") and state.get("supported"):
        chunks = state.get("chunks", [])
        cited = _cited_ids(state["answer"], {c["chunk_id"] for c in chunks})
        used = [c for c in chunks if c["chunk_id"] in cited] or chunks
        sources = [{"document_id": c["document_id"], "filename": c["filename"], "page": c["page"],
                    "chunk_id": c["chunk_id"], "score": c["score"]} for c in used]
        final = {"status": "completed", "answer": state["answer"], "sources": sources}
    else:
        final = {"status": "insufficient_evidence", "answer": INSUFFICIENT_MESSAGE, "sources": []}
    return {"final": final, "status": final["status"], "_detail": {"status": final["status"]}}


@traced("retry")
def bump_attempt(state):
    return {"attempt": state.get("attempt", 0) + 1}


def build_graph(deps: Deps):
    max_retries = deps.settings.max_retries
    g = StateGraph(GraphState)
    g.add_node("planner", make_planner(deps))
    g.add_node("retriever", make_retriever(deps))
    g.add_node("answerer", make_answerer(deps))
    g.add_node("verifier", make_verifier(deps))
    g.add_node("retry", bump_attempt)
    g.add_node("composer", compose)

    def can_retry(s) -> bool:
        return s.get("attempt", 0) < max_retries

    def after_planner(s):
        return "composer" if s.get("error") or not s.get("needs_retrieval") else "retriever"

    def after_retriever(s):
        return "answerer" if not s.get("error") and s.get("chunks") else "composer"

    def after_answerer(s):
        if s.get("error"):
            return "composer"
        if not s.get("answer"):  # model said the context is insufficient
            return "retry" if can_retry(s) else "composer"
        return "verifier"

    def after_verifier(s):
        if s.get("error") or s.get("supported"):
            return "composer"
        return "retry" if can_retry(s) else "composer"

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", after_planner, {"retriever": "retriever", "composer": "composer"})
    g.add_conditional_edges("retriever", after_retriever, {"answerer": "answerer", "composer": "composer"})
    g.add_conditional_edges("answerer", after_answerer,
                            {"verifier": "verifier", "retry": "retry", "composer": "composer"})
    g.add_conditional_edges("verifier", after_verifier, {"retry": "retry", "composer": "composer"})
    g.add_edge("retry", "retriever")
    g.add_edge("composer", END)
    return g.compile()


def run_workflow(graph, question: str, user_id: str, document_ids: list[str] | None = None) -> dict:
    return graph.invoke(
        {"question": question, "user_id": user_id, "document_ids": document_ids or None, "trace": []}
    )
