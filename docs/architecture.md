# Architecture

```text
React UI ──HTTPS──> FastAPI ──> Ingestion pipeline ──> Vector store (local | Chroma | pgvector)
                       │                                      │
                       └──> LangGraph workflow ───────────────┘
                              planner → retriever → answerer → verifier ─┬─> composer
                                            ▲                            │
                                            └────────── retry ◄──────────┘  (bounded)
                       └──> SQL database: users, documents, chunks, runs (trace + metrics)
```

## Workflow nodes (`backend/app/agents`)

| Node | Responsibility | Model call |
|------|----------------|-----------|
| planner | Decide whether retrieval is needed; rewrite the query | yes |
| retriever | Embed query, owner-filtered vector search, drop chunks below `MIN_SCORE` | embedding only |
| answerer | Answer from retrieved context only; reply `INSUFFICIENT_EVIDENCE` if unsupported | yes |
| verifier | Check each claim against the context; fails closed on unparsable output | yes |
| retry | Increment attempt; the retriever then doubles `k` (bounded by `MAX_RETRIES`) | no |
| composer | Build the final answer, cited sources and status | no |

Routing: no chunks → abstain. Answerer says insufficient → retry or abstain. Verifier rejects → retry or abstain.
Any node exception is captured in the trace and the run ends as `failed` with a generic message.

## Key decisions

- **Authorization at retrieval time.** Every vector search is filtered by `owner_id`, and chunk rows are re-checked against the owner when text is loaded. Unknown and not-yours documents both return 404.
- **Stores hold vectors only.** Chunk text lives in SQL; the vector store returns `(chunk_id, score)`. Swapping stores does not change the agents.
- **Small state.** Workflow state carries chunk text (the answerer needs it) but the persisted trace stores only chunk IDs, scores, token counts and latencies.
- **No raw content in logs.** Logs carry request IDs, node names, latencies and exception *types* only.
- **Providers behind interfaces.** `LLM` and `Embedder` have Gemini and offline fake implementations. The fake provider is extractive and lexical, so it is only useful for tests and demos.
- **Synchronous ingestion.** Upload blocks until indexing finishes. Move to a task queue before handling large files.
