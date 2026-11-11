# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-hin tesseract-ocr-eng libpq5 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# JPL DE440s ephemeris for the family calendar (ADR-0022 §1): fetched once per build and accepted
# only if it matches the pinned SHA-256; its own layer, so app changes do not download it again
COPY app/modules/calendar/ephemeris.py /tmp/ephemeris.py
RUN python /tmp/ephemeris.py fetch /app/ephemeris/de440s.bsp && rm /tmp/ephemeris.py
ENV VSH_EPHEMERIS_PATH=/app/ephemeris/de440s.bsp
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN useradd --system --uid 10001 --home /app vanshavali && mkdir -p /app/var && chown -R vanshavali /app/var
USER vanshavali
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# Proxy headers are honoured only from these addresses/CIDRs (uvicorn walks X-Forwarded-For right to
# left, skipping them). Set it to the reverse proxies directly in front of the API (nginx, the load
# balancer). Never "*": any client could then choose its own IP and dodge per-IP rate limits.
ENV FORWARDED_ALLOW_IPS="127.0.0.1,::1"
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
