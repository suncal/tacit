"""    tacit serve         run the API + console
    tacit demo          seed a demo org, then serve
    tacit doctor        what's connected, which brain
    tacit seed          seed only
    tacit import-slack-export PATH [--channels a,b]
                        load a Slack workspace export (zip or folder) as history, then mine + backtest
    tacit backfill-github OWNER/REPO --since 2026-07-01 [--window-h 72] [--judge N]
                        ingest a repo's real issue/PR history, mine playbooks, backtest with the judge, write a JSON report
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tacit")
    ap.add_argument("cmd", nargs="?", default="serve", choices=["serve", "demo", "doctor", "seed", "backfill-github", "import-slack-export"])
    ap.add_argument("repo", nargs="?", help="owner/name for backfill-github; export path for import-slack-export")
    ap.add_argument("--channels", help="import-slack-export: only these channel names (comma-separated)")
    ap.add_argument("--since", default="2026-07-01", help="ISO date, backfill-github")
    ap.add_argument("--window-h", type=float, help="mining trigger window in hours (default from settings; 72 suits issue trackers)")
    ap.add_argument("--judge", type=int, default=40, help="backtest drafts per playbook")
    ap.add_argument("--out", help="write the backfill report JSON here")
    ap.add_argument("--min-evidence", type=int, default=1, help="backfill-github: only backtest playbooks with at least this much evidence")
    ap.add_argument("--no-ingest", action="store_true", help="backfill-github: skip the API pull, re-mine and backtest what is already in the DB")
    ap.add_argument("--port", type=int)
    ap.add_argument("--host")
    ap.add_argument("--db")
    ap.add_argument("--brain")
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args(argv)
    if a.port:
        os.environ["TACIT_PORT"] = str(a.port)
    if a.host:
        os.environ["TACIT_HOST"] = a.host
    if a.db:
        os.environ["TACIT_DATABASE_URL"] = a.db if "://" in a.db else f"sqlite:///{a.db}"
    if a.brain:
        os.environ["TACIT_BRAIN_PROVIDER"] = a.brain
    if a.cmd == "demo" and not os.environ.get("TACIT_ORG_NAME"):
        os.environ["TACIT_ORG_NAME"] = "Northwind Labs"
    from .settings import get_settings
    s = get_settings()
    from .db import Base, engine
    from . import models  # noqa: F401  (register tables before create_all)
    Base.metadata.create_all(engine)
    from .app import TacitApp
    if a.cmd == "doctor":
        t = TacitApp(s)
        b = t.brain_info()
        print(f"tacit {__import__('tacit').__version__}\ndb:     {s.database_url}\nbrain:  {b['provider']} ({b['model']}){'' if b['llm'] else '  ← no LLM: deterministic local brain'}")
        for i in t.integrations():
            print(f"{i['name']:<12} {'connected' if i['connected'] else 'not set  '}  {i['detail'] if i['connected'] else '(' + i['how'] + ')'}")
        print(f"tools:  {len(t.registry.all())}")
        return 0
    t = TacitApp(s)
    if a.cmd == "backfill-github":
        return _backfill_github(t, a)
    if a.cmd == "import-slack-export":
        return _import_slack(t, a)
    if a.cmd in ("demo", "seed"):
        from .seed import seed
        r = seed(t)
        print("seed:", r)
        if a.cmd == "seed":
            return 0
    import uvicorn
    from .main import create_app
    app = create_app(t, background=True)
    print(f"Tacit is up → http://{s.host}:{s.port}   docs → /api/docs   brain={t.brain_info()['provider']}")
    if a.cmd == "demo":
        print("demo login → demo@northwind.dev / tacit-demo")
    uvicorn.run(app, host=s.host, port=s.port, log_level="warning")
    return 0


def _import_slack(t, a) -> int:
    import json
    import time
    if not a.repo or not os.path.exists(a.repo):
        print("usage: tacit import-slack-export <export.zip | folder> [--channels general,support]", file=sys.stderr)
        return 2
    t0 = time.time()
    chans = [c.strip() for c in a.channels.split(",")] if a.channels else None
    r = t.slack.import_export(a.repo, chans, progress=lambda m: print("  " + m, flush=True))
    print("imported:", r, flush=True)
    from .core.playbooks import remine
    window = (a.window_h or t.settings.mining_trigger_window_h) * 3600
    mined = remine(by="import", brain=t.brain, trigger_window_s=window)
    print("mined:", mined, flush=True)
    from .core.backtest import backtest
    bt = backtest(t, None, a.judge)
    print(f"backtest: {bt['total']}  ({bt['seconds']}s)", flush=True)
    for pb in bt["playbooks"]:
        print(f"  {pb['hit_rate']:.0%} ({pb['hits']}/{pb['n']})  {pb['name']}")
    if a.out:
        out = os.path.abspath(a.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump({"import": r, "mine": mined, "backtest": bt, "seconds": round(time.time() - t0, 1)}, f, indent=1, default=str)
        print("report →", out)
    return 0


def _backfill_github(t, a) -> int:
    import json
    import time
    if not a.repo or "/" not in a.repo:
        print("usage: tacit backfill-github OWNER/REPO --since YYYY-MM-DD", file=sys.stderr)
        return 2
    if not t.github.ok() and not a.no_ingest:
        print("no GitHub token (TACIT_GITHUB_TOKEN or `gh auth login`)", file=sys.stderr)
        return 1
    since = a.since if "T" in a.since else a.since + "T00:00:00Z"
    t0 = time.time()
    print(f"backfilling {a.repo} since {since} …", flush=True)
    bf = {"skipped": True} if a.no_ingest else t.github.backfill(a.repo, since, progress=lambda m: print("  " + m, flush=True))
    print("ingested:", bf, flush=True)
    from .core.playbooks import remine
    window = (a.window_h or t.settings.mining_trigger_window_h) * 3600
    mined = remine(by="backfill", brain=t.brain, trigger_window_s=window)
    print("mined:", mined, flush=True)
    from .core.backtest import backtest
    ids = None
    if a.min_evidence > 1:
        from sqlalchemy import select
        from . import models as M
        from .db import session
        with session() as db:
            ids = list(db.scalars(select(M.Playbook.id).where(M.Playbook.evidence_count >= a.min_evidence, M.Playbook.stage != "retired")))
        print(f"backtesting {len(ids)} playbooks with evidence ≥ {a.min_evidence}", flush=True)
    bt = backtest(t, ids, a.judge)
    print(f"backtest: {bt['total']}  ({bt['seconds']}s)", flush=True)
    for pb in bt["playbooks"]:
        print(f"  {pb['hit_rate']:.0%} ({pb['hits']}/{pb['n']})  {pb['name']}")
    report = {"repo": a.repo, "since": since, "window_h": window / 3600, "brain": t.brain_info(), "ingest": bf, "mine": mined,
              "backtest": bt, "seconds": round(time.time() - t0, 1), "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if a.out:
        pathlib_out = os.path.abspath(a.out)
        os.makedirs(os.path.dirname(pathlib_out), exist_ok=True)
        with open(pathlib_out, "w") as f:
            json.dump(report, f, indent=1, default=str)
        print("report →", pathlib_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
