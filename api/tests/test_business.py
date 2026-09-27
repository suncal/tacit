"""Verified-work billing, third-party agent oversight, tamper-evident compliance, Day-One report."""
import time

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
