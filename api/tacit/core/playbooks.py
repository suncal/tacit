"""Persisting mined patterns as playbooks, preserving stage and stats across re-mines."""
from __future__ import annotations

from sqlalchemy import select

from .. import models as M
from ..db import session
from .audit import audit
from .events import as_dict
from .ids import new_id
from .mining import mine


def signature(pb: dict) -> tuple:
    t = pb["trigger"]
    if t.get("mode") == "reply":
        return (pb["actor"], pb["system"], "reply", tuple(sorted(t.get("keywords") or [])), t.get("target", ""))
    return (pb["actor"], pb["system"], "schedule", (t.get("cadence") or {}).get("kind"), t.get("target", ""))


def name_jobs(db, brain, playbooks: list, force: bool = False) -> int:
    """A mined name like 'Answer "invoice" threads in #billing' is honest but mechanical. With a model,
    the jobs get named the way the team would name them — once, at mining time."""
    if not getattr(brain, "is_llm", False):
        return 0
    todo = [p for p in playbooks if force or not p.summary]
    if not todo:
        return 0
    payload = [{"id": p.id, "actor": p.actor, "system": p.system, "evidence_count": p.evidence_count,
                "trigger": p.trigger, "examples": (p.examples or [])[:3]} for p in todo[:20]]
    try:
        named = brain.describe(payload)
    except Exception:
        import logging
        logging.getLogger("tacit.playbooks").warning("naming failed", exc_info=True)
        return 0
    n = 0
    for p in todo:
        row = named.get(p.id)
        if row:
            p.name, p.summary = row["name"] or p.name, row["summary"]
            n += 1
    return n


def remine(by: str = "console", brain=None) -> dict:
    with session() as db:
        events = [as_dict(e) for e in db.scalars(select(M.Event).order_by(M.Event.ts))]
        found = mine(events)
        existing = {signature({"actor": p.actor, "system": p.system, "trigger": p.trigger}): p for p in db.scalars(select(M.Playbook))}
        created, updated = 0, 0
        for f in found:
            sig = signature(f)
            p = existing.get(sig)
            if p:
                p.name, p.evidence_count, p.consistency, p.median_latency_s, p.examples = f["name"], f["evidence_count"], f["consistency"], f["median_latency_s"], f["examples"]
                p.response = {**p.response, "template": f["response"]["template"]}
                updated += 1
            else:
                db.add(M.Playbook(id=new_id("pb"), name=f["name"], system=f["system"], actor=f["actor"], stage="candidate",
                                  trigger=f["trigger"], response=f["response"], evidence_count=f["evidence_count"],
                                  consistency=f["consistency"], median_latency_s=f["median_latency_s"], examples=f["examples"]))
                created += 1
        db.flush()
        named = name_jobs(db, brain, list(db.scalars(select(M.Playbook).where(M.Playbook.stage != "retired")))) if brain else 0
        from .oversight import regrade
        regraded = regrade(db, None)
        audit(db, by, "playbooks.mine", "", {"events": len(events), "found": len(found), "created": created, "updated": updated, "agent_actions_regraded": regraded, "named": named})
    return {"events": len(events), "found": len(found), "created": created, "updated": updated, "agent_actions_regraded": regraded, "named": named}


def public(pb: M.Playbook, shadow) -> dict:
    s = shadow.summary(pb)
    return {"id": pb.id, "name": pb.name, "summary": pb.summary, "system": pb.system, "actor": pb.actor, "stage": pb.stage, "trigger": pb.trigger,
            "response": pb.response, "evidence_count": pb.evidence_count, "consistency": pb.consistency,
            "median_latency_s": pb.median_latency_s, "examples": pb.examples, "created_at": pb.created_at,
            "stage_changed_at": pb.stage_changed_at, "stage_history": pb.stage_history, "drafts_total": pb.drafts_total, **s}
