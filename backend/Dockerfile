# One image per deploy: the API, its worker thread and the built frontend (D5, D36).
# Build from the repository root so the frontend is in the context:
#   docker build -f backend/Dockerfile --build-arg FRONTEND_DIR=frontend .

FROM node:22-alpine AS frontend
ARG FRONTEND_DIR=frontend
WORKDIR /src
COPY ${FRONTEND_DIR}/package.json ${FRONTEND_DIR}/package-lock.json ./
RUN npm ci
COPY ${FRONTEND_DIR}/ ./
RUN npm run build && test -f dist/index.html

FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.10.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app app
COPY backend/sql sql
COPY backend/scripts scripts
COPY --from=frontend /src/dist frontend-dist
COPY backend/deploy/entrypoint.sh /usr/local/bin/entrypoint.sh

# /state holds the compose demo's generated keys. A fresh named volume mounted there takes
# this directory's owner, so the app user can write it.
RUN useradd --system --no-create-home ghostseats && install -d -o ghostseats -m 700 /state
USER ghostseats
ENV PATH=/app/.venv/bin:$PATH \
    FRONTEND_DIST=/app/frontend-dist \
    WEB_CONCURRENCY=2 \
    LOG_FORMAT=json \
    PROMETHEUS_MULTIPROC_DIR=/tmp/ghostseats-metrics
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
# Caddy on the host terminates TLS (D57); trust its X-Forwarded-* headers.
ENTRYPOINT ["sh", "/usr/local/bin/entrypoint.sh"]
# The metrics directory is emptied on every start: samples from a previous run's processes
# would otherwise be summed into this one's. Live streams never end on their own, so shutdown
# gives open connections 6 s and then closes them; clients reconnect (D61).
CMD ["sh", "-c", "rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn app.main:build --factory --host 0.0.0.0 --port 8000 --workers \"$WEB_CONCURRENCY\" --proxy-headers --forwarded-allow-ips '*' --no-access-log --log-config app/log_config.json --timeout-graceful-shutdown 6"]
