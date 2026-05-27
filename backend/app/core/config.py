from functools import lru_cache
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME:    str = "SentryLens"
    APP_ENV:     str = "development"
    SECRET_KEY:  str = "insecure-dev-key-change-in-production"
    API_V1_PREFIX: str = "/api/v1"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS:   int = 30

    # Registration — False in production means only admins can create users
    REGISTRATION_OPEN: bool = True

    # Dashboard URL embedded in SMS alerts
    DASHBOARD_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL:      str = "postgresql+asyncpg://sentrylens:sentrylens_dev_pass@postgres:5432/sentrylens"
    DATABASE_URL_SYNC: str = "postgresql://sentrylens:sentrylens_dev_pass@postgres:5432/sentrylens"

    # Redis
    REDIS_URL:              str = "redis://redis:6379/0"
    CELERY_BROKER_URL:      str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND:  str = "redis://redis:6379/1"

    # Twilio
    TWILIO_ACCOUNT_SID:  str = ""
    TWILIO_AUTH_TOKEN:   str = ""
    TWILIO_FROM_NUMBER:  str = ""
    DEFAULT_ALERT_RECIPIENTS: str = ""

    # Model
    MODEL_PATH:              str   = "/app/models/sentrylens_best.pt"
    FALLBACK_MODEL:          str   = "yolov8m.pt"
    INFERENCE_CONFIDENCE:    float = 0.65
    NMS_IOU_THRESHOLD:       float = 0.45
    FRAME_QUEUE_MAX:         int   = 30
    INFERENCE_EVERY_N_FRAMES: int  = 3

    # Violations
    ALERT_COOLDOWN_SECONDS:        int   = 30
    VIOLATION_CONFIDENCE_THRESHOLD: float = 0.70
    SCAFFOLD_OVERCROWD_THRESHOLD:   int   = 6

    # Storage
    SNAPSHOT_DIR:         str = "/app/snapshots"
    MAX_SNAPSHOT_AGE_DAYS: int = 90

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost"

    LOG_LEVEL: str = "INFO"

    # ── Validators ─────────────────────────────────────────────────

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_secure(cls, v: str, info) -> str:
        """BUG-1 FIX: refuse to start with default key in non-dev environments."""
        env = info.data.get("APP_ENV", "development")
        insecure = {
            "insecure-dev-key-change-in-production",
            "changeme", "secret", "password", "",
        }
        if env not in ("development", "test") and (v in insecure or len(v) < 32):
            raise ValueError(
                "SECRET_KEY must be ≥32 chars and not a known default in non-dev environments. "
                "Generate: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def alert_recipients_list(self) -> List[str]:
        if not self.DEFAULT_ALERT_RECIPIENTS:
            return []
        return [r.strip() for r in self.DEFAULT_ALERT_RECIPIENTS.split(",") if r.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
