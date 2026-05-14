# ── Application config: 12-factor, all secrets via env ───────────────────────
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Server
    HOST: str  = "0.0.0.0"
    PORT: int  = 8000
    LOG_LEVEL: str = "INFO"

    # Browser pool
    POOL_SIZE: int = 4
    USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # Resilience
    CB_FAILURE_THRESHOLD: int   = 5
    CB_RECOVERY_TIMEOUT: int    = 30
    BACKOFF_MAX_ATTEMPTS: int   = 5
    BACKOFF_BASE_WAIT: float    = 2.0
    BACKOFF_MAX_WAIT: float     = 60.0

    # Job queue
    MAX_QUEUE_SIZE: int = 100
    WORKER_COUNT: int   = 4