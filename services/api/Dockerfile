FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg alembic \
    apscheduler redis aiohttp pandas numpy pyarrow pydantic \
    python-multipart python-json-logger httpx
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
