#!/bin/sh
set -e
# A fresh organisation on every boot: the demo is public and mutable, so it is meant to be thrown away.
cp -f /app/seed.db /tmp/tacit.db && chmod 664 /tmp/tacit.db
# Generated per boot — a signing key committed to a public repo would let anyone forge a session.
export TACIT_SECRET_KEY="${TACIT_SECRET_KEY:-$(python -c 'import secrets;print(secrets.token_urlsafe(32))')}"
export TACIT_PORT="${PORT:-10000}"
echo "tacit demo on :${TACIT_PORT} (demo_mode=${TACIT_DEMO_MODE}, brain=${TACIT_BRAIN_PROVIDER})"
cd /app/api
exec python -m tacit.cli serve
