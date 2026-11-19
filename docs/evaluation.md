# Evaluation

Run from `backend/`:

```bash
python -m app.evaluation.runner                       # writes storage/eval_reports/eval_<timestamp>.json
python -m app.evaluation.runner --compare A.json B.json
```

`POST /api/v1/evaluations/run` runs the same thing (disable with `EVAL_ENABLED=false`).

The runner ingests `evaluation/corpus/*.txt` as a throwaway `user_eval` account, runs every question in
`evaluation/dataset.jsonl`, then deletes the evaluation documents.

## Metrics

| Metric | How it is computed here |
|--------|-------------------------|
| recall@k | Share of a question's `evidence_keywords` found in the top-k retrieved chunks of the expected documents |
| precision@k | Share of top-k chunks that are from an expected document and contain an evidence keyword |
| answer_correctness_keyword | Share of `expected_points` present verbatim in the answer (a crude proxy) |
| groundedness_lexical_proxy | Share of answer content tokens present in the retrieved context (independent of the verifier) |
| abstention_rate_on_unanswerable | Share of `should_abstain` questions that ended as `insufficient_evidence` |
| false_abstention_rate_on_answerable | Share of answerable questions that wrongly abstained |
| latency, tokens, cost | From the run trace; cost only if `PRICE_*_PER_MTOK` are set; embedding tokens are not counted |

Every report records dataset version and hash, providers and models, prompt version, vector store, `k`, chunking
settings and the test date.

## Read this before quoting numbers

- The bundled dataset is 8 synthetic questions over 3 synthetic documents. It is a harness check, not a benchmark.
- With `LLM_PROVIDER=fake` / `EMBEDDING_PROVIDER=fake` the scores verify the pipeline only and say nothing about model quality.
- Keyword correctness and lexical groundedness are proxies. For real claims, review samples by hand or add an LLM-judge
  or human-rated step, and compare against a single-agent RAG baseline.
- Build a larger set from your own documents, including ambiguous and absent-answer questions, before drawing conclusions.
