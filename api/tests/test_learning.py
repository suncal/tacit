"""The new mechanism: mine → shadow → score → trust → graduate → act (reversibly) → backtest."""
import time

from sqlalchemy import select

from tacit import models as M
from tacit.core import text as T
from tacit.core.backtest import backtest
from tacit.core.events import ingest
from tacit.core.mining import mine
from tacit.core.brains.local import LocalBrain
from tacit.core.ids import new_id
from tacit.core.playbooks import remine
from tacit.core.trust import wilson_lower, trust, recommendation
from tacit.db import session
from tacit.seed import _events, seed


def test_similarity_is_explainable():
    assert T.similarity("Sent Acme the invoice, net 30.", "Sent Acme the invoice, net 30.") == 1.0
    assert T.similarity("Sent Acme the invoice, net 30.", "lunch?") < 0.1
    assert 0.35 < T.similarity("Sent Acme their invoice just now — net 30 as usual, copy in the shared drive under Finance/Invoices.",
                               "Done — Acme invoice sent, net 30. PDF is in Finance/Invoices.") < 0.8
    assert "2fa" in T.tokens("how do I reset 2FA for a user?")


def test_wilson_is_conservative():
    assert wilson_lower(3, 3) < wilson_lower(30, 30)
    assert wilson_lower(0, 0) == 0.0
    assert 0.55 < wilson_lower(9, 10) < 0.7


def test_mining_finds_real_patterns_and_ignores_noise():
    found = mine(_events())
    names = [f["name"] for f in found]
    assert any("invoice" in n for n in names)
    assert any("2fa" in n for n in names)
    assert any("pull requests" in n for n in names)
    assert any("every mon" in n for n in names), names
    assert not any("lunch" in n.lower() for n in names)
    assert len(found) <= 8                                    # 5 real jobs hidden in 260 noise messages
    inv = next(f for f in found if "invoice" in f["name"])
    assert inv["actor"] == "priya" and inv["trigger"]["keywords"] == ["invoice"] and inv["evidence_count"] >= 10
    assert inv["response"]["tool"] == "slack_post"


def test_shadow_scores_against_the_humans_real_action(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    remine()
    with session() as db:
        pb = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        tacit.shadow.set_stage(db, pb, "shadow", by="test")
        pb_id = pb.id
    now = time.time()
    tid = ingest(tacit, system="slack", kind="message", actor="jonas", text="where's the invoice for Acme?", target="#billing", thread_key="slack:C_BILLING:t1", ts=now, meta={"channel": "#billing"})
    with session() as db:
        d = db.scalar(select(M.Draft).where(M.Draft.trigger_event_id == tid))
        assert d.status == "pending" and "invoice" in d.content["text"].lower()
    ingest(tacit, system="slack", kind="message", actor="priya", text="Sent Acme their invoice just now — net 30 as usual, copy in the shared drive under Finance/Invoices.", target="#billing", thread_key="slack:C_BILLING:t1", ts=now + 60)
    with session() as db:
        d = db.scalar(select(M.Draft).where(M.Draft.trigger_event_id == tid))
        pb = db.get(M.Playbook, pb_id)
        assert d.status == "scored" and d.score is not None and d.actual_event_id
        assert pb.drafts_scored == 1
        assert trust(pb)["scored"] == 1
    # someone else replying in the thread must NOT score the draft
    tid2 = ingest(tacit, system="slack", kind="message", actor="leila", text="invoice for Globex please", target="#billing", thread_key="slack:C_BILLING:t2", ts=now)
    ingest(tacit, system="slack", kind="message", actor="tomas", text="I think priya handles that", target="#billing", thread_key="slack:C_BILLING:t2", ts=now + 30)
    with session() as db:
        assert db.scalar(select(M.Draft).where(M.Draft.trigger_event_id == tid2)).status == "pending"


def test_backtest_and_graduation_recommendations(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    remine()
    with session() as db:
        for pb in db.scalars(select(M.Playbook)):
            tacit.shadow.set_stage(db, pb, "shadow", by="test")
    rep = backtest(tacit)
    assert rep["total"]["n"] > 30 and rep["total"]["hit_rate"] > 0.6, rep["total"]
    with session() as db:
        pb = max((p for p in db.scalars(select(M.Playbook)) if p.drafts_scored >= 10), key=lambda p: trust(p)["trust"])
        rec = recommendation(pb, 10, 0.6)
        assert rec and rec["to"] == "propose", (trust(pb), rec)
    # backtest is idempotent: running again does not double count
    before = rep["total"]["n"]
    rep2 = backtest(tacit)
    with session() as db:
        assert sum(p.drafts_scored for p in db.scalars(select(M.Playbook))) == rep2["total"]["n"] == before


def test_propose_pauses_and_auto_acts_reversibly(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    remine()
    with session() as db:
        inv = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        tfa = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%2fa%")))
        tacit.shadow.set_stage(db, inv, "propose", by="test")
        tfa.approvals = 5
        tacit.shadow.set_stage(db, tfa, "auto", by="test")
        inv_id, tfa_id = inv.id, tfa.id
    ingest(tacit, system="slack", kind="message", actor="jonas", text="where's the invoice for Hooli?", target="#billing", thread_key="slack:C_BILLING:p1", meta={"channel": "#billing"})
    with session() as db:
        a = db.scalar(select(M.Approval).where(M.Approval.status == "pending"))
        assert a and a.playbook_id == inv_id and a.preview.get("text")
        run = db.get(M.Run, a.run_id)
        assert run.status == "waiting" and run.draft_id
        aid = a.id
    ingest(tacit, system="slack", kind="message", actor="leila", text="customer locked out, 2fa codes not arriving", target="#support", thread_key="slack:C_SUPPORT:p1", meta={"channel": "#support"})
    with session() as db:
        run = db.scalar(select(M.Run).where(M.Run.playbook_id == tfa_id))
        assert run.status == "done" and run.tx_status == "committed"
        assert len(run.actions) == 1 and run.actions[0].undo is not None
        assert db.get(M.Playbook, tfa_id).executions == 1
        run_id = run.id
    # approve the proposal → executes; then undo the auto run → memory note removed, playbook undo counted
    r = tacit.agent.decide_approval(aid, True, by="test")
    assert r["status"] == "done" and r["actions"] and r["actions"][0]["status"] == "done"
    with session() as db:
        assert db.get(M.Playbook, inv_id).approvals == 1
    out = tacit.agent.undo_run(run_id, by="test")
    assert out["tx_status"] == "undone" and out["results"][0]["undone"]
    with session() as db:
        assert db.get(M.Playbook, tfa_id).undos == 1
        assert db.get(M.Run, run_id).actions[0].status == "undone"


def test_seed_is_deterministic_and_fast(tacit):
    r = seed(tacit, force=True)
    assert r["seeded"] and r["events"] > 400 and r["seconds"] < 10
    with session() as db:
        stages = {p.stage for p in db.scalars(select(M.Playbook))}
        assert {"auto", "propose", "shadow"} <= stages


def test_confidence_escalates_outliers_even_on_auto(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    remine()
    with session() as db:
        inv = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        inv.approvals = 5
        tacit.shadow.set_stage(db, inv, "auto", by="test")
        inv_id = inv.id
    # a normal trigger → acts on its own
    ingest(tacit, system="slack", kind="message", actor="jonas", text="where's the invoice for Acme? finance is chasing", target="#billing", thread_key="slack:C_BILLING:a1", meta={"channel": "#billing"})
    # an outlier that only shares the keyword → escalated to a human
    ingest(tacit, system="slack", kind="message", actor="jonas", text="invoice dispute escalation: legal wants the whole contract history and a call with their CFO", target="#billing", thread_key="slack:C_BILLING:a2", meta={"channel": "#billing"})
    with session() as db:
        runs = db.scalars(select(M.Run).where(M.Run.playbook_id == inv_id).order_by(M.Run.created_at)).all()
        assert [r.status for r in runs] == ["done", "waiting"]
        assert runs[1].principal.startswith("playbook-escalated:")
        a = db.scalar(select(M.Approval).where(M.Approval.status == "pending"))
        d = db.get(M.Draft, runs[1].draft_id)
        assert a and d.content["confidence"] < 0.45 < db.get(M.Draft, runs[0].draft_id).content["confidence"]


def test_miss_creates_lesson_and_rule_feeds_drafts(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    remine()
    with session() as db:
        inv = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        tacit.shadow.set_stage(db, inv, "shadow", by="test")
    now = time.time()
    ingest(tacit, system="slack", kind="message", actor="jonas", text="where's the invoice for Acme?", target="#billing", thread_key="slack:C_BILLING:m1", ts=now, meta={"channel": "#billing"})
    ingest(tacit, system="slack", kind="message", actor="priya", text="Acme is on a payment hold — no invoices go out until finance clears them. Ask Sam.", target="#billing", thread_key="slack:C_BILLING:m1", ts=now + 60)
    with session() as db:
        l = db.scalar(select(M.Lesson).where(M.Lesson.status == "open"))
        assert l and "hold" in l.actual_text
        l.answer, l.status, l.answered_at = "Customers on payment hold get no invoice — tell them to ask Sam.", "answered", time.time()
        db.flush()
        pb = db.get(M.Playbook, l.playbook_id)
        assert tacit.shadow.lessons_for(db, pb)[0]["rule"].startswith("Customers on payment hold")
    # a similar trigger now draws on the lesson (local brain: nearest example includes the lesson's real reply)
    ingest(tacit, system="slack", kind="message", actor="leila", text="where's the invoice for Acme? they're asking again", target="#billing", thread_key="slack:C_BILLING:m2", ts=now + 120, meta={"channel": "#billing"})
    with session() as db:
        d = db.scalars(select(M.Draft).order_by(M.Draft.created_at.desc())).first()
        assert "hold" in d.content["text"]


def test_cover_promotes_and_restores(tacit):
    from tacit.core.people import people, start_cover, end_cover
    for e in _events():
        ingest(tacit, shadow=False, **e)
    remine()
    with session() as db:
        for pb in db.scalars(select(M.Playbook).where(M.Playbook.actor == "priya")):
            tacit.shadow.set_stage(db, pb, "shadow", by="test")
    backtest(tacit)
    with session() as db:
        ppl = {p["actor"]: p for p in people(db, tacit)}
        assert ppl["priya"]["jobs"] >= 2 and ppl["priya"]["coverable"] >= 1
        c = start_cover(db, tacit, "priya", backup="maya", until=time.time() + 86400, by="test")
        assert len(c.promoted) >= 1
        assert all(db.get(M.Playbook, x["playbook_id"]).stage == "propose" for x in c.promoted)
        end_cover(db, tacit, c, by="test")
        assert all(db.get(M.Playbook, x["playbook_id"]).stage == "shadow" for x in c.promoted)


# ------------------------------------------------------------------ what a real model adds
class StubLLM(LocalBrain):
    """Stands in for Claude: same contract, canned JSON. Proves the wiring without spending a key."""
    name, model, is_llm = "stub", "stub-1", True

    def __init__(self):
        self.drafts, self.json_calls = [], []

    def json_call(self, system, prompt, max_tokens=1500):
        self.json_calls.append(prompt)
        if "give a better name" in prompt:
            import re as _re
            ids = _re.findall(r'<job id="([^"]+)"', prompt)
            return {"jobs": [{"id": i, "name": f"Named job {n}", "summary": f"priya does this when asked, case {n}."} for n, i in enumerate(ids)]}
        return {"question": "Is Acme on payment hold, so no invoice goes out until finance clears it?",
                "suggestion": "Customers on payment hold get no invoice — tell them to ask Sam.", "one_off": False}

    def draft(self, playbook, trigger_text, examples, context="", memory=""):
        self.drafts.append({"trigger": trigger_text, "context": context, "memory": memory, "rules": playbook.get("rules", [])})
        return "Sent them the invoice — net 30, copy in Finance/Invoices."


def test_a_model_names_the_jobs_it_mined(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    stub = StubLLM()
    out = remine(by="test", brain=stub)
    assert out["named"] >= 4 and stub.json_calls
    with session() as db:
        pbs = db.scalars(select(M.Playbook)).all()
        assert all(p.name.startswith("Named job") and p.summary for p in pbs)
    # naming is not repeated for jobs that already have a summary
    stub2 = StubLLM()
    remine(by="test", brain=stub2)
    assert stub2.json_calls == []


def test_a_model_proposes_the_rule_behind_a_miss(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    remine()
    stub = StubLLM()
    tacit.brain = stub
    with session() as db:
        db.add(M.Memory(id=new_id("mem"), text="Invoices are net 30 and filed under Finance/Invoices.", tags=["finance"]))
        pb = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        tacit.shadow.set_stage(db, pb, "shadow", by="test")
    now = time.time()
    ingest(tacit, system="slack", kind="message", actor="jonas", text="where's the invoice for Acme?", target="#billing", thread_key="slack:C_BILLING:llm1", ts=now, meta={"channel": "#billing"})
    assert stub.drafts and "net 30" in stub.drafts[-1]["memory"]          # the draft sees what the company knows
    ingest(tacit, system="slack", kind="message", actor="priya", text="Acme is on payment hold — nothing goes out until finance clears it. Ask Sam.", target="#billing", thread_key="slack:C_BILLING:llm1", ts=now + 90)
    with session() as db:
        l = db.scalar(select(M.Lesson).where(M.Lesson.status == "open"))
        assert "payment hold" in l.question and l.suggestion.startswith("Customers on payment hold")
        l.answer, l.status, l.answered_at = l.suggestion, "answered", time.time()
        db.flush()
        pb = db.get(M.Playbook, l.playbook_id)
        assert tacit.shadow.lessons_for(db, pb)[0]["rule"] == l.suggestion
    ingest(tacit, system="slack", kind="message", actor="leila", text="invoice for Globex please", target="#billing", thread_key="slack:C_BILLING:llm2", ts=now + 200, meta={"channel": "#billing"})
    assert "payment hold" in " ".join(stub.drafts[-1]["rules"])           # the rule reaches the next draft
