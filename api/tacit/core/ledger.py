"""Verified-work accounting.

The industry sells "outcome-based" pricing where an outcome means the conversation ended. Tacit can do the
honest version, because it has ground truth: an action is billable only if a human approved it, or it ran
autonomously on a job that had earned its autonomy and no human reversed it inside the dispute window.
Work that was reversed, refused or escalated is never billable. Work a person drove themselves is not billed
at all.
"""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy import func, select

from .. import models as M
from .ids import new_id
from .people import minutes_for


def record(db, action: M.Action, run: M.Run) -> Optional[M.LedgerEntry]:
    """Open a pending line for a write Tacit performed on a job's behalf."""
    if not run.playbook_id and not run.principal.startswith("automation:"):
        return None                      # a person driving the console is not billable work
    text = action.args.get("body") or action.args.get("text") or action.args.get("content") or ""
    e = M.LedgerEntry(id=new_id("led"), action_id=action.id, run_id=run.id, playbook_id=run.playbook_id,
                      kind="action", status="pending", minutes_saved=minutes_for(text),
                      detail={"tool": action.tool, "channel": run.channel, "principal": run.principal})
    db.add(e)
    return e


def settle(db, settings, now: Optional[float] = None) -> dict:
    """Decide each pending line. Conservative by construction: when in doubt, it stays pending, and
    anything a human reversed is written off permanently."""
    now = now or time.time()
    window = settings.dispute_window_hours * 3600
    price = settings.price_per_verified_action_usd
    verified = disputed = waived = 0
    for e in db.scalars(select(M.LedgerEntry).where(M.LedgerEntry.status == "pending")):
        action = db.get(M.Action, e.action_id) if e.action_id else None
        run = db.get(M.Run, e.run_id) if e.run_id else None
        if action is None or run is None:
            e.status, e.settled_at = "waived", now
            waived += 1
            continue
        if action.status in ("undone", "undo_failed"):
            e.status, e.amount_usd, e.settled_at = "disputed", 0.0, now
            e.detail = {**e.detail, "reason": "a human reversed it"}
            disputed += 1
            continue
        approval = db.scalars(select(M.Approval).where(M.Approval.run_id == run.id, M.Approval.status == "approved")).first()
        if approval:
            e.status, e.basis, e.amount_usd, e.settled_at = "verified", "human_approved", price, now
            e.detail = {**e.detail, "approved_by": approval.decided_by}
            verified += 1
            continue
        if db.scalars(select(M.Approval).where(M.Approval.run_id == run.id, M.Approval.status == "denied")).first():
            e.status, e.amount_usd, e.settled_at = "disputed", 0.0, now
            e.detail = {**e.detail, "reason": "a human refused it"}
            disputed += 1
            continue
        if action.ts + window <= now:
            pb = db.get(M.Playbook, e.playbook_id) if e.playbook_id else None
            if pb and pb.stage == "auto":
                e.status, e.basis, e.amount_usd, e.settled_at = "verified", "undisputed_auto", price, now
                e.detail = {**e.detail, "window_hours": settings.dispute_window_hours}
                verified += 1
            else:
                e.status, e.settled_at = "waived", now
                waived += 1
    return {"verified": verified, "disputed": disputed, "waived": waived}


def summary(db, settings, days: int = 30) -> dict:
    since = time.time() - days * 86400
    rows = db.scalars(select(M.LedgerEntry).where(M.LedgerEntry.created_at >= since)).all()
    by = lambda st: [r for r in rows if r.status == st]  # noqa: E731
    verified, disputed, pending, waived = by("verified"), by("disputed"), by("pending"), by("waived")
    amount = round(sum(r.amount_usd for r in verified), 2)
    minutes = round(sum(r.minutes_saved for r in verified), 1)
    people = db.scalar(select(func.count(func.distinct(M.Event.actor))).where(M.Event.actor_type == "human")) or 1
    seat_price = settings.comparison_seat_price_usd
    return {
        "period_days": days, "price_per_verified_action_usd": settings.price_per_verified_action_usd,
        "dispute_window_hours": settings.dispute_window_hours,
        "verified": len(verified), "disputed": len(disputed), "pending": len(pending), "not_billable": len(waived),
        "amount_usd": amount, "credited_usd": round(len(disputed) * settings.price_per_verified_action_usd, 2),
        "hours_saved": round(minutes / 60, 1),
        "value_usd": round(minutes / 60 * settings.loaded_hourly_cost_usd, 2),
        "roi": round((minutes / 60 * settings.loaded_hourly_cost_usd) / amount, 1) if amount else None,
        "seat_equivalent_usd": round(people * seat_price, 2), "people": people, "seat_price_usd": seat_price,
        "by_playbook": _by_playbook(db, rows),
        "lines": [{"id": r.id, "status": r.status, "basis": r.basis, "amount_usd": r.amount_usd, "minutes_saved": r.minutes_saved,
                   "playbook_id": r.playbook_id, "run_id": r.run_id, "detail": r.detail, "created_at": r.created_at, "settled_at": r.settled_at}
                  for r in sorted(rows, key=lambda r: -r.created_at)[:200]],
    }


def _by_playbook(db, rows) -> list[dict]:
    out: dict[str, dict] = {}
    for r in rows:
        if not r.playbook_id:
            continue
        o = out.setdefault(r.playbook_id, {"playbook_id": r.playbook_id, "name": "", "verified": 0, "disputed": 0, "amount_usd": 0.0, "minutes_saved": 0.0})
        if r.status == "verified":
            o["verified"] += 1; o["amount_usd"] += r.amount_usd; o["minutes_saved"] += r.minutes_saved
        elif r.status == "disputed":
            o["disputed"] += 1
    for pid, o in out.items():
        pb = db.get(M.Playbook, pid)
        o["name"] = pb.name if pb else pid
        o["amount_usd"] = round(o["amount_usd"], 2)
        o["hours_saved"] = round(o["minutes_saved"] / 60, 1)
    return sorted(out.values(), key=lambda o: -o["amount_usd"])
