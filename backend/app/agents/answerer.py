from app.agents.deps import Deps
from app.agents.prompts import ANSWER_SYSTEM, answer_prompt
from app.observability.tracing import traced
from app.services.llm import INSUFFICIENT


def format_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"[{c['chunk_id']}] ({c['filename']}, page {c['page'] if c['page'] else 'n/a'})\n{c['text']}" for c in chunks
    )


def make_answerer(deps: Deps):
    @traced("answerer")
    def answerer(state):
        chunks = state["chunks"]
        res = deps.llm.generate(
            "answer", answer_prompt(state["question"], format_context(chunks)), system=ANSWER_SYSTEM,
            payload={"question": state["question"],
                     "chunks": [{"chunk_id": c["chunk_id"], "text": c["text"]} for c in chunks]},
        )
        text = res.text.strip()
        insufficient = not text or INSUFFICIENT in text
        return {
            "answer": "" if insufficient else text,
            "_detail": {"input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
                        "insufficient": insufficient},
        }

    return answerer
