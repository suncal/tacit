from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import Principal, current_principal
from ..core.audit import audit
from ..core.ids import new_id
from ..core.meetings import summarize
from ..core.memory import search
from ..core.scheduler import compute_next, parse_schedule, run_automation
from ..db import get_db
from .deps import get_app

router = APIRouter(tags=["work"])


# ------------------------------------------------------------------ memory
class MemoryIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    kind: str = "fact"
    tags: list[str] = Field(default_factory=list)


@router.get("/memories")
def memories(q: Optional[str] = None, limit: int = Query(200, le=2000), db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    rows = search(db, q, 50) if q else db.scalars(select(M.Memory).order_by(M.Memory.created_at.desc()).limit(limit)).all()
    return {"memories": [{"id": m.id, "kind": m.kind, "text": m.text, "tags": m.tags, "source": m.source, "created_at": m.created_at} for m in rows]}


@router.post("/memories", status_code=201)
def add_memory(body: MemoryIn, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    m = M.Memory(id=new_id("mem"), text=body.text.strip(), kind=body.kind, tags=body.tags, source=p.label)
    db.add(m); audit(db, p.label, "memory.add", m.id, {"text": body.text[:200]}); db.commit()
    return {"id": m.id}


@router.delete("/memories/{memory_id}")
def del_memory(memory_id: str, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    m = db.get(M.Memory, memory_id)
    if m:
        db.delete(m); audit(db, p.label, "memory.delete", memory_id); db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ tasks
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    detail: str = ""
    assignee: str = ""
    due: str = ""


@router.get("/tasks")
def tasks(status: str = "all", db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    q = select(M.Task).order_by(M.Task.created_at.desc())
    if status != "all":
        q = q.where(M.Task.status == status)
    return {"tasks": [{"id": t.id, "title": t.title, "detail": t.detail, "status": t.status, "assignee": t.assignee, "source": t.source, "due": t.due, "created_at": t.created_at, "done_at": t.done_at} for t in db.scalars(q)]}


@router.post("/tasks", status_code=201)
def add_task(body: TaskIn, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    t = M.Task(id=new_id("task"), source="console", **body.model_dump())
    db.add(t); audit(db, p.label, "task.create", t.id, {"title": body.title}); db.commit()
    return {"id": t.id}


@router.post("/tasks/{task_id}/status")
def task_status(task_id: str, status: str = Query(pattern="^(open|done|cancelled)$"), db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    t = db.get(M.Task, task_id)
    if not t:
        raise HTTPException(404, "no such task")
    t.status = status; t.done_at = time.time() if status == "done" else None
    audit(db, p.label, "task." + status, task_id); db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ automations
class AutomationIn(BaseModel):
    name: str = ""
    schedule: str
    prompt: str = Field(min_length=1)


def _auto(a: M.Automation) -> dict:
    return {"id": a.id, "name": a.name, "trigger": a.trigger, "prompt": a.prompt, "enabled": a.enabled, "last_run_at": a.last_run_at, "next_run_at": a.next_run_at, "last_status": a.last_status, "created_at": a.created_at}


@router.get("/automations")
def automations(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    return {"automations": [_auto(a) for a in db.scalars(select(M.Automation).order_by(M.Automation.created_at.desc()))]}


@router.post("/automations", status_code=201)
def add_automation(body: AutomationIn, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    try:
        trig = parse_schedule(body.schedule)
    except ValueError as e:
        raise HTTPException(422, str(e))
    a = M.Automation(id=new_id("auto"), name=body.name or trig["human"], trigger=trig, prompt=body.prompt, next_run_at=compute_next(trig))
    db.add(a); audit(db, p.label, "automation.create", a.id, {"trigger": trig}); db.commit()
    return _auto(a)


@router.post("/automations/{automation_id}/{action}")
def automation_action(automation_id: str, action: str, db: Session = Depends(get_db), app=Depends(get_app), p: Principal = Depends(current_principal)):
    a = db.get(M.Automation, automation_id)
    if not a:
        raise HTTPException(404, "no such automation")
    if action == "run":
        db.commit()
        return {"run": run_automation(app, automation_id)}
    if action == "toggle":
        a.enabled = not a.enabled
    elif action == "delete":
        db.delete(a)
    else:
        raise HTTPException(404, "unknown action")
    audit(db, p.label, f"automation.{action}", automation_id); db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ meetings
class MeetingIn(BaseModel):
    title: str = "Meeting"
    transcript: str = Field(min_length=1, max_length=400000)


class AcceptIn(BaseModel):
    index: int = -1


def _meeting(m: M.Meeting) -> dict:
    return {"id": m.id, "title": m.title, "notes": m.notes, "action_items": m.action_items, "created_at": m.created_at}


@router.get("/meetings")
def meetings(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    return {"meetings": [_meeting(m) for m in db.scalars(select(M.Meeting).order_by(M.Meeting.created_at.desc()))]}


@router.post("/meetings", status_code=201)
def add_meeting(body: MeetingIn, db: Session = Depends(get_db), app=Depends(get_app), p: Principal = Depends(current_principal)):
    notes, items = summarize(app.brain, body.transcript)
    m = M.Meeting(id=new_id("mtg"), title=body.title, transcript=body.transcript, notes=notes, action_items=items)
    db.add(m); audit(db, p.label, "meeting.notes", m.id, {"items": len(items)}); db.commit()
    return _meeting(m)


@router.post("/meetings/{meeting_id}/accept")
def accept(meeting_id: str, body: AcceptIn, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    m = db.get(M.Meeting, meeting_id)
    if not m:
        raise HTTPException(404, "no such meeting")
    items, created = list(m.action_items), []
    for i, it in enumerate(items):
        if (body.index == -1 or i == body.index) and not it.get("accepted"):
            t = M.Task(id=new_id("task"), title=it["title"], detail=f"From meeting: {m.title}", assignee=it.get("owner", ""), source=f"meeting:{m.id}", due=it.get("due", ""))
            db.add(t); it["accepted"] = True; it["task_id"] = t.id; created.append(t.id)
    m.action_items = items
    audit(db, p.label, "meeting.accept", m.id, {"tasks": created}); db.commit()
    return {"meeting": _meeting(m), "created": created}
