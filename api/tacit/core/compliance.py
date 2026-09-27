"""Tamper-evident audit + regulator-ready evidence.

EU AI Act art. 12 requires automatic, traceable logs over the system's lifetime; art. 14 requires that a
human can understand, intervene in and override the system — and that you can *show* it. Both became
enforceable on 2 August 2026. Tacit produces that evidence as a by-product of how it works, so compliance
is an export, not a project.

The log is sealed into a hash chain: every row commits to the one before it, so removing or editing any
historical row is detectable by anyone who kept an earlier root.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

from sqlalchemy import func, select

from .. import models as M

GENESIS = "0" * 64


def _canonical(e: M.AuditEvent) -> str:
    return json.dumps({"id": e.id, "ts": round(e.ts, 6), "actor": e.actor, "action": e.action,
                       "target": e.target, "ok": bool(e.ok), "detail": e.detail}, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prev: str, e: M.AuditEvent) -> str:
    return hashlib.sha256((prev + "|" + _canonical(e)).encode()).hexdigest()


def seal(db) -> int:
    """Chain every unsealed audit row, in id order. Idempotent; safe to call often."""
    tip = db.scalars(select(M.AuditEvent).where(M.AuditEvent.hash != "").order_by(M.AuditEvent.id.desc()).limit(1)).first()
    prev = tip.hash if tip else GENESIS
    n = 0
    for e in db.scalars(select(M.AuditEvent).where(M.AuditEvent.hash == "").order_by(M.AuditEvent.id)):
        e.prev_hash = prev
        e.hash = prev = _digest(prev, e)
        n += 1
    if n:
        db.flush()
    return n


def verify(db) -> dict:
    """Walk the whole chain and report the first break, if any. This is what an auditor runs."""
    prev, checked, first_break = GENESIS, 0, None
    for e in db.scalars(select(M.AuditEvent).where(M.AuditEvent.hash != "").order_by(M.AuditEvent.id)):
        expect = _digest(prev, e)
        if e.prev_hash != prev or e.hash != expect:
            first_break = {"id": e.id, "ts": e.ts, "actor": e.actor, "action": e.action,
                           "reason": "row was altered or a row before it was removed"}
            break
        prev, checked = e.hash, checked + 1
    unsealed = db.scalar(select(func.count(M.AuditEvent.id)).where(M.AuditEvent.hash == "")) or 0
    return {"intact": first_break is None, "sealed_events": checked, "unsealed_events": unsealed,
            "root": prev, "first_break": first_break, "checked_at": time.time()}


def evidence(db, app, days: int = 90) -> dict:
    """The bundle you hand a regulator, an auditor or a customer's security team."""
    seal(db)
    since = time.time() - days * 86400
    s = app.settings
    pbs = db.scalars(select(M.Playbook)).all()
    agents = db.scalars(select(M.Agent)).all()

    def n(model, *where):
        return db.scalar(select(func.count(model.id)).where(*where)) or 0

    approvals = db.scalars(select(M.Approval).where(M.Approval.created_at >= since)).all()
    decided = [a for a in approvals if a.status != "pending"]
    escalated = [a for a in approvals if a.principal.startswith("playbook-escalated:")]
    undone = n(M.Action, M.Action.status == "undone", M.Action.ts >= since)
    acted = n(M.Action, M.Action.ts >= since)

    register = []
    for p in pbs:
        if p.stage == "retired":
            continue
        t = app.shadow.summary(p)["trust"]
        register.append({
            "system_id": p.id, "name": p.name, "owner": p.actor, "surface": p.system, "autonomy": p.stage,
            "risk_tier": "limited" if p.stage != "auto" else "limited-with-autonomy",
            "human_oversight": {"candidate": "no autonomous action", "shadow": "drafts only, never acts",
                                "propose": "every action approved by a named human before execution",
                                "auto": "acts within budget; low-confidence cases escalate to a human; every action reversible"}[p.stage],
            "evidence": {"graded_drafts": t["scored"], "match_rate": t["hit_rate"], "trust_lower_bound": t["trust"],
                         "human_approvals": t["approvals"], "human_rejections": t["rejections"],
                         "executions": t["executions"], "reversals": t["undos"]},
            "stage_changes": p.stage_history,
        })

    supervised = []
    for a in agents:
        from .oversight import scorecard
        supervised.append(scorecard(db, a, days))

    return {
        "generated_at": time.time(), "organisation": s.org_name, "period_days": days,
        "framework": ["EU AI Act art. 12 (record-keeping)", "EU AI Act art. 14 (human oversight)", "ISO/IEC 42001 clause 9 (performance evaluation)"],
        "statement": ("Tacit records every AI action and every human decision automatically, in an append-only log sealed into a hash "
                      "chain. No AI system below the 'auto' stage may act without a named human approving the specific action. "
                      "Systems at 'auto' act only within enforced budgets, escalate low-confidence cases to a human, and every action "
                      "carries a recorded inverse so a human can reverse it."),
        "log_integrity": verify(db),
        "model": app.brain_info(),
        "oversight": {
            "actions_taken": acted, "actions_reversed_by_humans": undone,
            "approvals_requested": len(approvals), "approvals_granted": sum(1 for a in decided if a.status == "approved"),
            "approvals_refused": sum(1 for a in decided if a.status == "denied"),
            "low_confidence_escalations": len(escalated),
            "median_time_to_decision_s": _median([a.decided_at - a.created_at for a in decided if a.decided_at]),
            "corrections_taught_by_humans": n(M.Lesson, M.Lesson.status == "answered"),
        },
        "controls": {
            "permission_rules": [{"principal": r.principal, "tool": r.tool, "decision": r.decision} for r in db.scalars(select(M.Policy))],
            "defaults": app.policy.defaults,
            "budgets": [{"scope": b.scope, "max_writes_per_hour": b.max_writes_per_hour, "max_usd_per_day": b.max_usd_per_day} for b in db.scalars(select(M.Budget))],
            "data_residency": s.database_url.split("://")[0] + " (self-hosted)",
            "retention": "append-only; no deletion path in the product",
        },
        "ai_systems": register,
        "supervised_third_party_agents": supervised,
    }


def _median(xs: list[float]) -> Optional[float]:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2, 1)
