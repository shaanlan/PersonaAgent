from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_port: int = 8090
    app_base_url: str = "http://127.0.0.1:8090"
    app_version: str = "1.0.0"
    log_level: str = "info"
    request_timeout_seconds: int = 60
    chat_bind_addr: str = "127.0.0.1"

    auth_jwt_secret: str = ""
    auth_jwt_algorithm: str = "HS256"
    auth_jwt_issuer: str = "personality-matrix"
    auth_jwt_audience: str = ""
    internal_service_token: str = ""

    personality_api_base_url: str = ""
    personality_api_timeout_seconds: float = 3.0

    database_url: str = ""
    mysql_host: str = ""
    mysql_port: int = 3306
    mysql_database: str = "personality"
    mysql_user: str = ""
    mysql_password: str = ""
    db_auto_create: bool = True

    chroma_persist_dir: str = "./data/chroma"
    chroma_collection: str = "kb_mock_0000"
    index_snapshot_id: str = "mock"
    catalog_path: str = ""
    index_manifest_path: str = ""
    index_artifact_dir: str = ""

    embedding_provider: str = "mock"
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    embedding_api_base: str = "http://127.0.0.1:11434"
    embedding_api_key: str = ""

    rag_top_k: int = 6
    rag_candidate_k: int = 12
    rag_score_threshold: float = 0.35
    rag_max_per_doc: int = 2
    rag_max_sources: int = 3
    rag_locale_boost: float = 0.03
    content_snapshot_dir: str = ""

    llm_provider: str = "mock"
    llm_router_model: str = "ollama/qwen2.5:3b-instruct"
    llm_answer_model: str = "ollama/qwen2.5:3b-instruct"
    llm_summary_model: str = "ollama/qwen2.5:3b-instruct"
    llm_api_base: str = "http://127.0.0.1:11434"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 30.0
    llm_temperature: float = 0.3
    llm_fallback_enabled: bool = False
    llm_fallback_model: str = ""
    llm_fallback_api_base: str = ""
    llm_fallback_api_key: str = ""

    max_user_message_chars: int = 4000
    max_assistant_chars: int = 1200
    max_sessions_per_user: int = 100
    max_messages_per_session: int = 200
    session_ttl_days: int = 30
    message_retention_days: int = 30

    rate_session_create_per_minute: int = 10
    rate_message_per_minute: int = 20
    rate_global_streams: int = 20
    rate_ip_streams: int = 2
    rate_uid_streams: int = 3

    generation_first_token_timeout_seconds: int = 45
    generation_total_timeout_seconds: int = 60

    prompt_version: str = "answer/v1"

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.mysql_host:
            password = quote_plus(self.mysql_password)
            return (
                f"mysql+asyncmy://{self.mysql_user}:{password}"
                f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
            )
        return "sqlite+aiosqlite:///./data/persona_chat.db"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def jwt_configured(self) -> bool:
        return bool(self.auth_jwt_secret)

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider.lower() not in {"", "mock", "none"}

    @property
    def embedding_enabled(self) -> bool:
        return self.embedding_provider.lower() not in {"", "mock", "none"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
