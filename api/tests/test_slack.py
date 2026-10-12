"""Slack: Socket Mode events become threaded events, bots are marked, and a workspace export loads as history."""
import json
import os
import time

from sqlalchemy import select

from tacit import models as M
from tacit.connectors.slack import Slack
from tacit.core.playbooks import remine
from tacit.db import session


def _slack(tacit, monkeypatch):
    s = Slack(tacit)
    s.token, s.app_token, s.bot_id = "xoxb-test", "xapp-test", "UBOT"
    s.names["U1"], s.names["U2"] = "Priya", "Sam"
    monkeypatch.setattr(s, "call", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network in tests")))
    return s


def test_events_api_messages_are_threaded_and_bots_marked(tacit, monkeypatch):
    s = _slack(tacit, monkeypatch)
    now = time.time()
    root = f"{now:.6f}"
    assert s.handle_event({"type": "message", "channel": "C1", "user": "U1", "text": "Can someone send Acme their invoice?", "ts": root})
    assert s.handle_event({"type": "message", "channel": "C1", "user": "U2", "text": "Done — Acme invoice sent, net 30.", "ts": f"{now + 60:.6f}", "thread_ts": root})
    assert s.handle_event({"type": "message", "channel": "C1", "user": "UBOT", "bot_id": "B1", "text": "beep", "ts": f"{now + 61:.6f}", "thread_ts": root})
    assert s.handle_event({"type": "message", "channel": "C1", "subtype": "channel_join", "user": "U3", "ts": f"{now + 62:.6f}"}) is None
    assert s.handle_event({"type": "message", "channel": "C1", "user": "U1", "text": "dup", "ts": root}) is None          # same ts = same message
    with session() as db:
        evs = db.scalars(select(M.Event).where(M.Event.system == "slack").order_by(M.Event.ts)).all()
    assert [e.actor for e in evs] == ["Priya", "Sam", "UBOT"]
    assert {e.thread_key for e in evs} == {f"slack:C1:{root}"}
    assert [e.actor_type for e in evs] == ["human", "human", "tacit"]


def test_channel_filter_and_mention_summons_agent(tacit, monkeypatch):
    s = _slack(tacit, monkeypatch)
    s.channels = ["C9"]
    assert s.handle_event({"type": "message", "channel": "C1", "user": "U1", "text": "ignored", "ts": "1.0"}) is None
    seen = {}
    monkeypatch.setattr(s, "handle_mention", lambda ch, user, text, thread: seen.update(ch=ch, user=user, text=text, thread=thread))
    s.handle_event({"type": "app_mention", "channel": "C9", "user": "U1", "text": "<@UBOT> what is our invoice policy?", "ts": "2.0"})
    assert seen == {"ch": "C9", "user": "U1", "text": "<@UBOT> what is our invoice policy?", "thread": "2.0"}


def test_export_import_loads_history_that_mining_can_use(tacit, monkeypatch, tmp_path):
    s = _slack(tacit, monkeypatch)
    exp = tmp_path / "export"
    (exp / "billing").mkdir(parents=True)
    (exp / "users.json").write_text(json.dumps([{"id": "U1", "real_name": "Priya K", "profile": {"display_name": "priya"}},
                                                {"id": "U2", "name": "sam", "profile": {}}]))
    (exp / "channels.json").write_text(json.dumps([{"name": "billing"}]))
    t0 = time.time() - 30 * 86400
    for d in range(6):
        root = f"{t0 + d * 86400:.6f}"
        msgs = [{"type": "message", "user": "U1", "text": f"Customer {d} is asking for their invoice copy", "ts": root},
                {"type": "message", "user": "U2", "text": "Sent — invoice copy is in Finance/Invoices, net 30 as usual.", "ts": f"{t0 + d * 86400 + 900:.6f}", "thread_ts": root},
                {"type": "message", "subtype": "channel_join", "user": "U9", "ts": f"{t0 + d * 86400 + 1:.6f}"}]
        (exp / "billing" / f"2026-09-{d + 1:02d}.json").write_text(json.dumps(msgs))
    r = s.import_export(str(exp))
    assert r["messages"] == 12 and r["skipped"] == 6 and r["channels"] == ["billing"] and r["users"] == 2
    assert s.import_export(str(exp))["messages"] == 0                       # idempotent
    with session() as db:
        actors = {e.actor for e in db.scalars(select(M.Event).where(M.Event.system == "slack"))}
    assert actors == {"priya", "sam"}
    remine(by="test", trigger_window_s=6 * 3600)
    with session() as db:                       # priya's daily asks also mine as a cadence job; the reply job is the one we want
        pb = db.scalar(select(M.Playbook).where(M.Playbook.actor == "sam"))
    assert pb and pb.trigger["mode"] == "reply" and pb.evidence_count == 6 and pb.response["tool"] == "slack_post"


def test_export_import_reads_a_zip(tacit, monkeypatch, tmp_path):
    import zipfile
    s = _slack(tacit, monkeypatch)
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("My Workspace export/users.json", json.dumps([{"id": "U1", "real_name": "Priya K"}]))
        zf.writestr("My Workspace export/channels.json", json.dumps([{"name": "general"}]))
        zf.writestr("My Workspace export/general/2026-09-01.json", json.dumps([{"type": "message", "user": "U1", "text": "hello", "ts": "1700000000.000100"}]))
    r = s.import_export(str(z))
    assert r["messages"] == 1 and r["channels"] == ["general"]
    with session() as db:
        e = db.scalar(select(M.Event).where(M.Event.system == "slack"))
    assert e.actor == "Priya K" and e.target == "general" and e.thread_key == "slack:general:1700000000.000100"
