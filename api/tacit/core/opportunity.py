"""The Day-One report.

The thing that stops AI pilots is that nobody can say what the AI would do before it does it. Tacit can:
connect one read-only source, mine, backtest, and the first thing you see is a costed list of the repetitive
jobs your team is actually doing — and how much of it Tacit would already have handled correctly.

No write scopes are involved. Nothing acts. This is the whole pilot.
"""
from __future__ import annotations

import time

from sqlalchemy import func, select

from .. import models as M
from .backtest import backtest
from .people import minutes_for
from .playbooks import remine
from .trust import trust


def run(app, days_observed: int | None = None, by: str = "pilot") -> dict:
    from ..db import session
    t0 = time.time()
    mined = remine(by=by)
    report = backtest(app)
    with session() as db:
        span = db.execute(select(func.min(M.Event.ts), func.max(M.Event.ts)).where(M.Event.actor_type == "human")).first()
        observed_days = days_observed or (max(1.0, ((span[1] or t0) - (span[0] or t0)) / 86400) if span else 1.0)
        events = db.scalar(select(func.count(M.Event.id))) or 0
        by_pb = {p["id"]: p for p in report["playbooks"]}
        jobs, hours_year, coverable_hours = [], 0.0, 0.0
        for p in db.scalars(select(M.Playbook).where(M.Playbook.stage != "retired")):
            each = minutes_for(p.response.get("template", ""))
            per_year = p.evidence_count / observed_days * 365
            hrs = per_year * each / 60
            bt = by_pb.get(p.id, {})
            cover = bt.get("hit_rate", 0.0) or 0.0
            hours_year += hrs
            coverable_hours += hrs * cover
            jobs.append({
                "id": p.id, "name": p.name, "owner": p.actor, "system": p.system, "stage": p.stage,
                "seen": p.evidence_count, "per_year": round(per_year), "minutes_each": each,
                "hours_per_year": round(hrs, 1), "consistency": p.consistency,
                "backtest_n": bt.get("n", 0), "would_have_handled": round(cover, 3),
                "hours_recoverable": round(hrs * cover, 1),
                "value_usd": round(hrs * cover * app.settings.loaded_hourly_cost_usd),
                "trust": trust(p)["trust"],
                "why": _why(p, bt),
            })
        jobs.sort(key=lambda j: -j["hours_recoverable"])
        people = db.scalar(select(func.count(func.distinct(M.Event.actor))).where(M.Event.actor_type == "human")) or 0
        solo = [j for j in jobs if j["seen"] >= 3]
        out = {
            "generated_at": time.time(), "organisation": app.settings.org_name, "seconds": round(time.time() - t0, 2),
            "observed": {"events": events, "days": round(observed_days, 1), "people": people, "systems": _systems(db)},
            "mined": mined, "jobs": jobs,
            "totals": {
                "jobs": len(jobs), "hours_per_year": round(hours_year, 1),
                "hours_recoverable": round(coverable_hours, 1),
                "value_usd": round(coverable_hours * app.settings.loaded_hourly_cost_usd),
                "coverage": round(coverable_hours / hours_year, 3) if hours_year else 0.0,
                "backtest": report["total"],
                "verified_cost_usd": round(sum(j["per_year"] * (j["would_have_handled"] or 0) for j in jobs) * app.settings.price_per_verified_action_usd),
            },
            "bus_factor": _bus(jobs),
            "start_with": jobs[0] if jobs else None,
            "next_steps": [
                "Nothing has acted. Everything above came from reading history.",
                f"Put “{jobs[0]['name']}” into Shadow — it drafts silently and grades itself against {jobs[0]['owner']}." if jobs else "Connect a second source so patterns can form.",
                "Come back in a week: if the trust score clears the bar, promote it to Propose and approve each action with one tap.",
            ],
            "hours_note": f"Time per action = words ÷ 35 wpm + 3 min interruption cost. Value at ${app.settings.loaded_hourly_cost_usd:.0f}/hour loaded.",
        }
    return out


def _why(p: M.Playbook, bt: dict) -> str:
    if not bt.get("n"):
        return "Not enough history to backtest this one yet."
    hr = bt.get("hit_rate", 0)
    if hr >= 0.7:
        return f"{bt['hits']} of {bt['n']} past cases were drafted correctly without seeing the answer."
    if hr >= 0.4:
        return f"Partly learnable: {bt['hits']} of {bt['n']} matched. Shadow it and teach it the misses."
    return f"Only {bt['hits']} of {bt['n']} matched — the real replies depend on information Tacit cannot see yet."


def _systems(db) -> list[dict]:
    rows = db.execute(select(M.Event.system, func.count(M.Event.id)).group_by(M.Event.system)).all()
    return [{"system": s, "events": n} for s, n in sorted(rows, key=lambda r: -r[1])]


def _bus(jobs: list[dict]) -> list[dict]:
    by_owner: dict[str, dict] = {}
    for j in jobs:
        o = by_owner.setdefault(j["owner"], {"owner": j["owner"], "jobs": 0, "hours_per_year": 0.0})
        o["jobs"] += 1
        o["hours_per_year"] = round(o["hours_per_year"] + j["hours_per_year"], 1)
    return sorted(by_owner.values(), key=lambda o: -o["hours_per_year"])
