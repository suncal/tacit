"""Inbound push. Signature-checked where the platform supports it; everything else becomes a named event."""
from __future__ import annotations

import hashlib
import hmac
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from ..core.events import ingest
from .deps import get_app

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github")
async def github(request: Request, app=Depends(get_app)):
    raw = await request.body()
    secret = app.settings.github_webhook_secret
    if secret:
        sig = request.headers.get("X-Hub-Signature-256", "")
        want = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, want):
            raise HTTPException(401, "bad signature")
    data = await request.json()
    ev = request.headers.get("X-GitHub-Event", "unknown")
    action = data.get("action", "")
    name = f"github.{ev.replace('issues', 'issue').replace('pull_request', 'pr')}" + (f".{action}" if action else "")
    n = app.bus.emit(name, {k: data.get(k) for k in ("action", "repository", "issue", "pull_request", "comment") if k in data})
    if ev in ("issue_comment", "issues") and data.get("issue"):
        repo = data["repository"]["full_name"]; num = data["issue"]["number"]
        c = data.get("comment") or data["issue"]
        body = c.get("body") or ""
        author = c["user"]["login"]
        eid = ingest(app, "github", "comment" if data.get("comment") else "issue.opened", author, body, repo, f"github:{repo}#{num}",
                     meta={"repo": repo, "number": num}, external_id=f"gh:{'c' if data.get('comment') else 'i'}:{c['id']}",
                     actor_type="tacit" if author.lower() == app.settings.handle.lower() or author.endswith("[bot]") else "human")
        if eid and app.github.ok() and app.github.handle.lower() in body.lower():
            threading.Thread(target=app.github._mention, args=(repo, num, author, body), daemon=True).start()
    return {"ok": True, "event": name, "automations": n}


@router.post("/slack")
async def slack(request: Request, app=Depends(get_app)):
    raw = await request.body()
    secret = app.settings.slack_signing_secret
    if secret:
        ts = request.headers.get("X-Slack-Request-Timestamp", "0")
        if abs(time.time() - float(ts)) > 300:
            raise HTTPException(401, "stale request")
        base = f"v0:{ts}:{raw.decode()}"
        want = "v0=" + hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get("X-Slack-Signature", ""), want):
            raise HTTPException(401, "bad signature")
    data = await request.json()
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    ev = data.get("event") or {}
    if ev.get("type") in ("message", "app_mention") and not ev.get("bot_id"):
        ch, user, text, ts = ev.get("channel", ""), ev.get("user", ""), ev.get("text", ""), ev.get("ts", "")
        eid = ingest(app, "slack", "message", user, text, ch, f"slack:{ch}:{ev.get('thread_ts') or ts}", ts=float(ts or time.time()),
                     meta={"channel": ch, "ts": ts, "thread_ts": ev.get("thread_ts")}, external_id=f"slack:{ch}:{ts}")
        if eid and ev.get("type") == "app_mention" and app.slack.ok():
            threading.Thread(target=app.slack.handle_mention, args=(ch, user, text, ev.get("thread_ts") or ts), daemon=True).start()
    return {"ok": True}


@router.post("/{name}")
async def generic(name: str, request: Request, app=Depends(get_app)):
    try:
        data = await request.json()
    except Exception:
        data = {"raw": (await request.body()).decode("utf-8", "replace")[:4000]}
    n = app.bus.emit(f"webhook:{name}", data if isinstance(data, dict) else {"data": data})
    return {"ok": True, "event": f"webhook:{name}", "automations": n}
