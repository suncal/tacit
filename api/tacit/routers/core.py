from __future__ import annotations

import json
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import Principal, current_principal, require_admin
from ..core.audit import audit
from ..core.ids import new_id
from ..core.replay import replay as do_replay
from ..core.trust import trust
from ..db import get_db
from .deps import get_app

router = APIRouter(tags=["core"])


# ------------------------------------------------------------------ overview
@router.get("/overview")
def overview(db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    day = time.time() - 86400
    pbs = db.scalars(select(M.Playbook)).all()
    by_stage = {s: 0 for s in ("candidate", "shadow", "propose", "auto", "retired")}
    for p in pbs:
        by_stage[p.stage] = by_stage.get(p.stage, 0) + 1
    scored = sum(p.drafts_scored for p in pbs); hits = sum(p.drafts_hit for p in pbs)
    recs = []
    for p in pbs:
        s = app.shadow.summary(p)
        if s["recommendation"]:
            recs.append({"playbook_id": p.id, "name": p.name, "stage": p.stage, **s["recommendation"], "trust": s["trust"]["trust"]})
    from ..core.people import returned_minutes, CONTEXT_SWITCH_MIN, WORDS_PER_MIN
    hours_saved = returned_minutes(db) / 60
    recent_scores = db.scalars(select(M.Draft).where(M.Draft.status == "scored").order_by(M.Draft.resolved_at.desc()).limit(600)).all()
    series = _series(recent_scores)
    return {
        "org": app.settings.org_name, "handle": app.settings.handle, "brain": app.brain_info(),
        "counts": {
            "events": db.scalar(select(func.count(M.Event.id))) or 0,
            "events_24h": db.scalar(select(func.count(M.Event.id)).where(M.Event.ts >= day)) or 0,
            "playbooks": by_stage, "drafts_pending": db.scalar(select(func.count(M.Draft.id)).where(M.Draft.status == "pending")) or 0,
            "approvals": db.scalar(select(func.count(M.Approval.id)).where(M.Approval.status == "pending")) or 0,
            "runs_24h": db.scalar(select(func.count(M.Run.id)).where(M.Run.created_at >= day)) or 0,
            "actions_reversible": db.scalar(select(func.count(M.Action.id)).where(M.Action.undo.isnot(None), M.Action.status == "done")) or 0,
            "memories": db.scalar(select(func.count(M.Memory.id))) or 0,
            "tasks_open": db.scalar(select(func.count(M.Task.id)).where(M.Task.status == "open")) or 0,
            "automations": db.scalar(select(func.count(M.Automation.id))) or 0,
        },
        "shadow": {"scored": scored, "hits": hits, "hit_rate": round(hits / scored, 3) if scored else 0.0, "series": series},
        "hours_returned": round(hours_saved, 1),
        "return_method": f"per executed action: words ÷ {WORDS_PER_MIN:.0f} wpm + {CONTEXT_SWITCH_MIN:.0f} min interruption cost",
        "lessons_open": db.scalar(select(func.count(M.Lesson.id)).where(M.Lesson.status == "open")) or 0,
        "recommendations": sorted(recs, key=lambda r: -r["trust"])[:6],
        "top_playbooks": [{"id": p.id, "name": p.name, "stage": p.stage, "actor": p.actor, "system": p.system, "trust": trust(p)["trust"], "scored": p.drafts_scored, "evidence": p.evidence_count}
                          for p in sorted(pbs, key=lambda p: (-trust(p)["trust"], -p.evidence_count))[:6]],
        "integrations": app.integrations(),
        "fleet": _fleet_brief(db, app),
        "billing": _billing_brief(db, app),
    }


def _fleet_brief(db: Session, app) -> dict:
    from ..core.oversight import scorecard
    cards = [scorecard(db, a, 30) for a in db.scalars(select(M.Agent))]
    graded = [c for c in cards if c["rework_rate"] is not None]
    worst = max(graded, key=lambda c: c["rework_rate"] or 0, default=None)
    return {"agents": len(cards), "actions": sum(c["actions"] for c in cards),
            "vendor_spend_usd": round(sum(c["vendor_spend_usd"] for c in cards), 2),
            "rework_rate": round(sum(c["reworked"] for c in graded) / sum(c["actions"] for c in graded), 3) if graded and sum(c["actions"] for c in graded) else None,
            "worst": {"name": worst["agent"]["name"], "rework_rate": worst["rework_rate"], "cost_per_landed_action_usd": worst["cost_per_landed_action_usd"]} if worst else None}


def _billing_brief(db: Session, app) -> dict:
    from ..core.ledger import summary as ledger_summary
    l = ledger_summary(db, app.settings, 30)
    return {k: l[k] for k in ("verified", "disputed", "pending", "amount_usd", "credited_usd", "hours_saved", "value_usd", "roi", "seat_equivalent_usd")}


def _series(drafts):
    """Mean draft score over time. Weekly buckets when the history is long, daily when it's fresh."""
    import datetime as dt
    if not drafts:
        return []
    ts = [d.resolved_at or d.created_at for d in drafts]
    weekly = (max(ts) - min(ts)) > 21 * 86400
    buckets: dict[str, list[float]] = {}
    for d in drafts:
        t = dt.datetime.fromtimestamp(d.resolved_at or d.created_at)
        if weekly:
            t = t - dt.timedelta(days=t.weekday())
        buckets.setdefault(t.strftime("%Y-%m-%d"), []).append(d.score or 0)
    out = [{"key": k, "day": dt.datetime.strptime(k, "%Y-%m-%d").strftime("%b %d"), "score": round(sum(v) / len(v), 3), "n": len(v)} for k, v in buckets.items()]
    return sorted(out, key=lambda x: x["key"])[-16:]


# ------------------------------------------------------------------ chat + runs
class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    channel: str = "console"


@router.post("/chat")
def chat(body: ChatIn, app=Depends(get_app), p: Principal = Depends(current_principal)):
    return {"run": app.agent.run(body.channel, p.label, body.text)}


@router.get("/runs")
def runs(limit: int = Query(50, le=500), status: Optional[str] = None, db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    q = select(M.Run).order_by(M.Run.created_at.desc()).limit(limit)
    if status:
        q = q.where(M.Run.status == status)
    return {"runs": [app.agent.public(r) for r in db.scalars(q)]}


@router.get("/runs/{run_id}")
def run(run_id: str, db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    r = db.get(M.Run, run_id)
    if not r:
        raise HTTPException(404, "no such run")
    out = app.agent.public(r)
    out["messages"] = r.messages
    return out


@router.post("/runs/{run_id}/undo")
def undo(run_id: str, app=Depends(get_app), p: Principal = Depends(current_principal)):
    try:
        return app.agent.undo_run(run_id, by=p.label)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/runs/{run_id}/replay")
def replay(run_id: str, app=Depends(get_app), p: Principal = Depends(current_principal)):
    try:
        return do_replay(app, run_id, by=p.label)
    except ValueError as e:
        raise HTTPException(404, str(e))


# ------------------------------------------------------------------ approvals
class DecideIn(BaseModel):
    approve: bool


@router.get("/approvals")
def approvals(status: str = "pending", db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    q = select(M.Approval).order_by(M.Approval.created_at.desc()).limit(200)
    if status != "all":
        q = q.where(M.Approval.status == status)
    out = []
    for a in db.scalars(q):
        pb = db.get(M.Playbook, a.playbook_id) if a.playbook_id else None
        run = db.get(M.Run, a.run_id)
        d = db.get(M.Draft, run.draft_id) if run and run.draft_id else None
        out.append({"id": a.id, "run_id": a.run_id, "tool": a.tool, "args": a.args, "preview": a.preview, "principal": a.principal, "reason": a.reason,
                    "escalated": a.principal.startswith("playbook-escalated:"), "confidence": (d.content or {}).get("confidence") if d else None,
                    "status": a.status, "created_at": a.created_at, "decided_at": a.decided_at, "decided_by": a.decided_by,
                    "playbook": {"id": pb.id, "name": pb.name, "stage": pb.stage, "trust": trust(pb)["trust"]} if pb else None})
    return {"approvals": out}


@router.post("/approvals/{approval_id}/decide")
def decide(approval_id: str, body: DecideIn, app=Depends(get_app), p: Principal = Depends(current_principal)):
    r = app.agent.decide_approval(approval_id, body.approve, by=p.label)
    if r is None:
        raise HTTPException(404, "no pending approval with that id")
    return {"run": r}


# ------------------------------------------------------------------ tools / integrations / policies / budgets
@router.get("/tools")
def tools(app=Depends(get_app), _: Principal = Depends(current_principal)):
    return {"tools": [t.public() for t in app.registry.all()]}


@router.get("/integrations")
def integrations(app=Depends(get_app), _: Principal = Depends(current_principal)):
    return {"integrations": app.integrations(), "brain": app.brain_info()}


class PolicyIn(BaseModel):
    principal: str = "*"
    tool: str = "*"
    decision: str = Field(pattern="^(allow|ask|deny)$")
    note: str = ""


@router.get("/policies")
def policies(db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    return {"policies": [{"id": r.id, "principal": r.principal, "tool": r.tool, "decision": r.decision, "note": r.note, "created_at": r.created_at} for r in app.policy.rules(db)], "defaults": app.policy.defaults}


@router.post("/policies")
def add_policy(body: PolicyIn, db: Session = Depends(get_db), p: Principal = Depends(require_admin)):
    r = M.Policy(id=new_id("pol"), **body.model_dump())
    db.add(r); audit(db, p.label, "policy.create", r.id, body.model_dump()); db.commit()
    return {"id": r.id}


@router.delete("/policies/{policy_id}")
def del_policy(policy_id: str, db: Session = Depends(get_db), p: Principal = Depends(require_admin)):
    r = db.get(M.Policy, policy_id)
    if r:
        db.delete(r); audit(db, p.label, "policy.delete", policy_id); db.commit()
    return {"ok": True}


class BudgetIn(BaseModel):
    scope: str
    max_writes_per_hour: int = Field(20, ge=0)
    max_usd_per_day: float = Field(5.0, ge=0)
    note: str = ""


@router.get("/budgets")
def budgets(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    return {"budgets": [{"id": b.id, "scope": b.scope, "max_writes_per_hour": b.max_writes_per_hour, "max_usd_per_day": b.max_usd_per_day, "note": b.note} for b in db.scalars(select(M.Budget))]}


@router.post("/budgets")
def add_budget(body: BudgetIn, db: Session = Depends(get_db), p: Principal = Depends(require_admin)):
    b = M.Budget(id=new_id("bud"), **body.model_dump())
    db.add(b); audit(db, p.label, "budget.create", b.id, body.model_dump()); db.commit()
    return {"id": b.id}


@router.delete("/budgets/{budget_id}")
def del_budget(budget_id: str, db: Session = Depends(get_db), p: Principal = Depends(require_admin)):
    b = db.get(M.Budget, budget_id)
    if b:
        db.delete(b); audit(db, p.label, "budget.delete", budget_id); db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ audit + export
@router.get("/audit")
def audit_list(limit: int = Query(200, le=2000), actor: Optional[str] = None, action: Optional[str] = None, db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    q = select(M.AuditEvent).order_by(M.AuditEvent.id.desc()).limit(limit)
    if actor:
        q = q.where(M.AuditEvent.actor.like(f"%{actor}%"))
    if action:
        q = q.where(M.AuditEvent.action.like(f"{action}%"))
    return {"events": [{"id": e.id, "ts": e.ts, "actor": e.actor, "action": e.action, "target": e.target, "detail": e.detail, "ok": e.ok} for e in db.scalars(q)]}


@router.get("/audit/export")
def audit_export(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    def gen():
        for e in db.scalars(select(M.AuditEvent).order_by(M.AuditEvent.id)):
            yield json.dumps({"id": e.id, "ts": e.ts, "actor": e.actor, "action": e.action, "target": e.target, "detail": e.detail, "ok": e.ok}, default=str) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson", headers={"Content-Disposition": "attachment; filename=tacit-audit.jsonl"})


@router.get("/export")
def export_all(db: Session = Depends(get_db), _: Principal = Depends(require_admin)):
    """Everything, as JSON. Leaving must be one click."""
    out: dict[str, Any] = {}
    for name, model in (("events", M.Event), ("playbooks", M.Playbook), ("drafts", M.Draft), ("runs", M.Run), ("actions", M.Action), ("approvals", M.Approval),
                        ("memories", M.Memory), ("tasks", M.Task), ("automations", M.Automation), ("meetings", M.Meeting), ("policies", M.Policy), ("budgets", M.Budget), ("audit", M.AuditEvent)):
        out[name] = [{c.name: getattr(r, c.name) for c in model.__table__.columns} for r in db.scalars(select(model))]
    return out
