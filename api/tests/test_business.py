"""Verified-work billing, third-party agent oversight, tamper-evident compliance, Day-One report."""
import time

import pytest

from sqlalchemy import select

from tacit import models as M
from tacit.core import compliance, ledger, oversight
from tacit.core.events import ingest
from tacit.core.ids import new_id
from tacit.core.opportunity import run as opportunity
from tacit.core.playbooks import remine
from tacit.db import session
from tacit.seed import _events


def _seed_events(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    remine()


# ------------------------------------------------------------------ ledger
def test_only_approved_or_undisputed_work_is_billable(tacit):
    _seed_events(tacit)
    with session() as db:
        inv = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        tacit.shadow.set_stage(db, inv, "propose", by="test")
        inv_id = inv.id
    ingest(tacit, system="slack", kind="message", actor="jonas", text="where's the invoice for Hooli?", target="#billing", thread_key="slack:C_BILLING:l1", meta={"channel": "#billing"})
    with session() as db:
        aid = db.scalar(select(M.Approval).where(M.Approval.status == "pending")).id
        assert db.scalar(select(M.LedgerEntry)) is None          # nothing billable before it happens
    r = tacit.agent.decide_approval(aid, True, by="user:boss")
    with session() as db:
        e = db.scalar(select(M.LedgerEntry))
        assert e.status == "pending" and e.amount_usd == 0
        ledger.settle(db, tacit.settings)
        e = db.scalar(select(M.LedgerEntry))
        assert e.status == "verified" and e.basis == "human_approved" and e.amount_usd == tacit.settings.price_per_verified_action_usd
        assert e.detail["approved_by"] == "user:boss"
    # reversing it credits the line back, permanently
    tacit.agent.undo_run(r["id"], by="user:boss")
    with session() as db:
        e = db.scalar(select(M.LedgerEntry))
        e.status, e.amount_usd, e.settled_at = "pending", 0.0, None     # re-settle as the scheduler would
        db.flush()
        ledger.settle(db, tacit.settings)
        e = db.scalar(select(M.LedgerEntry))
        assert e.status == "disputed" and e.amount_usd == 0 and "reversed" in e.detail["reason"]
    with session() as db:
        s = ledger.summary(db, tacit.settings, 30)
        assert s["verified"] == 0 and s["disputed"] == 1 and s["amount_usd"] == 0
        assert s["by_playbook"] == [] or s["by_playbook"][0]["playbook_id"] == inv_id


def test_auto_work_bills_only_after_the_dispute_window(tacit):
    _seed_events(tacit)
    with session() as db:
        pb = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%2fa%")))
        pb.approvals = 5
        tacit.shadow.set_stage(db, pb, "auto", by="test")
    ingest(tacit, system="slack", kind="message", actor="leila", text="customer locked out, 2fa codes not arriving", target="#support", thread_key="slack:C_SUPPORT:l2", meta={"channel": "#support"})
    with session() as db:
        ledger.settle(db, tacit.settings)
        assert db.scalar(select(M.LedgerEntry)).status == "pending"     # still inside the window
        ledger.settle(db, tacit.settings, now=time.time() + tacit.settings.dispute_window_hours * 3600 + 60)
        e = db.scalar(select(M.LedgerEntry))
        assert e.status == "verified" and e.basis == "undisputed_auto"


def test_console_work_a_person_drove_is_never_billed(tacit):
    with session() as db:
        db.add(M.Policy(id=new_id("pol"), principal="user:admin", tool="file_write", decision="allow"))
    r = tacit.agent.run("console", "user:admin", "write file console-work.txt: hi")
    assert r["actions"]
    with session() as db:
        assert db.scalar(select(M.LedgerEntry)) is None


# ------------------------------------------------------------------ oversight of other vendors' agents
def test_supervises_a_third_party_agent_against_your_humans(tacit):
    _seed_events(tacit)
    with session() as db:
        db.add(M.Agent(id=new_id("agt"), handle="fin", name="Fin", vendor="Intercom", systems=["slack"], price_per_action_usd=0.99))
    now = time.time()
    # a question the team answers a particular way
    ingest(tacit, system="slack", kind="message", actor="jonas", text="how do I reset 2FA for a user who lost their phone?", target="#support", thread_key="slack:C_SUPPORT:o1", ts=now, meta={"channel": "#support"})
    ingest(tacit, system="slack", kind="message", actor="fin", actor_type="agent", target="#support", thread_key="slack:C_SUPPORT:o1", ts=now + 30,
           text="Verify their identity via the billing email on file, then Admin → Users → Reset 2FA. They must re-enrol within 24h.")
    ingest(tacit, system="slack", kind="message", actor="jonas", text="how do I reset 2FA for a user who lost their phone?", target="#support", thread_key="slack:C_SUPPORT:o2", ts=now, meta={"channel": "#support"})
    ingest(tacit, system="slack", kind="message", actor="fin", actor_type="agent", target="#support", thread_key="slack:C_SUPPORT:o2", ts=now + 30,
           text="Thanks for reaching out! I've escalated this to our support specialists. 🙂")
    with session() as db:
        good, bad = sorted(db.scalars(select(M.AgentAction)).all(), key=lambda a: -(a.conformance or 0))
        assert good.conformance > 0.5 > bad.conformance          # graded against the team's real answer
        assert good.expected and not good.reworked
    # a human steps in after the bad one: that is rework, and it is the number no vendor reports
    ingest(tacit, system="slack", kind="message", actor="priya", text="Ignore that — verify via billing email then Admin → Users → Reset 2FA.", target="#support", thread_key="slack:C_SUPPORT:o2", ts=now + 1800, meta={"channel": "#support"})
    with session() as db:
        bad = db.scalars(select(M.AgentAction).where(M.AgentAction.reworked == True)).first()  # noqa: E712
        assert bad.rework_by == "priya" and bad.verdict == "reworked"
        oversight.settle(db, now=now + oversight.REWORK_WINDOW_S + 60)
        agent = db.scalar(select(M.Agent))
        card = oversight.scorecard(db, agent, 30)
        assert card["actions"] == 2 and card["reworked"] == 1 and card["rework_rate"] == 0.5
        assert card["vendor_spend_usd"] == 1.98 and card["cost_per_landed_action_usd"] == 1.98   # billed twice, landed once
        f = oversight.fleet(db, tacit, 30)
        assert f["totals"]["agents"] == 1 and f["tacit"]["governed"] is True


def test_agent_actions_are_graded_retroactively_when_a_job_is_learned(tacit):
    with session() as db:
        db.add(M.Agent(id=new_id("agt"), handle="fin", name="Fin", vendor="Intercom", systems=["slack"]))
    now = time.time()
    ingest(tacit, system="slack", kind="message", actor="jonas", text="can someone send the Acme invoice for last month?", target="#billing", thread_key="slack:C_BILLING:r1", ts=now, meta={"channel": "#billing"})
    ingest(tacit, system="slack", kind="message", actor="fin", actor_type="agent", target="#billing", thread_key="slack:C_BILLING:r1", ts=now + 20,
           text="I can't access invoices directly. Please contact billing@ for that.")
    with session() as db:
        assert db.scalar(select(M.AgentAction)).conformance is None      # no job learned yet
    _seed_events(tacit)                                                   # now the team's history arrives and is mined
    with session() as db:
        a = db.scalar(select(M.AgentAction))
        assert a.conformance is not None and a.playbook_id and a.verdict == "off-standard"


# ------------------------------------------------------------------ compliance
def test_audit_log_is_sealed_and_tampering_is_detectable(tacit):
    tacit.agent.run("console", "user:admin", "remember that invoices are net 30")
    with session() as db:
        assert compliance.seal(db) > 0
        v = compliance.verify(db)
        assert v["intact"] and v["sealed_events"] > 0 and v["unsealed_events"] == 0
        root = v["root"]
        assert compliance.seal(db) == 0                                   # idempotent
        assert compliance.verify(db)["root"] == root
    with session() as db:                                                  # somebody edits history
        row = db.scalars(select(M.AuditEvent).where(M.AuditEvent.action == "tool.run")).first()
        row.actor = "somebody-else"
    with session() as db:
        v = compliance.verify(db)
        assert not v["intact"] and v["first_break"]["action"] == "tool.run"


def test_evidence_bundle_answers_articles_12_and_14(tacit):
    _seed_events(tacit)
    with session() as db:
        pb = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        tacit.shadow.set_stage(db, pb, "propose", by="user:admin")
        db.add(M.Agent(id=new_id("agt"), handle="fin", name="Fin", vendor="Intercom", systems=["slack"], price_per_action_usd=0.99))
    ingest(tacit, system="slack", kind="message", actor="jonas", text="where's the invoice for Acme?", target="#billing", thread_key="slack:C_BILLING:c1", meta={"channel": "#billing"})
    with session() as db:
        aid = db.scalar(select(M.Approval).where(M.Approval.status == "pending")).id
    tacit.agent.decide_approval(aid, True, by="user:admin")
    with session() as db:
        ev = compliance.evidence(db, tacit, 90)
        assert ev["log_integrity"]["intact"]
        assert ev["oversight"]["approvals_granted"] == 1 and ev["oversight"]["actions_taken"] >= 1
        assert ev["oversight"]["median_time_to_decision_s"] is not None
        sys_ = next(s for s in ev["ai_systems"] if "invoice" in s["name"])
        assert sys_["autonomy"] == "propose" and "approved by a named human" in sys_["human_oversight"]
        assert sys_["evidence"]["graded_drafts"] >= 0 and sys_["stage_changes"]
        assert ev["supervised_third_party_agents"][0]["agent"]["vendor"] == "Intercom"
        assert ev["controls"]["defaults"]["write"] == "ask"


# ------------------------------------------------------------------ day one
def test_day_one_report_costs_the_work_without_touching_anything(tacit):
    for e in _events():
        ingest(tacit, shadow=False, **e)
    with session() as db:
        before = db.query(M.Action).count()
    r = opportunity(tacit)
    assert r["totals"]["jobs"] >= 4
    assert r["totals"]["hours_per_year"] > r["totals"]["hours_recoverable"] > 0
    assert 0 < r["totals"]["coverage"] <= 1 and r["totals"]["value_usd"] > 0
    assert r["start_with"]["hours_recoverable"] == max(j["hours_recoverable"] for j in r["jobs"])
    assert r["observed"]["people"] > 3 and any(s["system"] == "slack" for s in r["observed"]["systems"])
    assert r["bus_factor"] and r["jobs"][0]["why"]
    with session() as db:
        assert db.query(M.Action).count() == before                        # read-only: nothing acted


# ------------------------------------------------------------------ correcting a mined job
def test_editing_a_job_resets_the_trust_it_earned_under_the_old_definition(client):
    client.post("/api/v1/auth/setup", json={"email": "a@b.co", "name": "A", "password": "correct-horse"})
    from tacit.seed import _events
    client.post("/api/v1/events/batch", json=_events())
    client.post("/api/v1/playbooks/mine")
    pb = next(p for p in client.get("/api/v1/playbooks").json()["playbooks"] if "invoice" in p["name"])
    client.post(f"/api/v1/playbooks/{pb['id']}/stage", json={"stage": "shadow"})
    client.post("/api/v1/playbooks/backtest", json={"playbook_ids": [pb["id"]]})
    before = client.get(f"/api/v1/playbooks/{pb['id']}").json()
    assert before["trust"]["scored"] > 0

    # cosmetic edits keep the evidence
    r = client.patch(f"/api/v1/playbooks/{pb['id']}", json={"name": "Send invoices when finance asks", "summary": "priya replies with the invoice, net 30."})
    assert r.status_code == 200 and r.json()["trust_reset"] is False
    assert client.get(f"/api/v1/playbooks/{pb['id']}").json()["trust"]["scored"] == before["trust"]["scored"]

    # changing what the job *is* invalidates the score earned by the old definition
    r = client.patch(f"/api/v1/playbooks/{pb['id']}", json={"keywords": ["invoice", "billing"], "template": "Sent — net 30, filed in Finance/Invoices."}).json()
    assert r["trust_reset"] is True and r["trust"]["scored"] == 0 and r["trust"]["trust"] == 0.0
    assert r["trigger"]["keywords"] == ["invoice", "billing"]
    assert client.patch(f"/api/v1/playbooks/{pb['id']}", json={"tool": "not_a_tool"}).status_code == 422


def test_an_edited_job_is_demoted_out_of_acting(client):
    client.post("/api/v1/auth/setup", json={"email": "a@b.co", "name": "A", "password": "correct-horse"})
    from tacit.seed import _events
    client.post("/api/v1/events/batch", json=_events())
    client.post("/api/v1/playbooks/mine")
    pb = next(p for p in client.get("/api/v1/playbooks").json()["playbooks"] if "2fa" in p["name"])
    client.post(f"/api/v1/playbooks/{pb['id']}/stage", json={"stage": "shadow"})
    client.post("/api/v1/playbooks/backtest", json={"playbook_ids": [pb["id"]]})
    client.post(f"/api/v1/playbooks/{pb['id']}/stage", json={"stage": "propose"})
    out = client.patch(f"/api/v1/playbooks/{pb['id']}", json={"template": "Totally different answer."}).json()
    assert out["stage"] == "shadow" and out["trust_reset"] is True


# ------------------------------------------------------------------ console services
def test_live_stream_search_and_onboarding(client):
    client.post("/api/v1/auth/setup", json={"email": "a@b.co", "name": "A", "password": "correct-horse"})
    ob = client.get("/api/v1/onboarding").json()
    done = {s["id"]: s["done"] for s in ob["steps"]}
    assert ob["total"] == 6 and not ob["complete"]
    assert [s["id"] for s in ob["steps"]][:2] == ["connect", "mine"]
    # "connect" depends on the operator's own machine; the rest cannot be done on a fresh install
    assert not any(done[k] for k in ("mine", "backtest", "shadow", "oversight"))

    from tacit.seed import _events
    client.post("/api/v1/events/batch", json=_events())
    client.post("/api/v1/playbooks/mine")
    ob = client.get("/api/v1/onboarding").json()
    assert dict((s["id"], s["done"]) for s in ob["steps"])["mine"] is True

    r = client.get("/api/v1/search?q=priya").json()
    assert any(x["kind"] == "person" and x["title"] == "priya" for x in r["results"])
    assert any(x["kind"] == "playbook" for x in client.get("/api/v1/search?q=invoice").json()["results"])

    client.post("/api/v1/onboarding/dismiss")
    assert client.get("/api/v1/onboarding").json()["dismissed"] is True
    assert "lines" in client.get("/api/v1/digest?days=7").json()


def test_audited_facts_reach_open_consoles(tacit):
    from tacit.core.live import live
    q = live.subscribe()
    try:
        tacit.agent.run("console", "user:admin", "run: echo watched")      # exec → needs approval
        kinds = []
        while not q.empty():
            kinds.append(q.get_nowait()["kind"])
        assert "tool.ask" in kinds                                          # the console learns without asking
    finally:
        live.unsubscribe(q)


# ------------------------------------------------------------------ measuring the human, not the AI
def _considered(db, approval_id: str, seconds: float = 40.0):
    """Back-date an approval's creation so the decision looks like someone actually read it."""
    a = db.get(M.Approval, approval_id)
    a.created_at = time.time() - seconds
    db.flush()
    return a


def test_an_approval_nobody_had_time_to_read_does_not_buy_autonomy(tacit):
    from tacit.core.oversight_quality import counted_as_evidence, decision_quality, min_read_seconds
    _seed_events(tacit)
    with session() as db:
        pb = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        tacit.shadow.set_stage(db, pb, "propose", by="test")
        pb_id = pb.id

    # 1. instant approval on a long preview — a signature
    ingest(tacit, system="slack", kind="message", actor="jonas", text="where's the invoice for Acme?", target="#billing", thread_key="slack:C_BILLING:q1", meta={"channel": "#billing"})
    with session() as db:
        a = db.scalar(select(M.Approval).where(M.Approval.status == "pending"))
        assert min_read_seconds(a) > 2.5          # there is real text to read
        aid = a.id
    tacit.agent.decide_approval(aid, True, by="user:rushed")
    with session() as db:
        q = decision_quality(db, db.get(M.Approval, aid))
        assert q["attention"] == "rubber-stamped" and q["seconds"] < q["needed_seconds"]
        assert db.get(M.Playbook, pb_id).approvals == 0            # not evidence
        assert not counted_as_evidence(db, db.get(M.Approval, aid))
        assert any(e.action == "approval.unread" for e in db.scalars(select(M.AuditEvent)))

    # 2. the same decision, taken with time — evidence
    ingest(tacit, system="slack", kind="message", actor="leila", text="where's the invoice for Globex?", target="#billing", thread_key="slack:C_BILLING:q2", meta={"channel": "#billing"})
    with session() as db:
        aid2 = _considered(db, db.scalar(select(M.Approval).where(M.Approval.status == "pending")).id).id
    tacit.agent.decide_approval(aid2, True, by="user:careful")
    with session() as db:
        assert decision_quality(db, db.get(M.Approval, aid2))["attention"] == "considered"
        assert db.get(M.Playbook, pb_id).approvals == 1            # only this one counted


def test_the_index_names_what_is_wrong_and_who(tacit):
    from tacit.core.oversight_quality import report
    _seed_events(tacit)
    with session() as db:
        pb = db.scalar(select(M.Playbook).where(M.Playbook.name.like("%invoice%")))
        tacit.shadow.set_stage(db, pb, "propose", by="test")

    for i in range(6):                                              # one person, always instant, never refusing
        ingest(tacit, system="slack", kind="message", actor="jonas", text=f"where's the invoice for Acme {i}?", target="#billing", thread_key=f"slack:C_BILLING:i{i}", meta={"channel": "#billing"})
        with session() as db:
            aid = db.scalar(select(M.Approval).where(M.Approval.status == "pending")).id
        tacit.agent.decide_approval(aid, True, by="user:rushed")

    with session() as db:
        r = report(db, tacit, 90)
    assert r["decisions"] == 6
    rv = r["reviewers"][0]
    assert rv["reviewer"] == "user:rushed" and rv["rubber_stamp_rate"] == 1.0 and rv["refusal_rate"] == 0.0
    assert 0 <= r["index"] <= 100 and r["index"] < 60               # this is not effective oversight
    titles = " ".join(f["title"] for f in r["findings"])
    assert "signed, not read" in titles and "ever been refused" in titles and "one person" in titles
    assert {c["name"] for c in r["components"]} >= {"Attention", "Independence", "Spread"}
    assert sum(c["weight"] for c in r["components"]) == pytest.approx(1.0, abs=0.01)


def test_evidence_bundle_reports_whether_oversight_was_real(client):
    client.post("/api/v1/auth/setup", json={"email": "a@b.co", "name": "A", "password": "correct-horse"})
    from tacit.seed import _events
    client.post("/api/v1/events/batch", json=_events())
    client.post("/api/v1/playbooks/mine")
    pb = next(p for p in client.get("/api/v1/playbooks").json()["playbooks"] if "invoice" in p["name"])
    client.post(f"/api/v1/playbooks/{pb['id']}/stage", json={"stage": "propose"})
    client.post("/api/v1/events", json={"system": "slack", "kind": "message", "actor": "jonas", "text": "where's the invoice for Acme?", "target": "#billing", "thread_key": "slack:C_BILLING:ev1", "meta": {"channel": "#billing"}})
    aid = client.get("/api/v1/approvals").json()["approvals"][0]["id"]
    client.post(f"/api/v1/approvals/{aid}/decide", json={"approve": True})

    q = client.get("/api/v1/oversight-quality?days=90").json()
    assert q["decisions"] == 1 and q["reviewers"][0]["rubber_stamp_rate"] == 1.0
    ev = client.get("/api/v1/compliance").json()["oversight_effectiveness"]
    assert ev["index"] == q["index"] and ev["reviewers"] and "rubber-stamped" in ev["method"]
    assert any("signed, not read" in f["title"] for f in ev["findings"])


def test_the_band_will_not_say_effective_while_something_high_severity_stands(tacit):
    from tacit.core.oversight_quality import _band
    assert _band(92, []) == "effective"
    assert _band(92, [{"severity": "medium"}]) == "effective"
    assert _band(92, [{"severity": "high"}]) == "nominal"      # the weighted average does not get to whitewash it
    assert _band(31, [{"severity": "high"}]) == "decorative"   # and the cap never flatters a bad score upwards


def test_fatigue_is_measured_against_the_reviewer_s_own_pace_not_a_fixed_number_of_seconds(tacit):
    """A team whose previews are short would never trip an absolute seconds-per-day threshold, and that is
    exactly the team most likely to be rubber-stamping."""
    from tacit.core.oversight_quality import _findings, _reviewer
    now = time.time()
    quick = [{"id": i, "by": "user:tired", "status": "approved", "seconds": s, "needed_seconds": 4.0,
              "attention": "considered", "confidence": 0.8, "reversed_after": False, "escalated": False,
              "decided_at": now - (30 - i) * 86400, "created_at": now - (30 - i) * 86400, "tool": "slack_post",
              "playbook_id": None}
             for i, s in enumerate([9, 10, 8, 9, 7, 6, 4, 3, 2, 2, 1, 1])]
    r = _reviewer("user:tired", quick)
    assert r["early_seconds"] and r["late_seconds"] and r["late_seconds"] < r["early_seconds"]
    assert abs(r["fatigue_slope_seconds_per_day"]) < 1        # would not have tripped the old absolute rule
    titles = " ".join(f["title"] for f in _findings(quick, [r], []))
    assert "deciding faster over time" in titles


def test_one_reviewer_signing_unread_is_caught_even_when_the_team_average_looks_fine(tacit):
    """The average is where this hides: two careful reviewers can carry a third who signs everything."""
    from tacit.core.oversight_quality import _findings, _reviewer
    now = time.time()

    def dec(by, secs, i):
        return {"id": i, "by": by, "status": "approved", "seconds": secs, "needed_seconds": 8.0,
                "attention": "rubber-stamped" if secs < 8.0 else "considered", "confidence": 0.8,
                "reversed_after": False, "escalated": False, "decided_at": now - i * 3600,
                "created_at": now - i * 3600, "tool": "slack_post", "playbook_id": None}

    careful = [dec("user:careful", 20.0, i) for i in range(50)]
    rushed = [dec("user:rushed", 1.0, 100 + i) for i in range(9)]
    rows = careful + rushed
    assert sum(1 for q in rows if q["attention"] == "rubber-stamped") / len(rows) < 0.2   # team average is "fine"
    reviewers = [_reviewer("user:careful", careful), _reviewer("user:rushed", rushed)]
    f = next(f for f in _findings(rows, reviewers, []) if "signed, not read" in f["title"])
    assert f["severity"] == "high" and "user:rushed" in f["detail"]
