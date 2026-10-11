from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed application configuration loaded from environment variables."""

    app_name: str = "Tungelligence Agentic RAG"
    app_version: str = "1.5.4"
    environment: str = "development"
    debug: bool = False

    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:8b"
    llm_timeout_seconds: float = Field(default=120.0, gt=0, le=600)

    embedding_provider: str = "sentence_transformers"
    vector_store_backend: str = "faiss"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = Field(default=384, ge=8, le=8192)

    top_k: int = Field(default=8, ge=1, le=50)
    rerank_top_k: int = Field(default=4, ge=1, le=20)
    retrieval_min_score: float = Field(default=0.20, ge=-1, le=1)
    rerank_min_score: float = Field(default=0.10, ge=-1, le=1)

    chunk_size: int = Field(default=800, ge=100, le=8000)
    chunk_overlap: int = Field(default=120, ge=0, le=4000)
    max_document_size_mb: int = Field(default=25, ge=1, le=512)

    raw_data_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_data_dir: Path = PROJECT_ROOT / "data" / "processed"
    vector_data_dir: Path = PROJECT_ROOT / "data" / "vector"
    workspace_data_dir: Path = PROJECT_ROOT / "data" / "workspaces"
    workspace_db_path: Path = PROJECT_ROOT / "data" / "tungelligence.db"
    conversation_history_messages: int = Field(default=12, ge=2, le=50)
    max_history_chars: int = Field(default=12000, ge=1000, le=50000)
    max_context_chars: int = Field(default=28000, ge=4000, le=100000)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_ranges(self) -> "Settings":
        """Validate relationships that field-level constraints cannot express."""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self

    def ensure_directories(self) -> None:
        """Create application data directories when they do not exist."""
        for directory in (self.raw_data_dir, self.processed_data_dir, self.vector_data_dir, self.workspace_data_dir, self.workspace_db_path.parent):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one cached settings instance for the process lifetime."""
    return Settings()
