"""
config.py — Three-tier configuration abstraction for Schedulo.
Automatically selects the correct settings class based on the ENVIRONMENT env variable.
Usage: from schedulo.config import get_settings; settings = get_settings()
"""

from __future__ import annotations

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocalSettings(BaseSettings):
    """Tier 1 — Local prototype (laptop / desktop, no cloud required)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Deployment ─────────────────────────────────────────────────────────────
    environment: str = "local"
    debug: bool = True
    secret_key: str = "local-dev-secret-change-in-production-only"
    app_name: str = "Schedulo"
    app_version: str = "1.0.0"

    # ── Database ───────────────────────────────────────────────────────────────
    db_engine: str = "sqlite"  # sqlite | postgresql
    database_url: str = "sqlite+aiosqlite:///./schedulo.db"

    # ── Cache ──────────────────────────────────────────────────────────────────
    cache_backend: str = "memory"  # memory | redis
    redis_url: str = "redis://localhost:6379/0"

    # ── Task Queue ─────────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = True  # Synchronous in prototype

    # ── File Storage ───────────────────────────────────────────────────────────
    storage_backend: str = "local"  # local | s3 | azure
    output_dir: str = "./outputs"
    models_dir: str = "./ml_models"
    logs_dir: str = "./logs"

    # ── Groq LLM (primary fast AI — free tier at https://console.groq.com) ───
    groq_api_key: str = ""
    groq_model: str = "llama3-8b-8192"          # free, fast, 8k context

    # ── Hugging Face LLM ───────────────────────────────────────────────────────
    hf_api_token: str = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    hf_primary_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    hf_fallback_model: str = "HuggingFaceH4/zephyr-7b-beta"
    hf_fast_model: str = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
    hf_inference_url: str = "https://api-inference.huggingface.co/models"
    hf_max_new_tokens: int = 1024
    hf_temperature: float = 0.3
    hf_top_p: float = 0.9
    hf_repetition_penalty: float = 1.1
    hf_stream: bool = True

    # ── Auth ───────────────────────────────────────────────────────────────────
    jwt_secret: str = "local-jwt-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours locally

    # ── CORS ───────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ── Scheduler Performance (tuned for laptop) ───────────────────────────────
    ga_population_size: int = 50
    ga_max_generations: int = 100
    csp_time_limit_seconds: int = 30
    rl_training_timesteps: int = 100_000

    @property
    def allowed_origins_list(self) -> list[str]:
        """Return CORS origins as a list."""
        return [o.strip() for o in self.allowed_origins.split(",")]


class ServerSettings(LocalSettings):
    """Tier 2 — University internal server (on-premise Linux server)."""

    environment: str = "server"
    debug: bool = False
    db_engine: str = "postgresql"
    cache_backend: str = "redis"
    celery_task_always_eager: bool = False

    # Full GA settings for server hardware
    ga_population_size: int = 200
    ga_max_generations: int = 500
    csp_time_limit_seconds: int = 60
    rl_training_timesteps: int = 1_000_000


class CloudSettings(ServerSettings):
    """Tier 3 — Cloud deployment (AWS / GCP / Azure)."""

    environment: str = "cloud"
    storage_backend: str = "s3"

    # Maximum GA settings for cloud scalability
    ga_population_size: int = 500
    ga_max_generations: int = 1000


_SETTINGS_MAP = {
    "local": LocalSettings,
    "server": ServerSettings,
    "cloud": CloudSettings,
}


@lru_cache()
def get_settings() -> LocalSettings:
    """
    Return the correct settings object based on the ENVIRONMENT env variable.
    Cached via lru_cache so it is instantiated only once per process.
    """
    env = os.getenv("ENVIRONMENT", "local").lower()
    cls = _SETTINGS_MAP.get(env, LocalSettings)
    return cls()
