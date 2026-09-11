"""Backtest: run the shadow engine over history you already have. Answers 'what would it have done?'
before a single live draft exists. Scored against the real responses that already happened."""
from __future__ import annotations

import time

from sqlalchemy import select

from .. import models as M
from ..db import session
from .audit import audit
from .shadow import matches


def backtest(app, playbook_ids: list[str] | None = None, limit_per_playbook: int = 40) -> dict:
    t0 = time.time()
    report = {"playbooks": [], "started_at": t0}
    with session() as db:
        q = select(M.Playbook).where(M.Playbook.stage != "retired")
        if playbook_ids:
            q = q.where(M.Playbook.id.in_(playbook_ids))
        pbs = db.scalars(q).all()
        # clear previous backtest drafts and their contribution to the stats
        for pb in pbs:
            old = db.scalars(select(M.Draft).where(M.Draft.playbook_id == pb.id, M.Draft.mode == "backtest")).all()
            for d in old:
                if d.status == "scored" and d.score is not None:
                    pb.drafts_scored -= 1; pb.score_sum -= d.score
                    if d.score_detail.get("hit"):
                        pb.drafts_hit -= 1
                pb.drafts_total -= 1
                db.delete(d)
        db.flush()
        events = db.scalars(select(M.Event).where(M.Event.actor_type == "human").order_by(M.Event.ts)).all()
        by_thread: dict[str, list[M.Event]] = {}
        for e in events:
            by_thread.setdefault(e.thread_key, []).append(e)
        for pb in pbs:
            rows, n = [], 0
            if (pb.trigger or {}).get("mode") == "reply":
                for e in events:
                    if n >= limit_per_playbook or not matches(pb, e):
                        continue
                    # the owner's real response in this thread after the trigger
                    actual = next((x for x in by_thread[e.thread_key] if x.ts > e.ts and x.actor == pb.actor), None)
                    if not actual:
                        continue
                    d = app.shadow._draft(db, pb, e, mode="backtest")
                    dm = db.get(M.Draft, d["draft_id"])
                    s = app.shadow._score(db, dm, pb, actual)
                    rows.append({"draft_id": dm.id, "trigger": e.text[:200], "draft": dm.content.get("text", "")[:300], "actual": actual.text[:300], "score": s["score"], "hit": s["hit"]})
                    n += 1
            else:  # scheduled: each real post is compared with what we'd draft on schedule
                owner_posts = [e for e in events if e.actor == pb.actor and e.system == pb.system and e.target == (pb.response or {}).get("target")]
                for e in owner_posts[-limit_per_playbook:]:
                    pseudo = M.Event(id=e.id, system=e.system, kind="schedule", actor="clock", actor_type="human", target=e.target, thread_key=e.thread_key, text="(scheduled)", meta={}, ts=e.ts - 1)
                    d = app.shadow._draft(db, pb, pseudo, mode="backtest")
                    dm = db.get(M.Draft, d["draft_id"])
                    dm.trigger_event_id = e.id
                    s = app.shadow._score(db, dm, pb, e)
                    rows.append({"draft_id": dm.id, "trigger": "(scheduled)", "draft": dm.content.get("text", "")[:300], "actual": e.text[:300], "score": s["score"], "hit": s["hit"]})
            hits = sum(1 for r in rows if r["hit"])
            report["playbooks"].append({"id": pb.id, "name": pb.name, "stage": pb.stage, "n": len(rows), "hits": hits,
                                        "hit_rate": round(hits / len(rows), 3) if rows else 0.0,
                                        "mean_score": round(sum(r["score"] for r in rows) / len(rows), 3) if rows else 0.0,
                                        "summary": app.shadow.summary(pb), "rows": rows[:12]})
        audit(db, "backtest", "backtest.run", "", {"playbooks": len(pbs), "seconds": round(time.time() - t0, 2)})
    report["seconds"] = round(time.time() - t0, 2)
    total = sum(p["n"] for p in report["playbooks"]); hits = sum(p["hits"] for p in report["playbooks"])
    report["total"] = {"n": total, "hits": hits, "hit_rate": round(hits / total, 3) if total else 0.0}
    return report
