"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://dispatch:dispatch@postgres/dispatch"
    REDIS_URL: str = "redis://redis:6379/0"
    INFERENCE_URL: str = "http://inference:8001"
    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"
    SECRET_KEY: str = "change_me"
    LOG_LEVEL: str = "info"
    CORS_ORIGINS: str = "*"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
