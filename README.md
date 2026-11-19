# Enterprise Knowledge Copilot

A multi-agent RAG application: upload PDF, DOCX or TXT files, ask questions in natural language, and get answers
that cite the passages they rely on. A LangGraph workflow plans the query, retrieves passages, drafts an answer from
that context only, and verifies the draft before returning it, or abstains when the evidence is insufficient.

> **Status: working prototype.** The backend, tests, evaluation harness and frontend are implemented. Read
> [What has and has not been verified](#what-has-and-has-not-been-verified) before describing this project to anyone.

## Features

- **Ingestion**: type/size/signature validation, text extraction with page numbers (PDF), overlapping chunks, embeddings, indexing.
- **Workflow**: planner → retriever → answerer → verifier → composer, with bounded retry and explicit "insufficient evidence" answers.
- **Security**: API-key auth, per-user ownership enforced at retrieval time, secrets from environment, no raw document text in logs, structured errors with request IDs.
- **Observability**: per-node latency, token counts, optional cost estimate, retrieved chunk IDs and retries stored per run (`GET /runs/{id}`).
- **Evaluation**: versioned dataset, Recall@k / Precision@k / correctness / groundedness proxy / abstention metrics, report with run metadata, run comparison.
- **Pluggable parts**: vector store (`local`, `chroma`, `pgvector`), LLM/embeddings (`gemini` or offline `fake`), file storage (`local` or `gcs`).

## Quick start (offline, no credentials)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
cp .env.example .env                                    # Windows: Copy-Item .env.example .env
uvicorn app.main:app --reload --app-dir backend         # http://localhost:8000/docs
```

In a second terminal:

```bash
cd frontend && npm install && npm run dev               # http://localhost:5173  (API key: demo-key)
```

Out of the box `LLM_PROVIDER=fake` and `EMBEDDING_PROVIDER=fake`. These are deterministic, lexical stand-ins so the whole
flow runs offline. **They are not a language model**; answers are extracted sentences. To use Gemini, set in `.env`:

```env
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=...            # or USE_VERTEX=true plus GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION
```

Switching embedding providers changes vector dimensions and meaning: delete and re-upload documents after switching.

## API

All routes are under `/api/v1` and need an `X-API-Key` header except `health`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/documents` | Upload and index a document (multipart `file`) |
| GET | `/documents` | List your documents |
| GET | `/documents/{id}` | Document status and metadata |
| DELETE | `/documents/{id}` | Delete a document, its chunks and vectors |
| POST | `/chat` | `{"question": "...", "document_ids": ["doc_..."]}` (ids optional) |
| GET | `/runs/{run_id}` | Workflow trace and metrics for a run |
| POST | `/evaluations/run` | Run the evaluation dataset |
| GET | `/evaluations/latest` | Most recent saved report |
| GET | `/health` | Health check |

```bash
curl -H "X-API-Key: demo-key" -F file=@policy.pdf http://localhost:8000/api/v1/documents
curl -H "X-API-Key: demo-key" -H "Content-Type: application/json" \
     -d '{"question":"What is the reimbursement policy for business travel?"}' http://localhost:8000/api/v1/chat
```

Statuses: `completed`, `insufficient_evidence`, `failed`.

## Tests and evaluation

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest -q                      # ingestion, auth, isolation, workflow routing, errors
python -m app.evaluation.runner          # writes backend/storage/eval_reports/eval_<timestamp>.json
```

See [docs/evaluation.md](docs/evaluation.md) for metric definitions and caveats.

## Docker (PostgreSQL + pgvector)

```bash
docker compose up --build        # UI http://localhost:3000, API http://localhost:8000/docs
```

## Repository layout

```text
backend/app/  api/ agents/ ingestion/ services/ observability/ evaluation/  config.py db.py main.py
backend/tests/   frontend/   docs/   docker-compose.yml   .env.example
```

## What has and has not been verified

| Area | Status |
|------|--------|
| Ingestion (TXT/DOCX/PDF), chunking, local vector store, auth, ownership isolation, workflow routing/retry/failure handling | Covered by `pytest` (16 tests passing) using the fake providers |
| Chroma vector store | Smoke-tested through the evaluation runner only |
| Evaluation harness | Runs end to end; with fake providers the numbers check the pipeline, not model quality |
| Frontend | Type-checks and builds; not manually exercised in a browser |
| Gemini / Vertex AI calls | Implemented against the `google-genai` SDK, **never run** (no credentials were available) |
| pgvector store, Docker Compose | Implemented, **never run** |
| GCS storage, Cloud Run deployment | Implemented/documented as a template, **never run** ([docs/deployment.md](docs/deployment.md)) |

## Known limitations

- Ingestion is synchronous; large files need a background queue.
- The `local` vector store scans one user's vectors in memory per query. Use pgvector or Chroma at scale.
- No OCR (scanned PDFs are rejected), no per-page numbers for DOCX, no rate limiting, API keys are static (swap in OIDC/JWT for real multi-tenant use).
- RAG and LLM verification are not guarantees of correctness. Keep sources visible and support human review.
- Multi-agent is not automatically better than single-agent RAG: compare quality, latency and cost before assuming it is.

## Resume wording

Only describe what you have run and measured yourself. Until you have used real Gemini models and deployed to Cloud Run,
do not list Vertex AI or Google Cloud Run as experience, and do not call the project production-grade. Replace general
claims with numbers from your own evaluation runs (record the dataset version, model, prompt version and date).
