"""The shadow engine — Tacit's new mechanism.

For every playbook that is at least in *shadow*, each matching trigger produces a Draft: what Tacit would do.
When the playbook's owner then acts for real in the same thread, the draft is scored against that action.
No labelling. The human's real work is the ground truth. Scores roll up into a per-playbook trust score,
which drives graduation: shadow → propose (asks first) → auto (acts, reversibly).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import select

from .. import models as M
from ..db import session
from . import text as T
from .audit import audit
from .ids import new_id
from .trust import HIT_THRESHOLD, recommendation, trust

log = logging.getLogger("tacit.shadow")
ACTIVE = ("shadow", "propose", "auto")
ESCALATE_BELOW = 0.45        # auto-stage drafts with confidence under this still go to a human
LESSON_BELOW = 0.35          # a scored draft this far from the real reply asks the owner for the rule


def matches(pb: M.Playbook, e: M.Event) -> bool:
    t = pb.trigger or {}
    if t.get("mode") != "reply" or e.system != pb.system or e.actor == pb.actor or e.actor_type != "human":
        return False
    if t.get("target") and e.target and t["target"] != e.target:
        return False
    if t.get("kind") and e.kind != t["kind"] and not (t["kind"].endswith("message") and e.kind == "message"):
        return False
    kws = t.get("keywords") or []
    if not kws:
        return True
    toks = set(T.tokens(e.text))
    hits = [k for k in kws if k in toks]
    return len(hits) == len(kws) if t.get("match") == "all" else len(hits) >= max(1, len(kws) // 2)


class Shadow:
    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------------------ live path
    def on_event(self, event_id: str) -> dict:
        """Called after every human event is ingested. Scores what it resolves, drafts what it triggers."""
        out = {"scored": [], "drafted": []}
        with session() as db:
            e = db.get(M.Event, event_id)
            if not e:
                return out
            out["scored"] = self._score_pending(db, e)
            for pb in db.scalars(select(M.Playbook).where(M.Playbook.stage.in_(ACTIVE))):
                if matches(pb, e):
                    out["drafted"].append(self._draft(db, pb, e, mode="live"))
        # propose/auto drafts become runs outside the ingest transaction
        for d in out["drafted"]:
            if d.get("stage") in ("propose", "auto"):
                self._enact(d["draft_id"])
        return out

    def _score_pending(self, db, e: M.Event) -> list[dict]:
        """The owner acted in a thread where we have a pending draft → grade ourselves."""
        scored = []
        pend = db.scalars(select(M.Draft).join(M.Event, M.Draft.trigger_event_id == M.Event.id)
                          .where(M.Draft.status == "pending", M.Event.thread_key == e.thread_key)).all()
        for d in pend:
            pb = db.get(M.Playbook, d.playbook_id)
            if not pb or pb.actor != e.actor:
                continue
            scored.append(self._score(db, d, pb, e))
        return scored

    def _score(self, db, d: M.Draft, pb: M.Playbook, actual: M.Event) -> dict:
        sim = T.similarity(d.content.get("text", ""), actual.text)
        target_ok = (d.content.get("target") or "") == (actual.target or "") if d.content.get("target") else True
        score = round(min(1.0, sim + (0.05 if target_ok else -0.15)), 4)
        d.score, d.actual_event_id, d.status = score, actual.id, "scored"
        d.resolved_at = actual.ts if d.mode == "backtest" else time.time()   # backtests keep history honest
        d.score_detail = {"similarity": sim, "target_match": target_ok, "draft_tokens": len(T.tokens(d.content.get("text", ""))),
                          "actual_tokens": len(T.tokens(actual.text)), "hit": score >= HIT_THRESHOLD, "threshold": HIT_THRESHOLD}
        pb.drafts_scored += 1
        pb.score_sum += score
        if score >= HIT_THRESHOLD:
            pb.drafts_hit += 1
        audit(db, "shadow", "draft.scored", pb.name, {"draft": d.id, "score": score, "hit": score >= HIT_THRESHOLD, "mode": d.mode})
        if d.mode == "live" and score < LESSON_BELOW:
            db.add(M.Lesson(id=new_id("les"), playbook_id=pb.id, draft_id=d.id, trigger_text=(db.get(M.Event, d.trigger_event_id) or actual).text,
                            draft_text=d.content.get("text", ""), actual_text=actual.text,
                            question=f"You answered this differently from what I drafted. What's the rule I'm missing?"))
            audit(db, "shadow", "lesson.asked", pb.name, {"draft": d.id})
        return {"draft_id": d.id, "playbook_id": pb.id, "score": score, "hit": score >= HIT_THRESHOLD}

    def confidence(self, pb: M.Playbook, trigger: M.Event) -> float:
        """How much does this trigger look like the ones the job was learned from? Outliers get escalated."""
        if (pb.trigger or {}).get("mode") != "reply":
            return 1.0
        ts = T.shingles(trigger.text)
        sims = [T.jaccard(ts, T.shingles(e.get("trigger", ""))) for e in (pb.examples or []) if e.get("trigger")]
        best = max(sims) if sims else 0.0
        kws = (pb.trigger or {}).get("keywords") or []
        toks = set(T.tokens(trigger.text))
        kw_cov = (sum(1 for k in kws if k in toks) / len(kws)) if kws else 1.0
        return round(min(1.0, 0.3 * kw_cov + 0.7 * min(1.0, best / 0.4)), 3)

    def lessons_for(self, db, pb: M.Playbook) -> list[dict]:
        rows = db.scalars(select(M.Lesson).where(M.Lesson.playbook_id == pb.id, M.Lesson.status == "answered").order_by(M.Lesson.answered_at.desc()).limit(12)).all()
        return [{"trigger": l.trigger_text, "response": l.actual_text, "rule": l.answer} for l in rows]

    def _draft(self, db, pb: M.Playbook, trigger: M.Event, mode: str = "live") -> dict:
        lessons = self.lessons_for(db, pb)
        pbd = {"name": pb.name, "actor": pb.actor, "org": self.app.settings.org_name, "response": pb.response,
               "rules": [l["rule"] for l in lessons if l.get("rule")]}
        context = self._thread_context(db, trigger)
        conf = self.confidence(pb, trigger)
        examples = (pb.examples or []) + [{"trigger": l["trigger"], "response": l["response"], "ts": 0} for l in lessons]
        try:
            text = self.app.brain.draft(pbd, trigger.text, examples, context)
        except Exception as ex:
            log.warning("draft failed for %s: %s", pb.id, ex)
            text = pb.response.get("template", "")
        tool = pb.response.get("tool", "note")
        target = trigger.target or pb.response.get("target", "")
        args = self._args_for(tool, target, text, trigger)
        d = M.Draft(id=new_id("drf"), playbook_id=pb.id, trigger_event_id=trigger.id, mode=mode,
                    content={"text": text, "target": target, "tool": tool, "args": args, "confidence": conf}, status="pending")
        db.add(d); db.flush()
        pb.drafts_total += 1
        audit(db, "shadow", "draft.created", pb.name, {"draft": d.id, "trigger": trigger.id, "stage": pb.stage, "mode": mode, "confidence": conf})
        return {"draft_id": d.id, "playbook_id": pb.id, "stage": pb.stage, "text": text, "confidence": conf}

    def _thread_context(self, db, trigger: M.Event, limit: int = 6) -> str:
        rows = db.scalars(select(M.Event).where(M.Event.thread_key == trigger.thread_key, M.Event.ts < trigger.ts)
                          .order_by(M.Event.ts.desc()).limit(limit)).all()
        return "\n".join(f"{r.actor}: {r.text[:400]}" for r in reversed(rows))

    @staticmethod
    def _args_for(tool: str, target: str, text: str, trigger: M.Event) -> dict:
        meta = trigger.meta or {}
        if tool == "github_comment":
            return {"repo": meta.get("repo") or target, "number": meta.get("number") or 0, "body": text}
        if tool == "slack_post":
            return {"channel": meta.get("channel") or target, "text": text, "thread_ts": meta.get("ts")}
        if tool == "linear_comment":
            return {"issue_id": meta.get("issue") or target, "body": text}
        return {"text": text, "target": target}

    # ------------------------------------------------------------------ propose / auto
    def _enact(self, draft_id: str) -> Optional[dict]:
        """Turn a draft into a real run: propose → pauses for approval; auto → executes (reversibly)."""
        with session() as db:
            d = db.get(M.Draft, draft_id)
            pb = db.get(M.Playbook, d.playbook_id)
            trig = db.get(M.Event, d.trigger_event_id)
            tool = self.app.registry.get(d.content.get("tool", "note"))
            if not tool:
                tool = self.app.registry.get("note")
                d.content = {**d.content, "tool": "note", "args": {"text": d.content.get("text", ""), "target": d.content.get("target", "")}}
            call = {"type": "tool_use", "id": new_id("call"), "name": tool.name, "input": d.content.get("args") or {}}
            conf = float(d.content.get("confidence", 1.0))
            escalated = pb.stage == "auto" and conf < ESCALATE_BELOW
            # an escalated auto draft runs as a *proposal*: a different principal so the auto allow-rule doesn't apply
            principal = f"playbook:{pb.id}" if not escalated else f"playbook-escalated:{pb.id}"
            if escalated:
                audit(db, "shadow", "draft.escalated", pb.name, {"draft": d.id, "confidence": conf, "threshold": ESCALATE_BELOW})
            r = M.Run(id=new_id("run"), channel=f"{trig.system}:{trig.target}", principal=principal, playbook_id=pb.id, draft_id=d.id,
                      input=f"[{pb.name}] triggered by {trig.actor}: {trig.text[:300]}",
                      messages=[{"role": "user", "content": f"Playbook '{pb.name}' triggered by {trig.actor}: {trig.text}"},
                                {"role": "assistant", "content": [{"type": "text", "text": d.content.get("text", "")}, call]}],
                      steps=[{"type": "say", "text": d.content.get("text", ""), "ts": time.time()}])
            db.add(r)
            d.status, d.run_id = "proposed", r.id
            audit(db, principal, "run.start", r.id, {"playbook": pb.name, "stage": pb.stage, "draft": d.id, "escalated": escalated})
            rid = r.id
        res = self._resume_fresh(rid)
        with session() as db:
            d = db.get(M.Draft, draft_id)
            if res["status"] == "done":
                d.status, d.resolved_at = "executed", time.time()
        return res

    def _resume_fresh(self, rid):
        with session() as db:
            r = db.get(M.Run, rid)
            messages, steps = list(r.messages), list(r.steps)
        return self.app.agent._loop(rid, messages, steps)

    # ------------------------------------------------------------------ housekeeping
    def expire_stale(self) -> int:
        cutoff = time.time() - self.app.settings.shadow_window_minutes * 60
        n = 0
        with session() as db:
            for d in db.scalars(select(M.Draft).where(M.Draft.status == "pending", M.Draft.mode == "live", M.Draft.created_at < cutoff)):
                d.status, d.resolved_at = "expired", time.time()
                n += 1
        return n

    # ------------------------------------------------------------------ stage changes
    def set_stage(self, db, pb: M.Playbook, stage: str, by: str, why: str = "") -> None:
        old = pb.stage
        pb.stage, pb.stage_changed_at = stage, time.time()
        pb.stage_history = list(pb.stage_history or []) + [{"from": old, "to": stage, "by": by, "why": why, "ts": time.time()}]
        tool = pb.response.get("tool", "note")
        principal = f"playbook:{pb.id}"
        # auto = an explicit, visible allow rule; anything else = the default (ask) applies
        for rule in db.scalars(select(M.Policy).where(M.Policy.principal == principal)):
            db.delete(rule)
        if stage == "auto":
            for t in dict.fromkeys([tool, "note"]):      # 'note' is the fallback when the target system isn't connected
                db.add(M.Policy(id=new_id("pol"), principal=principal, tool=t, decision="allow", note=f"auto stage for playbook '{pb.name}'"))
        audit(db, by, "playbook.stage", pb.name, {"from": old, "to": stage, "why": why})

    def summary(self, pb: M.Playbook) -> dict:
        s = self.app.settings
        return {"trust": trust(pb), "recommendation": recommendation(pb, s.graduate_min_scored, s.graduate_min_trust)}
