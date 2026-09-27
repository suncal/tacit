"""Getting a human's attention.

An approval nobody sees is worse than no approval at all: the job stalls and the team decides the AI
doesn't work. Tacit pings where the work already happens, and chases once if nobody answers.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from sqlalchemy import select

from .. import models as M
from .audit import audit

log = logging.getLogger("tacit.notify")


def _post_webhook(url: str, payload: dict) -> bool:
    try:
        r = httpx.post(url, json=payload, timeout=15)
        return r.status_code < 400
    except Exception as e:
        log.warning("webhook failed: %s", e)
        return False


def approval_pending(app, db, approval: M.Approval, reminder: bool = False) -> bool:
    """Tell someone an action is waiting. Returns True if a channel accepted it."""
    s = app.settings
    pb = db.get(M.Playbook, approval.playbook_id) if approval.playbook_id else None
    what = pb.name if pb else approval.tool
    summary = (approval.preview or {}).get("summary") or approval.tool
    url = f"{s.public_url or f'http://{s.host}:{s.port}'}/inbox"
    lead = "Still waiting" if reminder else "Needs a human"
    text = f"*{lead}:* {what}\n{summary}\n<{url}|Review it in Tacit>"
    sent = False
    if s.notify_slack_channel and app.slack.ok():
        try:
            app.slack.call("chat.postMessage", channel=s.notify_slack_channel, text=text)
            sent = True
        except Exception as e:
            log.warning("slack notify failed: %s", e)
    if s.notify_webhook:
        sent = _post_webhook(s.notify_webhook, {
            "event": "approval.pending", "reminder": reminder, "approval_id": approval.id,
            "playbook": what, "summary": summary, "principal": approval.principal, "url": url,
            "preview": approval.preview, "args": approval.args,
        }) or sent
    if sent:
        audit(db, "notify", "notify.sent", what, {"approval": approval.id, "reminder": reminder})
    return sent


def chase_stale_approvals(app) -> int:
    """One reminder per approval, once it has sat longer than the team said it should."""
    from ..db import session
    s = app.settings
    if not (s.notify_slack_channel or s.notify_webhook) or not s.notify_after_minutes:
        return 0
    cutoff = time.time() - s.notify_after_minutes * 60
    n = 0
    with session() as db:
        for a in db.scalars(select(M.Approval).where(M.Approval.status == "pending", M.Approval.created_at <= cutoff)):
            if (a.preview or {}).get("_reminded"):
                continue
            if approval_pending(app, db, a, reminder=True):
                a.preview = {**(a.preview or {}), "_reminded": True}
                n += 1
    return n


def digest(app, days: int = 1) -> dict:
    """What happened, in the words a manager would use. Posted by an automation or fetched by API."""
    from ..db import session
    from .ledger import summary as ledger_summary
    from .oversight import fleet
    with session() as db:
        since = time.time() - days * 86400
        acted = db.scalars(select(M.Action).where(M.Action.ts >= since)).all()
        approvals = db.scalars(select(M.Approval).where(M.Approval.created_at >= since)).all()
        pending = [a for a in db.scalars(select(M.Approval).where(M.Approval.status == "pending"))]
        lessons = db.scalars(select(M.Lesson).where(M.Lesson.status == "open")).all()
        led = ledger_summary(db, app.settings, days)
        fl = fleet(db, app, days)
        lines = [
            f"{len(acted)} action{'s' if len(acted) != 1 else ''} taken, {sum(1 for a in acted if a.status == 'undone')} reversed by a human.",
            f"{sum(1 for a in approvals if a.status == 'approved')} approved, {sum(1 for a in approvals if a.status == 'denied')} refused, {len(pending)} still waiting.",
            f"${led['amount_usd']:.2f} of verified work; ${led['credited_usd']:.2f} credited back.",
        ]
        worst = max((c for c in fl["agents"] if c["rework_rate"] is not None), key=lambda c: c["rework_rate"], default=None)
        if worst:
            lines.append(f"{worst['agent']['name']} needed a human after {worst['rework_rate']:.0%} of its actions.")
        if lessons:
            lines.append(f"{len(lessons)} correction{'s' if len(lessons) != 1 else ''} waiting for someone to explain the rule.")
        return {"days": days, "lines": lines, "pending_approvals": len(pending), "open_lessons": len(lessons),
                "text": f"*Tacit — last {days} day{'s' if days != 1 else ''}*\n" + "\n".join(f"• {l}" for l in lines)}


def send_digest(app, days: int = 1) -> bool:
    s = app.settings
    d = digest(app, days)
    sent = False
    if s.notify_slack_channel and app.slack.ok():
        try:
            app.slack.call("chat.postMessage", channel=s.notify_slack_channel, text=d["text"])
            sent = True
        except Exception as e:
            log.warning("digest slack failed: %s", e)
    if s.notify_webhook:
        sent = _post_webhook(s.notify_webhook, {"event": "digest", **d}) or sent
    return sent
