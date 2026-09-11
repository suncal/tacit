from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import Principal, current_principal, require_admin
from ..core.audit import audit
from ..core.backtest import backtest as run_backtest
from ..core.events import as_dict, ingest
from ..core.playbooks import public, remine
from ..core.trust import STAGES, HIT_THRESHOLD
from ..db import get_db
from .deps import get_app

router = APIRouter(tags=["learning"])


# ------------------------------------------------------------------ events
class EventIn(BaseModel):
    system: str = Field(min_length=1, max_length=30)
    kind: str = Field(min_length=1, max_length=40)
    actor: str = Field(min_length=1, max_length=120)
    text: str = ""
    target: str = ""
    thread_key: str = ""
    ts: Optional[float] = None
    meta: dict = Field(default_factory=dict)
    external_id: Optional[str] = None
    actor_type: str = "human"


@router.post("/events", status_code=201)
def post_event(body: EventIn, app=Depends(get_app), _: Principal = Depends(current_principal)):
    eid = ingest(app, **body.model_dump())
    return {"id": eid, "duplicate": eid is None}


@router.post("/events/batch", status_code=201)
def post_events(body: list[EventIn], app=Depends(get_app), _: Principal = Depends(current_principal)):
    ids = [ingest(app, **e.model_dump()) for e in body]
    return {"ingested": sum(1 for i in ids if i), "duplicates": sum(1 for i in ids if not i)}


@router.get("/events")
def events(limit: int = Query(100, le=1000), system: Optional[str] = None, actor: Optional[str] = None, thread_key: Optional[str] = None,
           db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    q = select(M.Event).order_by(M.Event.ts.desc()).limit(limit)
    if system:
        q = q.where(M.Event.system == system)
    if actor:
        q = q.where(M.Event.actor == actor)
    if thread_key:
        q = q.where(M.Event.thread_key == thread_key).order_by(M.Event.ts.asc())
    return {"events": [as_dict(e) for e in db.scalars(q)]}


@router.get("/events/stats")
def event_stats(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    rows = db.execute(select(M.Event.system, M.Event.actor, func.count(M.Event.id)).where(M.Event.actor_type == "human").group_by(M.Event.system, M.Event.actor)).all()
    return {"by_actor": [{"system": s, "actor": a, "n": n} for s, a, n in sorted(rows, key=lambda r: -r[2])]}


# ------------------------------------------------------------------ playbooks
@router.get("/playbooks")
def playbooks(stage: Optional[str] = None, db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    q = select(M.Playbook).order_by(M.Playbook.evidence_count.desc())
    if stage:
        q = q.where(M.Playbook.stage == stage)
    return {"playbooks": [public(p, app.shadow) for p in db.scalars(q)], "hit_threshold": HIT_THRESHOLD,
            "graduation": {"min_scored": app.settings.graduate_min_scored, "min_trust": app.settings.graduate_min_trust}}


@router.post("/playbooks/mine")
def mine(app=Depends(get_app), p: Principal = Depends(current_principal)):
    return remine(by=p.label)


class BacktestIn(BaseModel):
    playbook_ids: Optional[list[str]] = None
    limit_per_playbook: int = Field(40, ge=1, le=500)


@router.post("/playbooks/backtest")
def backtest(body: BacktestIn, app=Depends(get_app), _: Principal = Depends(current_principal)):
    return run_backtest(app, body.playbook_ids, body.limit_per_playbook)


@router.get("/playbooks/{playbook_id}")
def playbook(playbook_id: str, db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    pb = db.get(M.Playbook, playbook_id)
    if not pb:
        raise HTTPException(404, "no such playbook")
    drafts = db.scalars(select(M.Draft).where(M.Draft.playbook_id == pb.id).order_by(M.Draft.created_at.desc()).limit(100)).all()
    return {**public(pb, app.shadow), "drafts": [_draft(db, d) for d in drafts]}


class StageIn(BaseModel):
    stage: str = Field(pattern="^(candidate|shadow|propose|auto|retired)$")
    why: str = ""


@router.post("/playbooks/{playbook_id}/stage")
def set_stage(playbook_id: str, body: StageIn, db: Session = Depends(get_db), app=Depends(get_app), p: Principal = Depends(require_admin)):
    pb = db.get(M.Playbook, playbook_id)
    if not pb:
        raise HTTPException(404, "no such playbook")
    if body.stage == "auto" and app.shadow.summary(pb)["trust"]["trust"] < 0.5 and pb.approvals < 3:
        raise HTTPException(422, f"auto needs trust ≥ 50% or ≥3 approvals (trust is {app.shadow.summary(pb)['trust']['trust']:.0%})")
    app.shadow.set_stage(db, pb, body.stage, by=p.label, why=body.why)
    db.commit()
    return public(pb, app.shadow)


@router.delete("/playbooks/{playbook_id}")
def delete_playbook(playbook_id: str, db: Session = Depends(get_db), p: Principal = Depends(require_admin)):
    pb = db.get(M.Playbook, playbook_id)
    if pb:
        db.delete(pb); audit(db, p.label, "playbook.delete", playbook_id, {"name": pb.name}); db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ drafts
def _draft(db, d: M.Draft) -> dict:
    trig = db.get(M.Event, d.trigger_event_id)
    actual = db.get(M.Event, d.actual_event_id) if d.actual_event_id else None
    return {"id": d.id, "playbook_id": d.playbook_id, "status": d.status, "mode": d.mode, "content": d.content, "score": d.score,
            "score_detail": d.score_detail, "human_grade": d.human_grade, "run_id": d.run_id, "created_at": d.created_at, "resolved_at": d.resolved_at,
            "trigger": {"id": trig.id, "actor": trig.actor, "text": trig.text, "target": trig.target, "ts": trig.ts, "system": trig.system} if trig else None,
            "actual": {"id": actual.id, "actor": actual.actor, "text": actual.text, "ts": actual.ts} if actual else None}


@router.get("/drafts")
def drafts(status: Optional[str] = None, mode: str = "live", limit: int = Query(100, le=500), db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    q = select(M.Draft).order_by(M.Draft.created_at.desc()).limit(limit)
    if status:
        q = q.where(M.Draft.status == status)
    if mode != "all":
        q = q.where(M.Draft.mode == mode)
    out = []
    for d in db.scalars(q):
        row = _draft(db, d)
        pb = db.get(M.Playbook, d.playbook_id)
        row["playbook"] = {"id": pb.id, "name": pb.name, "stage": pb.stage, "actor": pb.actor} if pb else None
        out.append(row)
    return {"drafts": out}


class GradeIn(BaseModel):
    grade: int = Field(ge=-1, le=1)


@router.post("/drafts/{draft_id}/grade")
def grade(draft_id: str, body: GradeIn, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    """A human override: 👍 counts as a hit, 👎 as a miss — even when the text similarity said otherwise."""
    d = db.get(M.Draft, draft_id)
    if not d:
        raise HTTPException(404, "no such draft")
    pb = db.get(M.Playbook, d.playbook_id)
    was_hit = bool(d.score_detail.get("hit")) if d.status == "scored" else None
    d.human_grade = body.grade
    now_hit = body.grade > 0
    if was_hit is None:            # unscored draft: grading it scores it
        d.status, d.resolved_at, d.score = "scored", time.time(), 1.0 if now_hit else 0.0
        d.score_detail = {"hit": now_hit, "human": True}
        pb.drafts_scored += 1; pb.score_sum += d.score
        if now_hit:
            pb.drafts_hit += 1
    elif was_hit != now_hit:
        d.score_detail = {**d.score_detail, "hit": now_hit, "human": True}
        pb.drafts_hit += 1 if now_hit else -1
    audit(db, p.label, "draft.graded", pb.name, {"draft": d.id, "grade": body.grade})
    db.commit()
    return _draft(db, d)
