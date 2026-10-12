# Tacit — self-hosted image.
#
# Hardening choices, each deliberate:
#   * base images pinned by digest (an upstream tag moving under us cannot change what we ship)
#   * Python dependencies installed from api/requirements.lock (every transitive version pinned, hashes checked)
#   * runs as an unprivileged user (uid 10001); /data is the only writable path
#   * no compiler, no package manager cache, no .env ever copied in
#   * HEALTHCHECK on the API so an orchestrator restarts a wedged process
# Build:  docker build -t tacit .      Run:  docker run -p 4800:4800 -v tacit-data:/data --env-file .env tacit

# ---- web -------------------------------------------------------------
FROM node:22-alpine3.22@sha256:cd7807368cf24826297cbad5dca1a44972ccfd770647db52a8c7589eb4599ac8 AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- api -------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TACIT_HOST=0.0.0.0 TACIT_PORT=4800 TACIT_WEB_DIST=../web/dist TACIT_DATABASE_URL=sqlite:////data/tacit.db
RUN groupadd --gid 10001 tacit && useradd --uid 10001 --gid tacit --home-dir /app --shell /usr/sbin/nologin tacit \
 && mkdir -p /app /data && chown tacit:tacit /app /data
WORKDIR /app
COPY api/requirements.lock api/
# pip is only needed to install; the bundled copy carries its own CVEs, so upgrade it for the install and then remove it.
RUN python -m pip install --upgrade "pip>=26.2" \
 && pip install --require-hashes --no-deps -r api/requirements.lock \
 && pip uninstall -y pip setuptools wheel 2>/dev/null; rm -rf /root/.cache /usr/local/lib/python3.12/site-packages/pip* /usr/local/lib/python3.12/site-packages/setuptools* /usr/local/bin/pip*
COPY --chown=tacit:tacit api/ api/
COPY --from=web --chown=tacit:tacit /web/dist web/dist
RUN rm -f api/.env api/*.db api/*.db-* && find api -name __pycache__ -type d -exec rm -rf {} +
USER tacit
WORKDIR /app/api
VOLUME ["/data"]
EXPOSE 4800
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:4800/api/health',timeout=4)" || exit 1
CMD ["python", "-m", "tacit.cli", "serve"]
