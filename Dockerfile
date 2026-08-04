FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir -e ".[dev]"

ENV ENGINE_DB_PATH=/app/.engine/state.db

EXPOSE 8000

CMD ["engine", "serve"]
