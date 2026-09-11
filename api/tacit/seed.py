"""Seed a believable org: 90 days of team activity with real recurring patterns hidden in real noise.

Then: mine → shadow → backtest → graduate, so the console opens in a state that shows the whole arc.
Deterministic (seeded RNG) so screenshots and tests agree.
"""
from __future__ import annotations

import datetime as dt
import random
import time

from sqlalchemy import select

from . import models as M
from .auth import hash_password
from .core.audit import audit
from .core.backtest import backtest
from .core.events import ingest
from .core.ids import new_id
from .core.meetings import summarize
from .core.playbooks import remine
from .core.scheduler import compute_next, parse_schedule
from .db import session

R = random.Random(7)
DAYS = 90
PEOPLE = ["maya", "sam", "priya", "jonas", "leila", "tomas", "aiko"]
CUSTOMERS = ["Acme", "Globex", "Initech", "Umbrella", "Hooli", "Vandelay", "Stark", "Wayne", "Tyrell", "Cyberdyne", "Wonka", "Soylent"]

INVOICE_ASKS = ["hey, where's the invoice for {c}? finance is chasing", "can someone send the {c} invoice for last month?",
                "{c} is asking for their invoice again", "invoice for {c} — did it go out?", "need the {c} invoice pdf for the auditors",
                "do we have the invoice for {c} ready?"]
INVOICE_REPLIES = ["Sent {c} their invoice just now — net 30 as usual, copy in the shared drive under Finance/Invoices.",
                   "Done — {c} invoice sent, net 30. PDF is in Finance/Invoices.",
                   "{c} invoice went out this morning, net 30 terms. Copy in Finance/Invoices if you need it.",
                   "Sent to {c} — net 30, copy filed under Finance/Invoices."]
TWOFA_ASKS = ["customer can't get into their account, 2fa codes not arriving", "how do I reset 2FA for a user who lost their phone?",
              "user locked out — 2fa device gone. what's the process?", "2fa reset request from {c}, who handles this?"]
TWOFA_REPLIES = ["Process: verify identity via the billing email on file, then Admin → Users → Reset 2FA. It logs an audit entry. Tell them to re-enrol within 24h.",
                 "Verify them via the billing email first, then Admin → Users → Reset 2FA (it writes an audit entry). They must re-enrol within 24h.",
                 "Same as always: identity check via billing email → Admin → Users → Reset 2FA → ask them to re-enrol within 24h."]
PR_TITLES = ["Add retry to webhook dispatcher", "Fix off-by-one in pagination", "Migrate billing to Stripe price IDs", "Refactor auth middleware",
             "Add rate limiting to public API", "Upgrade Postgres driver", "Cache customer lookups", "Fix flaky invoice test", "Add audit log export",
             "Tighten CSP headers", "Replace moment with date-fns", "Add index on events.thread_key", "Handle Slack retries idempotently", "Bump Python to 3.12"]
PR_REVIEW = ["First pass:\n- Does this need a migration? If so, is it reversible?\n- Tests cover the failure path?\n- Please add a line to CHANGELOG.\nI'll do a full review once CI is green.",
             "Quick first look:\n- Migration reversible?\n- Failure-path tests?\n- CHANGELOG entry please.\nFull review after CI passes.",
             "First-pass checklist: reversible migration (if any), tests for the failure path, CHANGELOG line. Will review properly once CI is green."]
ONCALL = ["On-call summary for the week:\n• Pages: {p}\n• Incidents: {i} (all resolved)\n• Noisy alert: {a} — tuning threshold\n• Handover: {h}",
          "Weekly on-call recap:\n• {p} pages, {i} incidents, all resolved\n• Noisiest alert: {a}, threshold being tuned\n• Handing over to {h}"]
ALERTS = ["queue-depth", "p95-latency", "disk-usage", "error-rate", "cert-expiry"]
BUG_TITLES = ["Export CSV drops last row", "Invoice PDF shows wrong currency", "Login loops on Safari", "Webhook retries duplicate events",
              "Dashboard chart off by one day", "Search ignores accents", "2FA reset email in spam", "Timezone wrong in audit log", "Slow customer page"]
BUG_TRIAGE = ["Triage: reproduced on staging. Severity {s}. Assigning to this sprint; please add repro steps + expected vs actual to the description.",
              "Triaged — reproduces on staging, severity {s}. Pulling into the sprint. Add repro steps and expected/actual please.",
              "Repro confirmed on staging (sev {s}). Into this sprint. Needs repro steps + expected vs actual in the description."]
NOISE = ["lunch?", "anyone seen the new figma?", "deploy going out in 10", "brb", "nice work on the demo yesterday", "can we move standup to 10?",
         "who owns the analytics dashboard now?", "reminder: friday deploy freeze", "the coffee machine is dead again", "merged 🎉",
         "what's the wifi password in the new office", "PTO next monday", "great thread, thanks all", "I'll take a look after lunch",
         "pushing a fix now", "is staging down?", "staging is back", "ship it", "🔥", "any objections to bumping the SLA doc?"]

MEMORIES = [
    ("Deploys are frozen every Friday after 14:00 — nothing ships Friday afternoon.", ["ops", "policy"]),
    ("Production stack: Python services on Fly.io, Postgres on Neon, frontend on Vercel.", ["eng", "infra"]),
    ("Pricing decision (Sep 2026): annual discount is 20%; the Starter tier is discontinued.", ["pricing", "decision"]),
    ("Support SLA: first reply within 4 business hours; P1 incidents page on-call in #incidents.", ["support", "sla"]),
    ("Sam owns billing, Stripe and on-call rota. Priya owns support playbooks and the FAQ. Maya is EM and reviews every PR first.", ["people", "owners"]),
    ("Invoices are net 30 and always filed under Finance/Invoices in the shared drive.", ["finance", "process"]),
    ("2FA resets require identity verification via the billing email on file and are logged to the audit trail.", ["support", "security"]),
]

TRANSCRIPT = """Maya: Quick sync on the pricing page relaunch.
Sam: Design is done. Engineering needs to wire the new Stripe price IDs before we ship.
Maya: Agreed. Sam will wire the price IDs by Thursday.
Priya: I should update the FAQ copy — the annual discount changed from 15% to 20%.
Maya: Decision: we go with 20% annual, and we drop the Starter tier entirely.
Sam: Then someone needs to migrate the 40 Starter customers. Priya, can you draft the email?
Priya: Yes, I'll draft the migration email by tomorrow.
Maya: Action: Maya to book the launch review for Monday 10am.
"""


def _at(day_offset: float, hour: float, minute: float = 0) -> float:
    base = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=DAYS)
    return (base + dt.timedelta(days=day_offset, hours=hour, minutes=minute)).timestamp()


def _pick(templates: list[str]) -> str:
    """People have a canned reply and occasionally paraphrase it."""
    return templates[0] if R.random() < 0.75 else R.choice(templates[1:])


def _events() -> list[dict]:
    ev: list[dict] = []

    def add(system, kind, actor, text, target, thread, ts, meta=None):
        ev.append(dict(system=system, kind=kind, actor=actor, text=text, target=target, thread_key=thread, ts=ts, meta=meta or {}, external_id=f"seed:{len(ev)}"))

    # 1. invoice requests in #billing → priya replies (15 of them, 2 unanswered)
    for i in range(17):
        d = R.uniform(0, DAYS - 2); c = R.choice(CUSTOMERS); asker = R.choice([p for p in PEOPLE if p != "priya"])
        th = f"slack:C_BILLING:{1000 + i}"
        add("slack", "message", asker, R.choice(INVOICE_ASKS).format(c=c), "#billing", th, _at(d, R.uniform(9, 17)), {"channel": "#billing"})
        if i < 15:
            add("slack", "message", "priya", _pick(INVOICE_REPLIES).format(c=c), "#billing", th, ev[-1]["ts"] + R.uniform(600, 5400), {"channel": "#billing"})
    # 2. 2FA questions in #support → priya (9)
    for i in range(9):
        d = R.uniform(0, DAYS - 2); c = R.choice(CUSTOMERS); asker = R.choice([p for p in PEOPLE if p != "priya"])
        th = f"slack:C_SUPPORT:{2000 + i}"
        add("slack", "message", asker, R.choice(TWOFA_ASKS).format(c=c), "#support", th, _at(d, R.uniform(9, 18)), {"channel": "#support"})
        add("slack", "message", "priya", _pick(TWOFA_REPLIES), "#support", th, ev[-1]["ts"] + R.uniform(300, 3600), {"channel": "#support"})
    # 3. PRs opened → maya's first-pass comment (14)
    for i, title in enumerate(PR_TITLES):
        d = R.uniform(0, DAYS - 2); author = R.choice([p for p in PEOPLE if p != "maya"]); n = 400 + i
        th = f"github:northwind/api#{n}"
        add("github", "pr.opened", author, f"{title}\n\nSee linked issue. Ready for review.", "northwind/api", th, _at(d, R.uniform(9, 18)), {"repo": "northwind/api", "number": n})
        add("github", "comment", "maya", _pick(PR_REVIEW), "northwind/api", th, ev[-1]["ts"] + R.uniform(900, 7200), {"repo": "northwind/api", "number": n})
        if R.random() < 0.5:
            add("github", "comment", author, R.choice(["Thanks, on it.", "Added the CHANGELOG line.", "Migration is reversible, added a down()."]), "northwind/api", th, ev[-1]["ts"] + R.uniform(600, 7200), {"repo": "northwind/api", "number": n})
    # 4. Monday on-call summary by sam in #eng (weekly, scheduled)
    for w in range(13):
        d = 7 * w + (0 - dt.datetime.fromtimestamp(_at(0, 9)).weekday()) % 7
        if d >= DAYS - 1:
            continue
        add("slack", "message", "sam", _pick(ONCALL).format(p=R.randint(0, 6), i=R.randint(0, 2), a=R.choice(ALERTS), h=R.choice(PEOPLE)), "#eng",
            f"slack:C_ENG:oncall{w}", _at(d, 9, R.uniform(0, 20)), {"channel": "#eng"})
    # 5. bug issues in Linear → sam triage comment (9)
    for i, title in enumerate(BUG_TITLES):
        d = R.uniform(0, DAYS - 2); author = R.choice([p for p in PEOPLE if p != "sam"]); ident = f"ENG-{120 + i}"
        add("linear", "issue.opened", author, f"{title}\n\nbug report from a customer", ident, f"linear:{ident}", _at(d, R.uniform(9, 18)), {"issue": ident})
        add("linear", "comment", "sam", _pick(BUG_TRIAGE).format(s=R.choice(["S2", "S3"])), ident, f"linear:{ident}", ev[-1]["ts"] + R.uniform(1200, 14400), {"issue": ident})
    # 6. noise: 260 unrelated messages + a few one-off replies
    for i in range(260):
        d = R.uniform(0, DAYS); who = R.choice(PEOPLE); ch = R.choice(["#eng", "#general", "#support", "#billing", "#random"])
        th = f"slack:{ch}:noise{i}"
        add("slack", "message", who, R.choice(NOISE), ch, th, _at(d, R.uniform(8, 19)), {"channel": ch})
        if R.random() < 0.25:
            add("slack", "message", R.choice(PEOPLE), R.choice(NOISE), ch, th, ev[-1]["ts"] + R.uniform(60, 3600), {"channel": ch})
    ev.sort(key=lambda e: e["ts"])
    return ev


def seed(app, force: bool = False) -> dict:
    with session() as db:
        if db.get(M.Setting, "demo.seeded") and not force:
            return {"seeded": False}
    t0 = time.time()
    with session() as db:
        if not db.scalar(select(M.User.id).limit(1)):
            db.add(M.User(id=new_id("usr"), email="demo@northwind.dev", name="Demo Admin", role="admin", password_hash=hash_password("tacit-demo")))
        for text, tags in MEMORIES:
            db.add(M.Memory(id=new_id("mem"), text=text, tags=tags, source="seed"))
        db.add(M.Task(id=new_id("task"), title="Wire new Stripe price IDs for the relaunch", assignee="sam", source="meeting", due="Thursday"))
        db.add(M.Task(id=new_id("task"), title="Rotate the Neon database password", assignee="sam", source="console"))
        for name, sched, prompt in [("morning-digest", "daily 09:00", "Post a short digest of open tasks and anything new in memory since yesterday. Under 8 lines."),
                                    ("weekly-memory-recap", "weekly fri 16:00", "Summarise the decisions saved to memory this week as bullets, then create a task 'Review weekly recap' for maya.")]:
            trig = parse_schedule(sched)
            db.add(M.Automation(id=new_id("auto"), name=name, trigger=trig, prompt=prompt, next_run_at=compute_next(trig)))
        notes, items = summarize(app.brain, TRANSCRIPT)
        db.add(M.Meeting(id=new_id("mtg"), title="Pricing relaunch sync", transcript=TRANSCRIPT, notes=notes, action_items=items))
        db.add(M.Policy(id=new_id("pol"), principal="automation:*", tool="shell_run", decision="deny", note="automations may never run shell commands"))
        db.add(M.Budget(id=new_id("bud"), scope="playbook:*", max_writes_per_hour=10, max_usd_per_day=3.0, note="playbooks can't run away"))
        db.add(M.Budget(id=new_id("bud"), scope="automation:*", max_writes_per_hour=20, max_usd_per_day=5.0))
        audit(db, "seed", "seed.start", "", {})
    # events: ingest without shadowing (no playbooks yet), then mine
    events = _events()
    for e in events:
        ingest(app, shadow=False, **e)
    mined = remine(by="seed")
    # graduate the strongest patterns so the console shows the whole arc
    with session() as db:
        pbs = sorted(db.scalars(select(M.Playbook)).all(), key=lambda p: -p.evidence_count)
        for i, pb in enumerate(pbs[:4]):
            app.shadow.set_stage(db, pb, "shadow", by="seed", why="seeded: worth watching")
    report = backtest(app)
    with session() as db:
        pbs = sorted(db.scalars(select(M.Playbook).where(M.Playbook.stage == "shadow")).all(), key=lambda p: -(p.drafts_hit / max(p.drafts_scored, 1)))
        if pbs:
            best = pbs[0]
            best.approvals, best.rejections = 11, 1          # a history of human approvals
            app.shadow.set_stage(db, best, "auto", by="demo@northwind.dev", why="11 approved / 1 rejected, 0 undos")
        if len(pbs) > 1:
            second = pbs[1]
            second.approvals, second.rejections = 4, 0
            app.shadow.set_stage(db, second, "propose", by="demo@northwind.dev", why=f"{second.drafts_hit}/{second.drafts_scored} shadow drafts matched")
    # live triggers: one pending approval (propose) and one executed+reversible run (auto)
    live_ids = []
    with session() as db:
        auto_pb = db.scalar(select(M.Playbook).where(M.Playbook.stage == "auto"))
        prop_pb = db.scalar(select(M.Playbook).where(M.Playbook.stage == "propose"))
    for pb in (auto_pb, prop_pb):
        if not pb:
            continue
        e = _fresh_trigger(pb)
        if e:
            live_ids.append(ingest(app, **e))
    # a couple of pending shadow drafts too
    with session() as db:
        shadow_pb = db.scalar(select(M.Playbook).where(M.Playbook.stage == "shadow"))
    if shadow_pb:
        e = _fresh_trigger(shadow_pb)
        if e:
            ingest(app, **e)
    with session() as db:
        db.add(M.Setting(key="demo.seeded", value=True))
        audit(db, "seed", "seed.done", "", {"events": len(events), "seconds": round(time.time() - t0, 1), **mined})
    return {"seeded": True, "events": len(events), "mined": mined, "backtest": report["total"], "seconds": round(time.time() - t0, 1)}


def _fresh_trigger(pb) -> dict | None:
    t = pb.trigger or {}
    now = time.time() - R.uniform(300, 1800)
    if t.get("mode") != "reply":
        return None
    kws = set(t.get("keywords") or [])
    if pb.system == "slack" and "invoice" in kws:
        c = R.choice(CUSTOMERS)
        return dict(system="slack", kind="message", actor="jonas", text=f"where's the invoice for {c}? they emailed again", target="#billing", thread_key="slack:C_BILLING:live1", ts=now, meta={"channel": "#billing"}, external_id="seed:live:invoice")
    if pb.system == "slack":
        return dict(system="slack", kind="message", actor="leila", text="customer locked out, 2fa codes not arriving — who can reset?", target="#support", thread_key="slack:C_SUPPORT:live1", ts=now, meta={"channel": "#support"}, external_id="seed:live:2fa")
    if pb.system == "github":
        return dict(system="github", kind="pr.opened", actor="tomas", text="Add idempotency keys to invoice API\n\nReady for review.", target="northwind/api", thread_key="github:northwind/api#431", ts=now, meta={"repo": "northwind/api", "number": 431}, external_id="seed:live:pr")
    if pb.system == "linear":
        return dict(system="linear", kind="issue.opened", actor="aiko", text="Invoice totals rounding error\n\nbug report from a customer", target="ENG-140", thread_key="linear:ENG-140", ts=now, meta={"issue": "ENG-140"}, external_id="seed:live:bug")
    return None
