"""Console services: the live stream, global search, the first-run guide, the digest."""
from __future__ import annotations

import asyncio
import json
import queue
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import Principal, current_principal
from ..core.live import live
from ..core.notify import digest as build_digest, send_digest
from ..db import get_db
from .deps import get_app

router = APIRouter(tags=["console"])


# ------------------------------------------------------------------ live stream
@router.get("/stream")
async def stream(request: Request, _: Principal = Depends(current_principal)):
    """Server-sent events. One line per audited fact worth watching."""
    q = live.subscribe()

    async def gen():
        yield f": connected\ndata: {json.dumps({'kind': 'hello', 'ts': time.time()})}\n\n"
        last_beat = time.time()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = q.get_nowait()
                    yield f"event: {ev['kind']}\ndata: {json.dumps(ev, default=str)}\n\n"
                    continue
                except queue.Empty:
                    pass
                if time.time() - last_beat > 20:        # keep proxies from closing the pipe
                    last_beat = time.time()
                    yield ": ping\n\n"
                await asyncio.sleep(0.25)
        finally:
            live.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


# ------------------------------------------------------------------ search
@router.get("/search")
def search(q: str = Query(min_length=1, max_length=120), db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    """One box over everything: jobs, people, supervised agents, runs, memory, tasks."""
    like = f"%{q.lower()}%"
    out: list[dict] = []

    for p in db.scalars(select(M.Playbook).where(func.lower(M.Playbook.name).like(like)).limit(8)):
        out.append({"kind": "playbook", "id": p.id, "title": p.name, "subtitle": f"{p.actor} · {p.system} · {p.stage}",
                    "to": f"/playbooks/{p.id}", "badge": p.stage})
    for a in db.scalars(select(M.Agent).where(or_(func.lower(M.Agent.name).like(like), func.lower(M.Agent.vendor).like(like), func.lower(M.Agent.handle).like(like))).limit(5)):
        out.append({"kind": "agent", "id": a.id, "title": a.name, "subtitle": f"{a.vendor or 'in-house'} · supervised", "to": "/oversight"})
    actors = db.execute(select(M.Event.actor, func.count(M.Event.id)).where(M.Event.actor_type == "human", func.lower(M.Event.actor).like(like)).group_by(M.Event.actor).limit(5)).all()
    for name, n in actors:
        out.append({"kind": "person", "id": name, "title": name, "subtitle": f"{n} observed actions", "to": "/people"})
    for r in db.scalars(select(M.Run).where(or_(func.lower(M.Run.input).like(like), func.lower(M.Run.output).like(like))).order_by(M.Run.created_at.desc()).limit(6)):
        out.append({"kind": "run", "id": r.id, "title": r.input[:90], "subtitle": f"{r.principal} · {r.status}", "to": f"/runs/{r.id}", "badge": r.status})
    for m in db.scalars(select(M.Memory).where(func.lower(M.Memory.text).like(like)).limit(5)):
        out.append({"kind": "memory", "id": m.id, "title": m.text[:110], "subtitle": "org memory", "to": "/memory"})
    for t in db.scalars(select(M.Task).where(func.lower(M.Task.title).like(like)).limit(5)):
        out.append({"kind": "task", "id": t.id, "title": t.title, "subtitle": f"{t.assignee or 'unassigned'} · {t.status}", "to": "/tasks"})
    return {"q": q, "results": out}


# ------------------------------------------------------------------ first run
@router.get("/onboarding")
def onboarding(db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    """The shortest honest path from installed to useful. Every step is checked against real state."""
    s = app.settings
    events = db.scalar(select(func.count(M.Event.id))) or 0
    playbooks = db.scalar(select(func.count(M.Playbook.id))) or 0
    scored = db.scalar(select(func.count(M.Draft.id)).where(M.Draft.status == "scored")) or 0
    watched = db.scalar(select(func.count(M.Playbook.id)).where(M.Playbook.stage.in_(("shadow", "propose", "auto")))) or 0
    agents = db.scalar(select(func.count(M.Agent.id))) or 0
    connected = [i for i in app.integrations() if i["connected"] and i["key"] in ("github", "slack", "linear")]
    steps = [
        {"id": "connect", "title": "Connect one source, read-only",
         "detail": "GitHub, Slack or Linear — or POST your own events. Tacit only needs to watch.",
         "done": bool(connected) or events > 0, "hint": ", ".join(i["name"] for i in connected) or "set TACIT_GITHUB_REPOS or TACIT_SLACK_CHANNELS", "to": "/settings"},
        {"id": "mine", "title": "Find the repeating work",
         "detail": "Cluster what your team actually does into jobs, with the evidence attached.",
         "done": playbooks > 0, "hint": f"{playbooks} job{'s' if playbooks != 1 else ''} found from {events:,} events", "to": "/playbooks", "action": "mine"},
        {"id": "backtest", "title": "See what it would have done",
         "detail": "Replay the shadow engine over history you already have. Nothing acts.",
         "done": scored > 0, "hint": f"{scored} drafts graded against real replies", "to": "/report", "action": "backtest"},
        {"id": "shadow", "title": "Put one job in shadow",
         "detail": "It drafts silently and grades itself against the owner. Costs nothing, risks nothing.",
         "done": watched > 0, "hint": f"{watched} job{'s' if watched != 1 else ''} being watched", "to": "/playbooks"},
        {"id": "oversight", "title": "Supervise an AI you already pay for",
         "detail": "Grade a vendor's agent against the same standard. Free, read-only, no vendor cooperation.",
         "done": agents > 0, "hint": f"{agents} agent{'s' if agents != 1 else ''} supervised", "to": "/oversight"},
        {"id": "brain", "title": "Give it a model",
         "detail": "Optional. The harness works without one; a model makes the drafts adapt to context.",
         "done": app.brain.is_llm, "hint": app.brain_info()["model"] if app.brain.is_llm else "set TACIT_ANTHROPIC_API_KEY", "to": "/settings"},
    ]
    if app.settings.demo_mode:                 # a visitor cannot set an env var on someone else's server
        steps = [s_ for s_ in steps if s_["id"] != "brain"]
    done = sum(1 for s_ in steps if s_["done"])
    return {"steps": steps, "done": done, "total": len(steps), "complete": done == len(steps),
            "dismissed": bool((db.get(M.Setting, "onboarding.dismissed") or M.Setting(key="", value=False)).value)}


@router.post("/onboarding/dismiss")
def dismiss_onboarding(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    row = db.get(M.Setting, "onboarding.dismissed")
    if row:
        row.value = True
    else:
        db.add(M.Setting(key="onboarding.dismissed", value=True))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ digest
@router.get("/digest")
def digest(days: int = Query(1, ge=1, le=30), app=Depends(get_app), _: Principal = Depends(current_principal)):
    return build_digest(app, days)


@router.post("/digest/send")
def digest_send(days: int = Query(1, ge=1, le=30), app=Depends(get_app), _: Principal = Depends(current_principal)):
    return {"sent": send_digest(app, days)}
