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
COPY backend/ ./backend/
COPY ui/ ./ui/
COPY scripts/ ./scripts/


RUN uv venv /app/.venv && uv pip install --no-cache -e .

# Dedicated lightweight isolated virtual environment for ML Agent code execution
RUN uv venv /app/.ml_venv && VIRTUAL_ENV=/app/.ml_venv uv pip install --no-cache \
    numpy \
    pandas \
    scipy \
    scikit-learn \
    matplotlib \
    seaborn \
    statsmodels \
    plotly \
    openpyxl

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV CSV_OUTPUT_DIR=/tmp/ml_sandbox
ENV ML_VENV_PYTHON=/app/.ml_venv/bin/python

RUN mkdir -p /tmp/ml_sandbox


CMD ["python", "-m", "backend"]
