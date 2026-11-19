from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
STORAGE_DIR = BASE_DIR / "storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BASE_DIR.parent / ".env", BASE_DIR / ".env"), extra="ignore"
    )

    app_env: str = "development"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    database_url: str = f"sqlite:///{(STORAGE_DIR / 'app.db').as_posix()}"
    vector_store: str = "local"  # local | chroma | pgvector
    chroma_dir: str = str(STORAGE_DIR / "chroma")

    # Providers: "fake" is an offline, deterministic stand-in used for tests and demos.
    llm_provider: str = "fake"  # fake | gemini
    embedding_provider: str = "fake"  # fake | gemini
    llm_model: str = "gemini-2.5-flash"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768
    gemini_api_key: str = ""
    use_vertex: bool = False
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    llm_timeout_s: float = 30.0
    llm_max_attempts: int = 3

    # Optional pricing (USD per 1M tokens). Cost is only reported when set.
    price_input_per_mtok: float = 0.0
    price_output_per_mtok: float = 0.0

    # Auth: "name:key,name2:key2". Replace before any real use.
    api_keys: str = "demo:demo-key"

    storage_backend: str = "local"  # local | gcs
    upload_dir: str = str(STORAGE_DIR / "uploads")
    gcs_bucket: str = ""
    max_upload_mb: int = 20

    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 5
    min_score: float = 0.15
    max_retries: int = 1  # extra retrieval rounds the verifier may request

    eval_enabled: bool = True
    eval_report_dir: str = str(STORAGE_DIR / "eval_reports")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def parsed_api_keys(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.api_keys.split(","):
            if ":" in pair:
                name, key = pair.split(":", 1)
                if name.strip() and key.strip():
                    out[name.strip()] = key.strip()
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
