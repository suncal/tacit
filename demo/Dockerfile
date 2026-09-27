# ---------------------------------------------------------------------------
# The public demo image.
#
# Two things make this different from a normal Tacit deployment, and both are
# deliberate: it carries no model credential at all, and TACIT_DEMO_MODE strips
# every tool that can reach outside the process (shell, filesystem, web fetch).
# Anyone on the internet can drive this instance, so it must not be a shell, an
# SSRF proxy, or a way to spend somebody's tokens.
# ---------------------------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /w
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    TACIT_HOST=0.0.0.0 \
    TACIT_DEMO_MODE=1 \
    TACIT_BRAIN_PROVIDER=local \
    TACIT_ORG_NAME="Northwind Labs" \
    TACIT_WEB_DIST=../web/dist \
    TACIT_DATABASE_URL=sqlite:////tmp/tacit.db
WORKDIR /app
RUN pip install --no-cache-dir \
      "fastapi>=0.115" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" "alembic>=1.13" \
      "pydantic[email]>=2.7" "pydantic-settings>=2.3" "httpx>=0.27" "itsdangerous>=2.2" \
      "python-multipart>=0.0.9"
COPY api/ /app/api/
COPY --from=web /w/dist /app/web/dist
COPY demo/seed.db /app/seed.db
COPY demo/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && rm -f /app/api/.env
EXPOSE 10000
CMD ["/app/entrypoint.sh"]
