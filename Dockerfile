FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml README.md ./
COPY shared/ ./shared/
COPY agents/ ./agents/

RUN uv venv /app/.venv && uv pip install --no-cache -e .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV CSV_OUTPUT_DIR=/app/output

RUN mkdir -p /app/output

CMD ["python", "-m", "agents.db_agent.main"]
