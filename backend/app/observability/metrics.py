from app.config import Settings


def summarize_trace(trace: list[dict], total_latency_ms: float, settings: Settings) -> dict:
    """Aggregate per-node trace entries into request-level metrics.

    Token counts cover generation calls only (planner/answerer/verifier); embedding calls are not
    counted. Cost is None unless prices are configured.
    """
    in_tok = sum(t.get("input_tokens", 0) for t in trace)
    out_tok = sum(t.get("output_tokens", 0) for t in trace)
    node_latency: dict[str, float] = {}
    for t in trace:
        node_latency[t["node"]] = round(node_latency.get(t["node"], 0.0) + t["latency_ms"], 1)
    cost = None
    if settings.price_input_per_mtok or settings.price_output_per_mtok:
        cost = round(
            (in_tok * settings.price_input_per_mtok + out_tok * settings.price_output_per_mtok) / 1e6, 6
        )
    return {
        "latency_ms": round(total_latency_ms),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "node_latency_ms": node_latency,
        "retries": sum(1 for t in trace if t["node"] == "retry"),
        "estimated_cost_usd": cost,
    }
