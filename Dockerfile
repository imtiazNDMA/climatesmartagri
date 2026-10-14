FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_DEV=1
WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends --yes libexpat1 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
EXPOSE 9988
CMD ["uv", "run", "uvicorn", "csa_portal.main:create_app", "--factory", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "9988"]
