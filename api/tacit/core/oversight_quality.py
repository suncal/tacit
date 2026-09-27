"""Measuring the human, not the AI.

Article 14 does not ask for oversight; it asks for oversight that is *effective*. Every product on the
market measures the model. None measures whether the person approving its actions was actually looking —
and an approval granted in two seconds on a four-hundred-word change is not oversight, it is a signature.

Tacit can measure it because it records what nobody else links together: who decided, how long they took,
how much text they were shown, how confident the system was, and whether the thing they approved had to be
reversed afterwards.

The consequence matters more than the metric. Tacit's trust ladder treats approvals as evidence that a job
deserves autonomy. If those approvals were rubber-stamped, the evidence is counterfeit — so a decision that
fails the attention test is excluded from promotion evidence rather than merely reported.
"""
from __future__ import annotations

import statistics
import time
from typing import Optional

from sqlalchemy import select

from .. import models as M

# A person reads prose at roughly 250 words a minute, and a change preview needs a glance at the target
# as well as the text. Below this, they cannot have read what they approved.
WORDS_PER_SECOND = 250 / 60
FLOOR_SECONDS = 2.5
CEILING_SECONDS = 90.0          # past this we assume they were doing something else, not reading harder
FATIGUE_MIN_DECISIONS = 8       # below this, a trend line is noise
FATIGUE_SHARE = 0.5             # flag a reviewer who has shed half their usual attention over the period
STAMP_RATE_TEAM = 0.2           # rubber-stamping across the whole queue
STAMP_RATE_PERSON = 0.4         # or concentrated in one reviewer, which the team average can hide


def min_read_seconds(approval: M.Approval) -> float:
    """The least time in which this specific decision could have been made honestly."""
    pv = approval.preview or {}
    text = " ".join(str(pv.get(k) or "") for k in ("summary", "text", "diff"))
    if not text:
        text = " ".join(str(v) for v in (approval.args or {}).values())[:2000]
    words = len(text.split())
    return round(min(CEILING_SECONDS, max(FLOOR_SECONDS, words / WORDS_PER_SECOND)), 2)


def decision_quality(db, a: M.Approval) -> Optional[dict]:
    """One decision, examined. Returns None while it is still pending."""
    if a.status == "pending" or not a.decided_at:
        return None
    took = max(0.0, a.decided_at - a.created_at)
    need = min_read_seconds(a)
    run = db.get(M.Run, a.run_id)
    draft = db.get(M.Draft, run.draft_id) if run and run.draft_id else None
    confidence = (draft.content or {}).get("confidence") if draft else None
    reversed_after = bool(run and any(x.status == "undone" for x in run.actions))
    return {
        "id": a.id, "tool": a.tool, "playbook_id": a.playbook_id, "by": a.decided_by or "unknown",
        "status": a.status, "seconds": round(took, 1), "needed_seconds": need,
        "attention": "rubber-stamped" if (a.status == "approved" and took < need) else "considered",
        "confidence": confidence, "reversed_after": reversed_after,
        "created_at": a.created_at, "decided_at": a.decided_at,
        "escalated": a.principal.startswith("playbook-escalated:"),
    }


def counted_as_evidence(db, a: M.Approval) -> bool:
    """Should this approval count towards a job earning more autonomy?
    An approval nobody had time to read is not evidence that the job is safe."""
    q = decision_quality(db, a)
    return bool(q) and q["status"] == "approved" and q["attention"] == "considered"


def _trend(pairs: list[tuple[float, float]]) -> float:
    """Least-squares slope of value against time, in units per day. Positive = getting slower/more careful."""
    if len(pairs) < FATIGUE_MIN_DECISIONS:
        return 0.0
    xs = [p[0] / 86400 for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, 3)


def report(db, app, days: int = 90) -> dict:
    since = time.time() - days * 86400
    rows = [q for q in (decision_quality(db, a) for a in db.scalars(
        select(M.Approval).where(M.Approval.created_at >= since).order_by(M.Approval.created_at))) if q]
    pending = db.scalars(select(M.Approval).where(M.Approval.status == "pending")).all()

    people: dict[str, list[dict]] = {}
    for q in rows:
        people.setdefault(q["by"], []).append(q)

    reviewers = [_reviewer(name, qs) for name, qs in people.items()]
    reviewers.sort(key=lambda r: -r["decisions"])
    score, components = _index(rows, reviewers, pending)
    findings = _findings(rows, reviewers, pending)
    return {
        "period_days": days, "decisions": len(rows), "reviewers": reviewers,
        "index": score, "band": _band(score, findings), "components": components,
        "findings": findings,
        "pending_oldest_hours": round((time.time() - min((a.created_at for a in pending), default=time.time())) / 3600, 1) if pending else 0.0,
        "pending": len(pending),
        "method": ("A decision is 'rubber-stamped' when it was approved faster than the preview could be read "
                   f"at {WORDS_PER_SECOND * 60:.0f} words per minute (floor {FLOOR_SECONDS:.1f}s). Those approvals are "
                   "excluded from the evidence a job needs to earn more autonomy."),
        "recent": sorted(rows, key=lambda q: -q["decided_at"])[:60],
    }


def _reviewer(name: str, qs: list[dict]) -> dict:
    approved = [q for q in qs if q["status"] == "approved"]
    refused = [q for q in qs if q["status"] == "denied"]
    stamped = [q for q in approved if q["attention"] == "rubber-stamped"]
    missed = [q for q in approved if q["reversed_after"]]
    lo = [q for q in qs if q["confidence"] is not None and q["confidence"] < 0.6]
    hi = [q for q in qs if q["confidence"] is not None and q["confidence"] >= 0.6]
    ar = lambda g: (sum(1 for q in g if q["status"] == "approved") / len(g)) if g else None  # noqa: E731
    calib = None
    if lo and hi and ar(hi) is not None and ar(lo) is not None:
        calib = round(ar(hi) - ar(lo), 3)          # >0 means they scrutinise the shaky ones more. That is the point.
    times = [q["seconds"] for q in qs]
    return {
        "reviewer": name, "decisions": len(qs), "approved": len(approved), "refused": len(refused),
        "refusal_rate": round(len(refused) / len(qs), 3) if qs else 0.0,
        "median_seconds": round(statistics.median(times), 1) if times else 0.0,
        "p90_seconds": round(sorted(times)[int(len(times) * 0.9)], 1) if times else 0.0,
        "rubber_stamped": len(stamped),
        "rubber_stamp_rate": round(len(stamped) / len(approved), 3) if approved else 0.0,
        "reversed_after_approval": len(missed),
        "miss_rate": round(len(missed) / len(approved), 3) if approved else None,
        "calibration": calib,
        "fatigue_slope_seconds_per_day": _trend([(q["decided_at"], q["seconds"]) for q in qs]),
        "span_days": round((max(ts) - min(ts)) / 86400, 1) if (ts := [q["decided_at"] for q in qs]) else 0.0,
        "early_seconds": _third(qs, 0), "late_seconds": _third(qs, -1),
        "escalations_seen": sum(1 for q in qs if q["escalated"]),
    }


def _third(qs: list[dict], which: int) -> Optional[float]:
    """Typical time per decision in the first or last third of this reviewer's period. Comparing the two
    says how their attention moved without a median that has already absorbed the drift."""
    if len(qs) < 3:
        return None
    ordered = sorted(qs, key=lambda q: q["decided_at"])
    k = max(1, len(ordered) // 3)
    part = ordered[:k] if which == 0 else ordered[-k:]
    return round(statistics.median(q["seconds"] for q in part), 1)


def _index(rows: list[dict], reviewers: list[dict], pending: list) -> tuple[int, list[dict]]:
    """A single number, from parts you can argue with. Every component is shown with its own score."""
    approved = [q for q in rows if q["status"] == "approved"]
    stamped = sum(1 for q in approved if q["attention"] == "rubber-stamped")
    attention = 1 - (stamped / len(approved)) if approved else None
    refusal = (sum(1 for q in rows if q["status"] == "denied") / len(rows)) if rows else None
    # some refusal is healthy; none at all means the gate is decorative, and constant refusal means it is misconfigured
    refusal_score = None if refusal is None else round(min(1.0, refusal / 0.1) if refusal <= 0.1 else max(0.0, 1 - (refusal - 0.1) / 0.5), 3)
    calibs = [r["calibration"] for r in reviewers if r["calibration"] is not None]
    calibration = round(min(1.0, max(0.0, 0.5 + statistics.fmean(calibs) / 2)), 3) if calibs else None
    misses = [q for q in approved if q["reversed_after"]]
    catch = round(1 - len(misses) / len(approved), 3) if approved else None
    concentration = None
    if reviewers:
        top = max(r["decisions"] for r in reviewers)
        total = sum(r["decisions"] for r in reviewers)
        concentration = round(1 - (top / total) + (1 / max(1, len(reviewers))), 3) if total else None
        concentration = min(1.0, concentration) if concentration is not None else None
    slopes = [r["fatigue_slope_seconds_per_day"] for r in reviewers if r["decisions"] >= FATIGUE_MIN_DECISIONS]
    fatigue = round(min(1.0, max(0.0, 1 + statistics.fmean(slopes) / 10)), 3) if slopes else None

    parts = [
        ("Attention", attention, .30, "share of approvals where the reviewer had time to read what they approved"),
        ("Catching", catch, .25, "approvals that were not reversed afterwards"),
        ("Calibration", calibration, .15, "whether low-confidence actions get more scrutiny than confident ones"),
        ("Independence", refusal_score, .15, "a gate that never refuses anything is decorative"),
        ("Spread", concentration, .10, "oversight resting on more than one person"),
        ("Stamina", fatigue, .05, "whether decisions are getting quicker over time"),
    ]
    known = [(n, v, w, d) for n, v, w, d in parts if v is not None]
    total_w = sum(w for _, _, w, _ in known)
    score = round(100 * sum(v * w for _, v, w, _ in known) / total_w) if total_w else 0
    return score, [{"name": n, "score": round(v * 100), "weight": round(w / total_w, 3) if total_w else 0, "what": d}
                   for n, v, w, d in known]


BANDS = ["decorative", "nominal", "thin", "effective"]


def _band(score: int, findings: list[dict]) -> str:
    """The word, not the number. Oversight cannot be called effective while something high-severity
    about it is unresolved, however well the weighted average comes out."""
    band = BANDS[3] if score >= 80 else BANDS[2] if score >= 60 else BANDS[1] if score >= 40 else BANDS[0]
    if any(f["severity"] == "high" for f in findings):
        band = BANDS[min(BANDS.index(band), 1)]
    return band


def _findings(rows: list[dict], reviewers: list[dict], pending: list) -> list[dict]:
    out = []
    approved = [q for q in rows if q["status"] == "approved"]
    stamped = [q for q in approved if q["attention"] == "rubber-stamped"]
    worst = max(reviewers, key=lambda r: r["rubber_stamp_rate"], default=None)
    team_rate = len(stamped) / len(approved) if approved else 0.0
    # one reviewer signing everything unread is a finding even when the team average looks tolerable
    person = worst if worst and worst["decisions"] >= FATIGUE_MIN_DECISIONS and worst["rubber_stamp_rate"] >= STAMP_RATE_PERSON else None
    if approved and (team_rate >= STAMP_RATE_TEAM or person):
        where = (f"{person['reviewer']} granted {person['rubber_stamped']} of their {person['approved']} approvals "
                 f"({person['rubber_stamp_rate']:.0%}) that way" if person else
                 f"{worst['reviewer']} accounts for the most, at {worst['rubber_stamp_rate']:.0%} of their approvals")
        out.append({"severity": "high", "title": "Approvals are being signed, not read",
                    "detail": f"{len(stamped)} of {len(approved)} approvals were granted faster than the preview could be read — "
                              f"{team_rate:.0%} of the queue. {where}. "
                              "Those decisions no longer count towards a job earning more autonomy.",
                    "do": "Route approvals to someone with time, or narrow the jobs so each decision is smaller."})
    if rows and not any(q["status"] == "denied" for q in rows):
        out.append({"severity": "medium", "title": "Nothing has ever been refused",
                    "detail": f"All {len(rows)} decisions in this period were approvals. A control that never says no "
                              "cannot be shown to be doing anything.",
                    "do": "Check whether the low-confidence and escalated cases are actually reaching a person."})
    if len(reviewers) == 1 and rows:
        out.append({"severity": "medium", "title": "Oversight rests on one person",
                    "detail": f"Every decision was made by {reviewers[0]['reviewer']}. If they are away, the queue stops — "
                              "and there is no second opinion on any of it.",
                    "do": "Add a second approver, or set a cover arrangement on the People page."})
    for r in reviewers:
        early, late = r["early_seconds"], r["late_seconds"]
        if (r["decisions"] < FATIGUE_MIN_DECISIONS or not early or late is None
                or r["fatigue_slope_seconds_per_day"] >= 0 or late > FATIGUE_SHARE * early):
            continue
        out.append({"severity": "medium", "title": f"{r['reviewer']} is deciding faster over time",
                    "detail": f"They started this period spending about {early:.0f}s on a decision and now spend about "
                              f"{late:.0f}s — a {1 - late / early:.0%} drop across {r['span_days']:.0f} days. "
                              "This is what approval fatigue looks like before it becomes rubber-stamping.",
                    "do": "Reduce the volume reaching them, or rotate the duty."})
    miscal = [r for r in reviewers if r["calibration"] is not None and r["calibration"] < 0]
    for r in miscal:
        out.append({"severity": "high", "title": f"{r['reviewer']} approves shaky actions more readily than confident ones",
                    "detail": "Low-confidence drafts are being approved at a higher rate than high-confidence ones, which is "
                              "the opposite of what attention would produce.",
                    "do": "Show the confidence more prominently, or require a second approver below the escalation threshold."})
    if pending:
        oldest = (time.time() - min(a.created_at for a in pending)) / 3600
        if oldest > 24:
            out.append({"severity": "low", "title": "The queue is ageing",
                        "detail": f"{len(pending)} decisions are waiting, the oldest for {oldest:.0f} hours. Work stalls and "
                                  "people learn to distrust the queue.",
                        "do": "Set TACIT_NOTIFY_SLACK_CHANNEL so approvals are chased where the team already is."})
    return out
