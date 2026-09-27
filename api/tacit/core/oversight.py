"""Supervision of agents you did not build.

Every company now pays two or three AI vendors and has no way to tell whether any of them did the job the
way the company would have. Vendors grade themselves: "resolved" means the conversation ended.

Tacit already holds the only ground truth that matters — what your own people do. So it can grade anyone's
agent against your standard, and measure the number no vendor reports: how often a human had to step in
afterwards. Point it at Sierra, Fin, Copilot or a homegrown bot; their actions arrive through the same
event API as everything else.
"""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import func, select

from .. import models as M
from . import text as T
from .audit import audit
from .ids import new_id
from .shadow import matches

REWORK_WINDOW_S = 6 * 3600
CONFORMANT_AT = 0.5


def _conformance(pb: M.Playbook, trigger: M.Event, actual: str, app=None) -> tuple[Optional[float], str, dict]:
    """How close is this to what your team would have said? Compared with the job's usual reply and with the
    closest real example of this situation. A vendor that paraphrases correctly should not be marked down, so
    when a model is available it judges substance and the word overlap becomes the fallback."""
    cands = [pb.response.get("template", "")] + [e.get("response", "") for e in (pb.examples or [])]
    ts = T.shingles(trigger.text or "")
    best_ex = max((e for e in (pb.examples or []) if e.get("trigger")), key=lambda e: T.jaccard(ts, T.shingles(e["trigger"])), default=None)
    if best_ex:
        cands.append(best_ex.get("response", ""))
    scored = [(T.similarity(actual, c), c) for c in cands if c]
    if not scored:
        return None, "", {}
    sim, expected = max(scored, key=lambda x: x[0])
    if app is not None and app.settings.judge_enabled and app.brain.is_llm:
        try:
            v = app.brain.judge({"name": pb.name, "actor": pb.actor, "judge_model": app.settings.judge_model},
                                trigger.text or "", actual, expected)
            if v:
                return v["score"], expected, {"graded_by": "model", "similarity": round(sim, 4), "why": v["why"], "equivalent": v["equivalent"]}
        except Exception:
            import logging
            logging.getLogger("tacit.oversight").warning("judge failed", exc_info=True)
    return round(sim, 4), expected, {"graded_by": "overlap", "similarity": round(sim, 4)}


def agent_for(db, handle: str) -> Optional[M.Agent]:
    return db.scalars(select(M.Agent).where(M.Agent.handle == handle)).first()


def on_agent_event(db, app, event: M.Event) -> Optional[dict]:
    """A supervised agent acted. Grade it against the standard Tacit learned from your humans."""
    agent = agent_for(db, event.actor)
    if not agent:
        return None
    trigger = db.scalars(select(M.Event).where(M.Event.thread_key == event.thread_key, M.Event.ts < event.ts,
                                               M.Event.actor_type == "human").order_by(M.Event.ts.desc()).limit(1)).first()
    pb, expected, conformance = None, "", None
    if trigger is not None:
        pb = next((p for p in db.scalars(select(M.Playbook).where(M.Playbook.system == event.system, M.Playbook.stage != "retired"))
                   if matches(p, trigger)), None)
    detail = {}
    if pb is not None:
        conformance, expected, detail = _conformance(pb, trigger, event.text or "", app)
    a = M.AgentAction(id=new_id("aa"), agent_id=agent.id, event_id=event.id,
                      playbook_id=pb.id if pb else None, trigger_event_id=trigger.id if trigger else None,
                      conformance=conformance, expected=expected[:4000], actual=(event.text or "")[:4000],
                      detail=detail, verdict="pending", ts=event.ts)
    db.add(a)
    audit(db, f"agent:{agent.handle}", "agent.action", agent.name,
          {"event": event.id, "playbook": pb.name if pb else None, "conformance": conformance})
    return {"agent_action_id": a.id, "conformance": conformance, "playbook": pb.id if pb else None}


def on_human_event(db, event: M.Event) -> int:
    """A human acted. If a supervised agent had just acted in this thread, that is rework — the honest
    measure of whether the agent's work actually landed."""
    n = 0
    recent = db.scalars(select(M.AgentAction).join(M.Event, M.AgentAction.event_id == M.Event.id)
                        .where(M.Event.thread_key == event.thread_key, M.AgentAction.reworked == False,  # noqa: E712
                               M.AgentAction.ts < event.ts, M.AgentAction.ts > event.ts - REWORK_WINDOW_S)).all()
    for a in recent:
        a.reworked, a.rework_event_id, a.rework_by = True, event.id, event.actor
        a.verdict, a.settled_at = "reworked", time.time()
        agent = db.get(M.Agent, a.agent_id)
        audit(db, f"agent:{agent.handle if agent else a.agent_id}", "agent.reworked", agent.name if agent else "",
              {"agent_action": a.id, "by": event.actor})
        n += 1
    return n


def regrade(db, app, force: bool = False) -> int:
    """Grade agent actions against the standard as it is now. Runs after mining, so actions taken before a
    job was learned — or before the vendor was registered — are scored retroactively against your humans."""
    q = select(M.AgentAction)
    if not force:
        q = q.where(M.AgentAction.conformance.is_(None))
    pbs = db.scalars(select(M.Playbook).where(M.Playbook.stage != "retired")).all()
    n = 0
    for a in db.scalars(q):
        ev = db.get(M.Event, a.event_id)
        if ev is None:
            continue
        trig = db.get(M.Event, a.trigger_event_id) if a.trigger_event_id else None
        if trig is None:
            trig = db.scalars(select(M.Event).where(M.Event.thread_key == ev.thread_key, M.Event.ts < ev.ts,
                                                    M.Event.actor_type == "human").order_by(M.Event.ts.desc()).limit(1)).first()
            if trig is not None:
                a.trigger_event_id = trig.id
        if trig is None:
            continue
        pb = next((p for p in pbs if p.system == ev.system and matches(p, trig)), None)
        if pb is None:
            continue
        conf, expected, detail = _conformance(pb, trig, ev.text or "", app)
        if conf is None:
            continue
        a.playbook_id, a.conformance, a.expected, a.detail = pb.id, conf, expected[:4000], detail
        if a.verdict in ("pending", "unmatched") and not a.reworked:
            a.verdict = "conformant" if conf >= CONFORMANT_AT else "off-standard"
        n += 1
    if n:
        audit(db, "oversight", "agent.regraded", "", {"actions": n})
    return n


def settle(db, now: Optional[float] = None) -> int:
    """Nobody stepped in inside the rework window → the agent's action stands. Grade it on conformance."""
    now = now or time.time()
    n = 0
    for a in db.scalars(select(M.AgentAction).where(M.AgentAction.verdict == "pending")):
        if a.ts + REWORK_WINDOW_S > now:
            continue
        a.verdict = "conformant" if (a.conformance or 0) >= CONFORMANT_AT else ("off-standard" if a.conformance is not None else "unmatched")
        a.settled_at = now
        n += 1
    return n


def scorecard(db, agent: M.Agent, days: int = 30) -> dict:
    since = time.time() - days * 86400
    rows = db.scalars(select(M.AgentAction).where(M.AgentAction.agent_id == agent.id, M.AgentAction.ts >= since)).all()
    total = len(rows)
    graded = [r for r in rows if r.conformance is not None]
    reworked = [r for r in rows if r.reworked]
    conformant = [r for r in graded if not r.reworked and (r.conformance or 0) >= CONFORMANT_AT]
    spend = round(total * agent.price_per_action_usd + agent.monthly_fee_usd * (days / 30), 2)
    landed = total - len(reworked)
    return {
        "agent": {"id": agent.id, "handle": agent.handle, "name": agent.name, "vendor": agent.vendor,
                  "systems": agent.systems, "risk_tier": agent.risk_tier, "owner": agent.owner,
                  "price_per_action_usd": agent.price_per_action_usd, "monthly_fee_usd": agent.monthly_fee_usd},
        "period_days": days, "actions": total, "graded": len(graded),
        "conformance": round(sum(r.conformance or 0 for r in graded) / len(graded), 3) if graded else None,
        "conformant": len(conformant), "off_standard": len(graded) - len(conformant) - len([r for r in reworked if r.conformance is not None]),
        "reworked": len(reworked), "rework_rate": round(len(reworked) / total, 3) if total else None,
        "landed_rate": round(landed / total, 3) if total else None,
        "vendor_spend_usd": spend,
        "cost_per_landed_action_usd": round(spend / landed, 3) if landed else None,
        "unmatched": len([r for r in rows if r.conformance is None]),
        "worst": [{"id": r.id, "conformance": r.conformance, "reworked": r.reworked, "expected": r.expected[:400],
                   "actual": r.actual[:400], "rework_by": r.rework_by, "ts": r.ts, "detail": r.detail}
                  for r in sorted(graded, key=lambda r: (not r.reworked, r.conformance or 0))[:6]],
    }


def fleet(db, app, days: int = 30) -> dict:
    """Every non-human worker in the company, Tacit's own jobs included, on one page."""
    cards = [scorecard(db, a, days) for a in db.scalars(select(M.Agent))]
    since = time.time() - days * 86400
    own_actions = db.scalar(select(func.count(M.Action.id)).where(M.Action.ts >= since)) or 0
    own_undone = db.scalar(select(func.count(M.Action.id)).where(M.Action.ts >= since, M.Action.status == "undone")) or 0
    return {
        "agents": sorted(cards, key=lambda c: -(c["actions"] or 0)),
        "tacit": {"name": f"@{app.settings.handle} (this system)", "actions": own_actions,
                  "reworked": own_undone, "rework_rate": round(own_undone / own_actions, 3) if own_actions else None,
                  "governed": True},
        "totals": {"agents": len(cards), "actions": sum(c["actions"] for c in cards) + own_actions,
                   "vendor_spend_usd": round(sum(c["vendor_spend_usd"] for c in cards), 2),
                   "ungoverned_actions": sum(c["actions"] for c in cards)},
    }
