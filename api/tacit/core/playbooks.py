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


def remine(by: str = "console") -> dict:
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
        audit(db, by, "playbooks.mine", "", {"events": len(events), "found": len(found), "created": created, "updated": updated})
    return {"events": len(events), "found": len(found), "created": created, "updated": updated}


def public(pb: M.Playbook, shadow) -> dict:
    s = shadow.summary(pb)
    return {"id": pb.id, "name": pb.name, "system": pb.system, "actor": pb.actor, "stage": pb.stage, "trigger": pb.trigger,
            "response": pb.response, "evidence_count": pb.evidence_count, "consistency": pb.consistency,
            "median_latency_s": pb.median_latency_s, "examples": pb.examples, "created_at": pb.created_at,
            "stage_changed_at": pb.stage_changed_at, "stage_history": pb.stage_history, "drafts_total": pb.drafts_total, **s}
