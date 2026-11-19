from app.agents.answerer import format_context
from app.agents.deps import Deps
from app.agents.prompts import VERIFIER_SYSTEM, verifier_prompt
from app.observability.tracing import traced
from app.utils import parse_json


def make_verifier(deps: Deps):
    @traced("verifier")
    def verifier(state):
        chunks = state["chunks"]
        res = deps.llm.generate(
            "verify", verifier_prompt(state["answer"], format_context(chunks)), system=VERIFIER_SYSTEM,
            json_mode=True,
            payload={"answer": state["answer"],
                     "chunks": [{"chunk_id": c["chunk_id"], "text": c["text"]} for c in chunks]},
        )
        data = parse_json(res.text)
        if not data or "supported" not in data:
            supported, claims = False, ["verifier output could not be parsed"]  # fail closed
        else:
            supported = data["supported"] is True
            claims = [str(c)[:300] for c in (data.get("unsupported_claims") or [])][:10]
        return {
            "supported": supported,
            "unsupported_claims": claims,
            "_detail": {"input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                        "supported": supported, "unsupported_count": len(claims)},
        }

    return verifier
