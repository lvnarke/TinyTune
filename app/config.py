import os
from dataclasses import dataclass


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://tinytune:tinytune-local-only@localhost:5432/tinytune"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "8"))
    db_acquire_timeout_seconds: float = float(
        os.getenv("DB_ACQUIRE_TIMEOUT_SECONDS", "1.0")
    )
    cache_enabled: bool = _bool_env("CACHE_ENABLED", True)
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "30"))
    play_mode: str = os.getenv("PLAY_MODE", "async").strip().lower()
    worker_processing_delay_ms: int = int(
        os.getenv("WORKER_PROCESSING_DELAY_MS", "25")
    )
    worker_batch_size: int = int(os.getenv("WORKER_BATCH_SIZE", "25"))
    worker_claim_idle_ms: int = int(os.getenv("WORKER_CLAIM_IDLE_MS", "5000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    success_log_sample_rate: float = float(os.getenv("SUCCESS_LOG_SAMPLE_RATE", "0.01"))

    stream_name: str = "tinytune:play-events"
    consumer_group: str = "play-processors"

    def validate(self) -> None:
        if self.play_mode not in {"sync", "async"}:
            raise ValueError("PLAY_MODE must be either 'sync' or 'async'")
        if self.db_pool_size < 1:
            raise ValueError("DB_POOL_SIZE must be positive")
        if not 0 <= self.success_log_sample_rate <= 1:
            raise ValueError("SUCCESS_LOG_SAMPLE_RATE must be between 0 and 1")


settings = Settings()
settings.validate()

