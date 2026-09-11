"""Schedules, an event bus, and the background loop that runs automations + shadow housekeeping."""
from __future__ import annotations

import datetime as dt
import fnmatch
import json
import logging
import re
import threading
import time

from sqlalchemy import select

from .. import models as M
from ..db import session
from .audit import audit

log = logging.getLogger("tacit.scheduler")
DOW = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def parse_schedule(text: str) -> dict:
    t = (text or "").strip().lower()
    m = re.match(r"^every\s+(\d+)\s*(m|min|minutes?|h|hours?|d|days?)$", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)[0]
        return {"kind": "interval", "seconds": n * {"m": 60, "h": 3600, "d": 86400}[unit], "human": f"every {text.split(None, 1)[1]}"}
    m = re.match(r"^(?:daily|every day)(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", t)
    if m:
        h, mi = _hm(m)
        return {"kind": "daily", "hour": h, "minute": mi, "human": f"daily at {h:02d}:{mi:02d}"}
    m = re.match(r"^(?:weekly|every)\s+([a-z]{3})[a-z]*(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", t)
    if m and m.group(1) in DOW:
        h, mi = _hm(m, 2)
        return {"kind": "weekly", "dow": DOW[m.group(1)], "hour": h, "minute": mi, "human": f"every {m.group(1)} at {h:02d}:{mi:02d}"}
    m = re.match(r"^on\s+([\w.:*-]+)$", t)
    if m:
        return {"kind": "event", "event": m.group(1), "human": f"on {m.group(1)}"}
    raise ValueError(f"unrecognised schedule {text!r} — try 'every 30m', 'daily 09:00', 'weekly mon 09:00', 'on github.pr.opened'")


def _hm(m, i=1):
    h, mi, ap = int(m.group(i)), int(m.group(i + 1) or 0), m.group(i + 2)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return h, mi


def compute_next(trig: dict, after: float | None = None):
    after = after or time.time()
    k = trig.get("kind")
    if k == "interval":
        return after + trig["seconds"]
    if k in ("daily", "weekly"):
        base = dt.datetime.fromtimestamp(after)
        cand = base.replace(hour=trig["hour"], minute=trig.get("minute", 0), second=0, microsecond=0)
        if k == "daily":
            if cand <= base:
                cand += dt.timedelta(days=1)
        else:
            cand += dt.timedelta(days=(trig["dow"] - cand.weekday()) % 7)
            if cand <= base:
                cand += dt.timedelta(days=7)
        return cand.timestamp()
    return None


class Bus:
    """Routes named events to event-triggered automations and to the shadow engine."""
    def __init__(self, app):
        self.app = app

    def emit(self, event: str, payload: dict | None = None) -> int:
        n = 0
        with session() as db:
            for a in db.scalars(select(M.Automation).where(M.Automation.enabled == True)):  # noqa: E712
                t = a.trigger
                if t.get("kind") == "event" and fnmatch.fnmatch(event, t.get("event", "")):
                    threading.Thread(target=run_automation, args=(self.app, a.id, payload, event), daemon=True).start()
                    n += 1
            audit(db, "bus", "event", event, {"triggered": n, "payload": _short(payload)})
        return n


def _short(p):
    try:
        s = json.dumps(p or {}, default=str)
    except Exception:
        s = str(p)
    return s[:1000]


def run_automation(app, automation_id: str, payload=None, event=None):
    with session() as db:
        a = db.get(M.Automation, automation_id)
        if not a:
            return None
        a.last_run_at = time.time(); a.last_status = "running"
        name, prompt, trig = a.name, a.prompt, a.trigger
    ctx = f"event: {event}\npayload: {_short(payload)}" if payload is not None else None
    r = app.agent.run(f"automation:{name}", f"automation:{name}", prompt, context=ctx)
    with session() as db:
        a = db.get(M.Automation, automation_id)
        if a:
            a.last_status = r["status"]; a.next_run_at = compute_next(trig)
    return r


class Scheduler(threading.Thread):
    def __init__(self, app, tick: int = 15):
        super().__init__(daemon=True, name="tacit-scheduler")
        self.app, self.tick, self.stop = app, tick, threading.Event()

    def run(self):
        while not self.stop.is_set():
            try:
                self.once()
            except Exception as e:  # never die
                log.exception("scheduler tick failed: %s", e)
            self.stop.wait(self.tick)

    def once(self):
        t = time.time()
        due = []
        with session() as db:
            for a in db.scalars(select(M.Automation).where(M.Automation.enabled == True)):  # noqa: E712
                if a.next_run_at and a.next_run_at <= t:
                    a.next_run_at = compute_next(a.trigger, t)   # claim first: a slow run must not double-fire
                    due.append(a.id)
        for aid in due:
            run_automation(self.app, aid)
        self.app.shadow.expire_stale()
        from .people import expire_covers
        with session() as db:
            expire_covers(db, self.app)
