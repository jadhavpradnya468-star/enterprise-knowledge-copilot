import json

from app.agents.deps import Deps
from app.agents.graph import build_graph, run_workflow
from app.services.llm import FakeLLM, LLMResult
from tests.conftest import ALICE, upload

Q = "What is the reimbursement policy for business travel?"


class UnsupportedVerifier(FakeLLM):
    def generate(self, task, *a, **kw):
        if task == "verify":
            return LLMResult(json.dumps({"supported": False, "unsupported_claims": ["x"]}))
        return super().generate(task, *a, **kw)


class BrokenAnswerer(FakeLLM):
    def generate(self, task, *a, **kw):
        if task == "answer":
            raise TimeoutError("boom")
        return super().generate(task, *a, **kw)


def _deps(client, llm):
    d = client.app.state.deps
    return Deps(d.settings, llm, d.embedder, d.store, d.storage)


def test_unsupported_answer_retries_then_abstains(client):
    upload(client, ALICE)
    state = run_workflow(build_graph(_deps(client, UnsupportedVerifier())), Q, "user_alice")
    nodes = [t["node"] for t in state["trace"]]
    assert nodes == ["planner", "retriever", "answerer", "verifier", "retry", "retriever",
                     "answerer", "verifier", "composer"]
    assert state["final"]["status"] == "insufficient_evidence"
    assert state["final"]["sources"] == []


def test_node_failure_is_captured_and_returns_failed(client):
    upload(client, ALICE)
    state = run_workflow(build_graph(_deps(client, BrokenAnswerer())), Q, "user_alice")
    assert state["final"]["status"] == "failed"
    err = [t for t in state["trace"] if t["status"] == "error"]
    assert err and err[0]["node"] == "answerer"
