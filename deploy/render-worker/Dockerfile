# syntax=docker/dockerfile:1.7
# Render worker for animated exports (ADR-0017): the backend's Python worker plus Node, the
# pre-built Remotion bundle, Chromium (Remotion's Chrome Headless Shell) and its system libraries.
# Build from the repository root:
#   docker build -f deploy/render-worker/Dockerfile -t vanshavali-render-worker .
FROM node:22-bookworm-slim AS renderer
WORKDIR /opt/renderer
COPY renderer/package.json renderer/package-lock.json ./
RUN npm ci && npx remotion browser ensure
COPY renderer/ ./
RUN npm run bundle && npm prune --omit=dev

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Chromium runtime libraries for the headless shell, and fonts for Indic scripts
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 ca-certificates \
    libnss3 libdbus-1-3 libatk1.0-0 libgbm1 libasound2 libxrandr2 libxkbcommon0 libxfixes3 \
    libxcomposite1 libxdamage1 libatk-bridge2.0-0 libpango-1.0-0 libcairo2 libcups2 \
    fonts-noto-core fonts-noto-extra \
 && rm -rf /var/lib/apt/lists/*
COPY --from=renderer /usr/local/bin/node /usr/local/bin/node
COPY --from=renderer /opt/renderer /opt/renderer
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
RUN useradd --system --uid 10001 --home /app vanshavali \
 && mkdir -p /app/var /home/vanshavali && chown -R vanshavali /app/var /home/vanshavali \
 && chown -R vanshavali /opt/renderer/node_modules/.remotion 2>/dev/null || true
USER vanshavali
ENV PATH="/app/.venv/bin:$PATH" VSH_RENDERER_DIR=/opt/renderer VSH_RENDER_BACKEND=remotion REMOTION_CONCURRENCY=2
CMD ["python", "-m", "app.cli.worker", "--queue", "render"]
