# Deploying to Google Cloud Run (untested template)

These steps were **not** executed while generating this project. Treat them as a starting point and adjust names,
regions and IAM to your environment. Do not claim GCP/Vertex AI experience until you have deployed and tested this.

1. Create a project, enable `run.googleapis.com`, `artifactregistry.googleapis.com`, `aiplatform.googleapis.com`,
   `sqladmin.googleapis.com`, `secretmanager.googleapis.com`.
2. Create a Cloud SQL for PostgreSQL instance and run `CREATE EXTENSION vector;` (the app also tries to).
3. Create a GCS bucket for uploads. Grant the Cloud Run service account `roles/storage.objectAdmin` on it and `roles/aiplatform.user`.
4. Put `API_KEYS` and the database URL in Secret Manager.
5. Build and deploy the backend:

```bash
gcloud run deploy copilot-api --source backend --region <region> \
  --set-env-vars APP_ENV=production,VECTOR_STORE=pgvector,LLM_PROVIDER=gemini,EMBEDDING_PROVIDER=gemini,USE_VERTEX=true,\
GOOGLE_CLOUD_PROJECT=<project>,GOOGLE_CLOUD_LOCATION=<region>,STORAGE_BACKEND=gcs,GCS_BUCKET=<bucket> \
  --set-secrets API_KEYS=copilot-api-keys:latest,DATABASE_URL=copilot-db-url:latest \
  --add-cloudsql-instances <project>:<region>:<instance> --no-allow-unauthenticated
```

The backend image does not install `google-cloud-storage`; add it (see `requirements-optional.txt`) when using GCS.
6. Deploy the frontend (or serve the built `frontend/dist` from Cloud Storage/Firebase Hosting) and point `/api` at the service.
7. Verify: upload a test document, ask a question, confirm sources, open `/api/v1/runs/{id}`.
