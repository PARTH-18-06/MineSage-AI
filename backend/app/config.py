from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    redis_url: str
    minio_endpoint: str
    minio_root_user: str
    minio_root_password: str
    minio_bucket: str = "documents"
    minio_secure: bool = False
    jwt_secret_key: str = "change-this-local-dev-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 120
    default_admin_email: str = "admin@cmpdi.local"
    default_admin_password: str = "AdminPass123!"
    default_admin_full_name: str = "CMPDI Demo Admin"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    qa_mode: str = "local_extractive"
    llm_provider: str = "groq"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    data_quality_ground_truth_path: str = "/samples/demo/evaluation/ground_truth.json"
    workflow_manual_baseline_path: str = "/samples/demo/evaluation/manual_baseline_assumptions.json"
    workflow_benchmark_path: str = "/samples/demo/evaluation/workflow_benchmark.json"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
