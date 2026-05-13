"""Central configuration using pydantic-settings (reads .env automatically)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "CreditFraudService"
    app_env: str = "development"
    app_version: str = "1.0.0"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── Ollama / Qwen3 LLM ───────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:latest"
    ollama_timeout: int = 120

    # ── Embeddings ───────────────────────────────────────────────────────────
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"

    # ── ChromaDB ─────────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_fraud_kb: str = "fraud_knowledge_base"
    chroma_collection_transactions: str = "fraud_transactions"

    # ── RAG ──────────────────────────────────────────────────────────────────
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.3
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 64

    # ── ADK Agent ────────────────────────────────────────────────────────────
    adk_model: str = "ollama/qwen3:latest"
    adk_max_iterations: int = 10
    adk_session_timeout: int = 300

    # ── MCP ──────────────────────────────────────────────────────────────────
    mcp_server_name: str = "fraud-detection-mcp"
    mcp_transport: str = "stdio"

    # ── Governance ───────────────────────────────────────────────────────────
    audit_log_file: str = "./logs/audit.jsonl"
    governance_policy_file: str = "./config/policies.yaml"
    max_requests_per_minute: int = 60
    pii_masking_enabled: bool = True
    require_explainability: bool = True

    # ── Risk Thresholds ──────────────────────────────────────────────────────
    risk_threshold_high: float = 0.80
    risk_threshold_medium: float = 0.50
    risk_threshold_low: float = 0.20
    auto_block_threshold: float = 0.95

    @field_validator("app_env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def chroma_persist_path(self) -> Path:
        return Path(self.chroma_persist_dir)

    @property
    def audit_log_path(self) -> Path:
        path = Path(self.audit_log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
