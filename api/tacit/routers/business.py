"""Verified-work billing, third-party agent oversight, compliance evidence, and the Day-One pilot report."""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as M
from ..auth import Principal, current_principal, require_admin
from ..core.audit import audit
from ..core.compliance import evidence as build_evidence, seal, verify as verify_chain
from ..core.ids import new_id
from ..core.ledger import settle as settle_ledger, summary as ledger_summary
from ..core.opportunity import run as run_opportunity
from ..core.oversight import fleet, scorecard, settle as settle_agents
from ..db import get_db
from .deps import get_app

router = APIRouter(tags=["business"])


# ------------------------------------------------------------------ verified work
@router.get("/ledger")
def ledger(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    settle_ledger(db, app.settings)
    db.commit()
    return ledger_summary(db, app.settings, days)


# ------------------------------------------------------------------ supervised agents
class AgentIn(BaseModel):
    handle: str = Field(min_length=1, max_length=120, description="the actor string its events arrive under")
    name: str = Field(min_length=1, max_length=160)
    vendor: str = ""
    systems: list[str] = Field(default_factory=list)
    price_per_action_usd: float = Field(0.0, ge=0)
    monthly_fee_usd: float = Field(0.0, ge=0)
    risk_tier: str = "limited"
    owner: str = ""
    notes: str = ""


@router.get("/oversight")
def oversight(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    settle_agents(db)
    db.commit()
    return fleet(db, app, days)


@router.get("/oversight/{agent_id}")
def oversight_one(agent_id: str, days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    a = db.get(M.Agent, agent_id)
    if not a:
        raise HTTPException(404, "no such agent")
    card = scorecard(db, a, days)
    rows = db.scalars(select(M.AgentAction).where(M.AgentAction.agent_id == a.id).order_by(M.AgentAction.ts.desc()).limit(100)).all()
    card["actions_detail"] = [{"id": r.id, "conformance": r.conformance, "verdict": r.verdict, "reworked": r.reworked,
                               "rework_by": r.rework_by, "expected": r.expected, "actual": r.actual, "ts": r.ts,
                               "playbook_id": r.playbook_id, "human_grade": r.human_grade} for r in rows]
    return card


@router.post("/oversight", status_code=201)
def register_agent(body: AgentIn, db: Session = Depends(get_db), p: Principal = Depends(require_admin)):
    if db.scalars(select(M.Agent).where(M.Agent.handle == body.handle)).first():
        raise HTTPException(409, f"{body.handle} is already supervised")
    a = M.Agent(id=new_id("agt"), **body.model_dump())
    db.add(a); audit(db, p.label, "agent.registered", a.name, {"handle": a.handle, "vendor": a.vendor}); db.commit()
    return {"id": a.id, "handle": a.handle, "name": a.name}


@router.delete("/oversight/{agent_id}")
def unregister_agent(agent_id: str, db: Session = Depends(get_db), p: Principal = Depends(require_admin)):
    a = db.get(M.Agent, agent_id)
    if a:
        db.delete(a); audit(db, p.label, "agent.unregistered", a.name); db.commit()
    return {"ok": True}


class GradeIn(BaseModel):
    grade: int = Field(ge=-1, le=1)


@router.post("/oversight/actions/{action_id}/grade")
def grade_agent_action(action_id: str, body: GradeIn, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    a = db.get(M.AgentAction, action_id)
    if not a:
        raise HTTPException(404, "no such action")
    a.human_grade = body.grade
    a.verdict = "conformant" if body.grade > 0 else "off-standard"
    a.settled_at = time.time()
    audit(db, p.label, "agent.graded", a.agent_id, {"action": a.id, "grade": body.grade}); db.commit()
    return {"ok": True, "verdict": a.verdict}


# ------------------------------------------------------------------ compliance
@router.get("/compliance")
def compliance(days: int = Query(90, ge=1, le=730), db: Session = Depends(get_db), app=Depends(get_app), _: Principal = Depends(current_principal)):
    ev = build_evidence(db, app, days)
    db.commit()
    return ev


@router.get("/compliance/verify")
def compliance_verify(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    seal(db); out = verify_chain(db); db.commit()
    return out


@router.get("/compliance/export")
def compliance_export(days: int = Query(90, ge=1, le=730), db: Session = Depends(get_db), app=Depends(get_app), p: Principal = Depends(require_admin)):
    ev = build_evidence(db, app, days)
    audit(db, p.label, "compliance.export", "", {"days": days, "root": ev["log_integrity"]["root"]})
    db.commit()
    stamp = time.strftime("%Y-%m-%d")
    return JSONResponse(ev, headers={"Content-Disposition": f'attachment; filename="tacit-oversight-evidence-{stamp}.json"'})


# ------------------------------------------------------------------ day one
@router.post("/pilot/report")
def pilot_report(app=Depends(get_app), p: Principal = Depends(current_principal)):
    """Mine + backtest + cost the result. Read-only: nothing acts."""
    out = run_opportunity(app, by=p.label)
    from ..db import session
    with session() as db:
        db.add(M.Setting(key="pilot.last", value={"at": out["generated_at"], "hours": out["totals"]["hours_recoverable"]})) if not db.get(M.Setting, "pilot.last") else None
        s = db.get(M.Setting, "pilot.last")
        if s:
            s.value = {"at": out["generated_at"], "hours": out["totals"]["hours_recoverable"]}
        audit(db, p.label, "pilot.report", "", {"jobs": out["totals"]["jobs"], "hours": out["totals"]["hours_recoverable"]})
    return out


@router.get("/pilot/report")
def pilot_report_get(app=Depends(get_app), db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    return run_opportunity(app, by="console")
