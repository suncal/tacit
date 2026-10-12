# ---------------------------------------------------------------------------
# The public demo image.
#
# Two things make this different from a normal Tacit deployment, and both are
# deliberate: it carries no model credential at all, and TACIT_DEMO_MODE strips
# every tool that can reach outside the process (shell, filesystem, web fetch).
# Anyone on the internet can drive this instance, so it must not be a shell, an
# SSRF proxy, or a way to spend somebody's tokens.
# ---------------------------------------------------------------------------
FROM node:22-alpine3.22@sha256:cd7807368cf24826297cbad5dca1a44972ccfd770647db52a8c7589eb4599ac8 AS web
WORKDIR /w
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TACIT_HOST=0.0.0.0 \
    TACIT_DEMO_MODE=1 \
    TACIT_BRAIN_PROVIDER=local \
    TACIT_ORG_NAME="Northwind Labs" \
    TACIT_WEB_DIST=../web/dist \
    TACIT_DATABASE_URL=sqlite:////tmp/tacit.db
RUN groupadd --gid 10001 tacit && useradd --uid 10001 --gid tacit --home-dir /app --shell /usr/sbin/nologin tacit && mkdir -p /app && chown tacit:tacit /app
WORKDIR /app
COPY api/requirements.lock /app/requirements.lock
RUN pip install --require-hashes --no-deps -r /app/requirements.lock
COPY --chown=tacit:tacit api/ /app/api/
COPY --from=web --chown=tacit:tacit /w/dist /app/web/dist
COPY --chown=tacit:tacit demo/seed.db /app/seed.db
COPY --chown=tacit:tacit demo/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && rm -f /app/api/.env /app/api/*.db /app/api/*.db-* && find /app/api -name __pycache__ -type d -exec rm -rf {} +
USER tacit
EXPOSE 10000
CMD ["/app/entrypoint.sh"]
