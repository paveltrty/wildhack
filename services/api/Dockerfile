FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] \
    sqlalchemy[asyncio] asyncpg alembic \
    apscheduler redis aiohttp \
    pandas pyarrow numpy \
    pydantic pydantic-settings \
    prometheus-fastapi-instrumentator python-json-logger \
    mlflow httpx python-multipart

COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
