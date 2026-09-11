# ---- web -------------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- api -------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TACIT_HOST=0.0.0.0 TACIT_PORT=4800 TACIT_WEB_DIST=../web/dist TACIT_DATABASE_URL=sqlite:////data/tacit.db
COPY api/pyproject.toml api/
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" "alembic>=1.13" "pydantic[email]>=2.7" "pydantic-settings>=2.3" "httpx>=0.27" "anthropic>=1.0" "itsdangerous>=2.2" "python-multipart>=0.0.9"
COPY api/ api/
COPY --from=web /web/dist web/dist
WORKDIR /app/api
VOLUME ["/data"]
EXPOSE 4800
HEALTHCHECK --interval=30s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:4800/api/health')"
CMD ["python", "-m", "tacit.cli", "serve"]
