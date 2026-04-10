import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://dispatch:dispatch@localhost/dispatch",
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    INFERENCE_URL: str = os.getenv("INFERENCE_URL", "http://localhost:8001")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").upper()
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() == "true"

    SCHEDULER_FORECAST_INTERVAL_MIN: int = int(
        os.getenv("SCHEDULER_FORECAST_INTERVAL_MIN", "30")
    )
    SCHEDULER_VEHICLE_CHECK_INTERVAL_MIN: int = int(
        os.getenv("SCHEDULER_VEHICLE_CHECK_INTERVAL_MIN", "5")
    )


settings = Settings()
