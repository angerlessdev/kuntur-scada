# syntax=docker/dockerfile:1
# Kuntur SCADA API. Build from the repository root: docker build -f backend/Dockerfile .

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first: this layer is reused until the lockfile changes
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/README.md backend/
COPY simulator/pyproject.toml simulator/README.md simulator/
RUN uv sync --frozen --no-dev --package kuntur --no-install-workspace

COPY backend/src backend/src
RUN uv sync --frozen --no-dev --package kuntur --no-editable

FROM python:3.12-slim
RUN useradd --system --uid 10001 --no-create-home kuntur
COPY --from=build /app/.venv /app/.venv
COPY config /app/config
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    KUNTUR_HOST=0.0.0.0 \
    KUNTUR_FLEET_FILE=/app/config/fleet.json
WORKDIR /app
USER kuntur
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
CMD ["kuntur-api"]
