"""Permissions, budgets, transactions, replay, jail — the parts a buyer's security team reads first."""
from sqlalchemy import select

from tacit import models as M
from tacit.core.ids import new_id
from tacit.core.replay import replay
from tacit.db import session


def test_read_allowed_write_asks_and_resume(tacit):
    r = tacit.agent.run("test", "slack:U1", "remember that deploys freeze on Friday")
    assert r["status"] == "done"                                   # memory_remember is a read-risk tool
    r = tacit.agent.run("test", "slack:U1", "run: echo hello-world")
    assert r["status"] == "waiting"
    with session() as db:
        a = db.scalar(select(M.Approval).where(M.Approval.status == "pending"))
        assert a.tool == "shell_run" and a.preview["irreversible"] is True
        aid = a.id
        assert not any(e.action == "tool.run" and e.target == "shell_run" for e in db.scalars(select(M.AuditEvent)))
    r2 = tacit.agent.decide_approval(aid, True, by="test")
    assert r2["status"] == "done" and "hello-world" in r2["output"]


def test_deny_blocks_and_policy_hides(tacit):
    r = tacit.agent.run("test", "slack:U1", "run: echo nope")
    with session() as db:
        aid = db.scalar(select(M.Approval)).id
    r2 = tacit.agent.decide_approval(aid, False)
    assert r2["status"] == "done" and "nope\n" not in r2["output"]
    with session() as db:
        db.add(M.Policy(id=new_id("pol"), principal="automation:*", tool="shell_run", decision="deny")); db.flush()
        assert "shell_run" not in [t.name for t in tacit.policy.visible(db, "automation:x", tacit.registry.all())]
        assert "shell_run" in [t.name for t in tacit.policy.visible(db, "user:admin", tacit.registry.all())]


def test_workspace_jail(tacit):
    r = tacit.agent.run("test", "user:admin", "read ../../../etc/passwd")
    assert "escapes workspace" in r["output"]


def test_file_write_preview_diff_and_undo(tacit):
    with session() as db:
        db.add(M.Policy(id=new_id("pol"), principal="user:admin", tool="file_write", decision="allow"))
    r = tacit.agent.run("test", "user:admin", "write file notes.txt: hello")
    assert r["status"] == "done" and r["actions"][0]["preview"]["kind"] == "create"
    r2 = tacit.agent.run("test", "user:admin", "write file notes.txt: hello world")
    pv = r2["actions"][0]["preview"]
    assert pv["kind"] == "update" and "+hello world" in pv["diff"] and "-hello" in pv["diff"]
    out = tacit.agent.undo_run(r2["id"])
    assert out["tx_status"] == "undone"
    r3 = tacit.agent.run("test", "user:admin", "read notes.txt")
    assert "hello\n" in r3["output"] and "hello world" not in r3["output"]
    out = tacit.agent.undo_run(r["id"])
    assert out["results"][0]["undone"]                                 # undo of a create = delete


def test_budget_hard_cap(tacit):
    with session() as db:
        db.add(M.Budget(id=new_id("bud"), scope="automation:*", max_writes_per_hour=1, max_usd_per_day=100))
        db.add(M.Policy(id=new_id("pol"), principal="automation:*", tool="file_write", decision="allow"))
    a = tacit.agent.run("test", "automation:x", "write file a.txt: 1")
    b = tacit.agent.run("test", "automation:x", "write file b.txt: 2")
    assert a["status"] == "done" and len(a["actions"]) == 1
    assert len(b["actions"]) == 0 and "budget" in b["output"]


def test_replay_reproduces_decisions_without_side_effects(tacit):
    r = tacit.agent.run("test", "user:admin", "remember that the API rate limit is 600 rpm")
    with session() as db:
        n = db.query(M.Memory).count()
    out = replay(tacit, r["id"])
    assert out["diff"]["identical"] and out["diff"]["overlap"] == 1.0
    with session() as db:
        assert db.query(M.Memory).count() == n                          # replay never writes
        rr = db.get(M.Run, out["replay_run_id"])
        assert rr.replay_of == r["id"]
