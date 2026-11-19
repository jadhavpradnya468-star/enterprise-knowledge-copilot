from app.agents.deps import Deps
from app.agents.prompts import PLANNER_SYSTEM, planner_prompt
from app.observability.tracing import traced
from app.utils import parse_json


def make_planner(deps: Deps):
    @traced("planner")
    def planner(state):
        q = state["question"]
        res = deps.llm.generate("plan", planner_prompt(q), system=PLANNER_SYSTEM, json_mode=True, payload={"question": q})
        data = parse_json(res.text) or {}
        needs = data.get("needs_retrieval", True)
        return {
            "needs_retrieval": needs if isinstance(needs, bool) else True,
            "category": str(data.get("category", "factual"))[:32],
            "query": str(data.get("rewritten_query") or q)[:500],
            "top_k": deps.settings.top_k,
            "attempt": 0,
            "_detail": {"input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                        "needs_retrieval": needs if isinstance(needs, bool) else True},
        }

    return planner
