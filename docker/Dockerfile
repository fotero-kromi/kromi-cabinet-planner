# The new app as one image: the built front end, the back end and the shared
# planning engine (docs/New_App_Docker.md). Built by compose.yaml:
#   docker compose up -d --build

# ---- 1. Front end: npm ci from the lock file, then the production build ----
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. The app: Python 3.12, back end + engine + the built front end -------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KROMI_FRONTEND_DIR=/app/frontend/dist
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY engine/ engine/
COPY backend/ backend/
COPY --from=frontend /build/frontend/dist frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/kromi-entrypoint
RUN chmod 0755 /usr/local/bin/kromi-entrypoint \
    && useradd --system --no-create-home --uid 10001 kromi

USER kromi
EXPOSE 8080
ENTRYPOINT ["kromi-entrypoint"]
