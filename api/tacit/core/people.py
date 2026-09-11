"""People & coverage: which jobs live in whose head, and what happens when they're out."""
from __future__ import annotations

import time
from collections import defaultdict

from sqlalchemy import func, select

from .. import models as M
from .audit import audit
from .ids import new_id
from .trust import trust

COVER_MIN_TRUST = 0.5
CONTEXT_SWITCH_MIN = 3.0        # minutes lost to an interruption, on top of writing
WORDS_PER_MIN = 35.0            # composing, not copy-typing


def minutes_for(text: str) -> float:
    """What a human spends on one reply: composing time + the cost of being interrupted."""
    words = len((text or "").split())
    return round(words / WORDS_PER_MIN + CONTEXT_SWITCH_MIN, 2)


def returned_minutes(db) -> float:
    """Sum over executed actions of the minutes the owner would have spent. Shown with the formula, not as magic."""
    total = 0.0
    for a in db.scalars(select(M.Action).where(M.Action.status == "done")):
        text = a.args.get("body") or a.args.get("text") or a.args.get("content") or ""
        total += minutes_for(text)
    return round(total, 1)


def people(db, app) -> list[dict]:
    pbs = db.scalars(select(M.Playbook).where(M.Playbook.stage != "retired")).all()
    by_actor: dict[str, list] = defaultdict(list)
    for p in pbs:
        by_actor[p.actor].append(p)
    counts = dict(db.execute(select(M.Event.actor, func.count(M.Event.id)).where(M.Event.actor_type == "human").group_by(M.Event.actor)).all())
    covers = {c.actor: c for c in db.scalars(select(M.Cover).where(M.Cover.status == "active"))}
    out = []
    for actor, jobs in sorted(by_actor.items(), key=lambda kv: -len(kv[1])):
        covered_ready = [p for p in jobs if p.stage in ("shadow", "propose", "auto") and trust(p)["trust"] >= COVER_MIN_TRUST or p.stage == "auto"]
        solo = [p for p in jobs if p.stage in ("candidate", "shadow")]      # only this person can do it today
        out.append({
            "actor": actor, "events": counts.get(actor, 0), "jobs": len(jobs),
            "playbooks": [{"id": p.id, "name": p.name, "stage": p.stage, "trust": trust(p)["trust"], "evidence": p.evidence_count,
                           "minutes_each": minutes_for(p.response.get("template", ""))} for p in sorted(jobs, key=lambda p: -p.evidence_count)],
            "coverable": len(covered_ready), "bus_factor_risk": len(solo),
            "weekly_minutes": round(sum(p.evidence_count / 13 * minutes_for(p.response.get("template", "")) for p in jobs), 1),
            "cover": {"id": covers[actor].id, "backup": covers[actor].backup, "until": covers[actor].until} if actor in covers else None,
        })
    return out


def start_cover(db, app, actor: str, backup: str, until: float, by: str) -> M.Cover:
    promoted = []
    for p in db.scalars(select(M.Playbook).where(M.Playbook.actor == actor, M.Playbook.stage.in_(("shadow", "propose")))):
        if p.stage == "shadow" and trust(p)["trust"] < COVER_MIN_TRUST:
            continue
        if p.stage == "shadow":
            promoted.append({"playbook_id": p.id, "from": p.stage})
            app.shadow.set_stage(db, p, "propose", by=by, why=f"cover: {actor} is out until {time.strftime('%b %d', time.localtime(until))}")
    c = M.Cover(id=new_id("cov"), actor=actor, backup=backup, until=until, promoted=promoted, created_by=by)
    db.add(c)
    audit(db, by, "cover.start", actor, {"backup": backup, "until": until, "promoted": len(promoted)})
    return c


def end_cover(db, app, cover: M.Cover, by: str = "scheduler") -> None:
    for item in cover.promoted or []:
        p = db.get(M.Playbook, item["playbook_id"])
        if p and p.stage == "propose":
            app.shadow.set_stage(db, p, item["from"], by=by, why="cover ended")
    cover.status = "ended"
    audit(db, by, "cover.end", cover.actor, {"restored": len(cover.promoted or [])})


def expire_covers(db, app) -> int:
    n = 0
    for c in db.scalars(select(M.Cover).where(M.Cover.status == "active", M.Cover.until <= time.time())):
        end_cover(db, app, c); n += 1
    return n
