"""GitHub backfill: real issue-tracker history (openings + comments, bots dropped) becomes minable events,
and a first reply is paired with the thread opener however late it comes (issue trackers: days or weeks)."""
import time

from sqlalchemy import select

from tacit import models as M
from tacit.connectors.github import GitHub, _is_bot
from tacit.core.playbooks import remine
from tacit.db import session


def test_bot_accounts_are_recognised(tacit):
    assert _is_bot("github-actions[bot]") and _is_bot("nextjs-bot") and _is_bot("codspeed[bot]")
    assert not _is_bot("marcoshernanz") and not _is_bot("abbot")


def test_backfill_ingests_history_and_mining_uses_the_wide_window(tacit, monkeypatch):
    gh = GitHub(tacit)
    gh.token = "fake"
    day = 86400
    t0 = time.time() - 40 * day
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
    issues, comments = [], []
    for n in range(1, 7):
        t = t0 + n * 3 * day
        issues.append({"id": 1000 + n, "number": n, "title": f"Build fails on Windows {n}", "body": "npm run build crashes with EPERM on Windows",
                       "user": {"login": f"user{n}"}, "created_at": iso(t), "html_url": f"https://example/{n}"})
        comments.append({"id": 2000 + n, "issue_url": f"https://api/repos/o/r/issues/{n}", "user": {"login": "triager"},
                         "body": "Thanks for the report. I could not reproduce this on the latest canary, please share a minimal repo.",
                         "created_at": iso(t + 2 * day), "html_url": ""})          # two days later: outside the 6h chat window
        comments.append({"id": 3000 + n, "issue_url": f"https://api/repos/o/r/issues/{n}", "user": {"login": "nextjs-bot"},
                         "body": "stats comment", "created_at": iso(t + 60), "html_url": ""})

    def fake_get(path, **params):
        if path.endswith("/issues"):
            return 200, issues if params.get("page", 1) == 1 else []
        if path.endswith("/issues/comments"):
            return 200, comments if params.get("page", 1) == 1 else []
        return 404, {}
    monkeypatch.setattr(gh, "get", fake_get)

    r = gh.backfill("o/r", iso(t0))
    assert r == {"repo": "o/r", "since": iso(t0), "issues": 6, "comments": 6, "skipped_bots": 6}
    assert gh.backfill("o/r", iso(t0))["comments"] == 0          # idempotent on external_id
    with session() as db:
        assert db.scalar(select(M.Event).where(M.Event.actor == "nextjs-bot")) is None

    # replies came two days after the opener: outside the chat-sized window, but a first reply always answers the opener
    found = remine(by="test", trigger_window_s=6 * 3600)
    assert found["found"] == 1
    with session() as db:
        pb = db.scalar(select(M.Playbook))
        assert pb.actor == "triager" and pb.evidence_count == 6 and pb.trigger["mode"] == "reply"
