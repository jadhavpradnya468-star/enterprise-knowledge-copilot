import operator
from typing import Annotated, TypedDict


class GraphState(TypedDict, total=False):
    # inputs
    question: str
    user_id: str
    document_ids: list[str] | None
    # planner
    needs_retrieval: bool
    category: str
    query: str
    top_k: int
    attempt: int
    # retrieval / answer / verification (chunks carry text because the answerer needs it;
    # the persisted trace stores only chunk ids)
    chunks: list[dict]
    answer: str
    supported: bool
    unsupported_claims: list[str]
    # outputs
    status: str  # completed | insufficient_evidence | failed
    error: str | None
    final: dict
    trace: Annotated[list[dict], operator.add]
